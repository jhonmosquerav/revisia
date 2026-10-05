"""Carga robusta de los artefactos de una corrida (spec 2026-10-04 §9.1).

Los loaders **nunca lanzan**: devuelven un :class:`Loaded` con el valor o con
el error (``OSError``, ``UnicodeDecodeError``, JSON/YAML inválido, raíz de tipo
inesperado, ``ValidationError``, ``RecursionError``, YAML demasiado anidado, YAML
con claves de fusión o con costes cuadráticos de carga y cualquier otra excepción
del parser). Antes de la Ola 1 un ``manifest.yml`` con raíz de lista reventaba el
auditor con ``AttributeError`` y una línea corrupta del ledger se descartaba en
silencio (auditoría 2026-09-03, A11/C3): un auditor que revienta o que ignora lo
ilegible no verifica nada. «Nunca lanzan» incluye lo que ningún ``except`` atrapa: un
YAML con miles de niveles de anidamiento desborda la pila nativa de ``CSafeLoader`` y
mata el proceso sin informe, y una bomba de claves de fusión (``<<``), un entero
sexagesimal de cientos de KB o decenas de miles de claves enteras que colisionan en
el hash (como escalares o como alias) cuelgan la carga misma; todos se rechazan antes de
cargar (revisiones de la Tarea 4 y de la fase 1 de PR-E).

``AuditContext`` reúne lo que los checks comparten (manifiesto, ledger,
decisiones efectivas, estado, protocolo) y lo calcula una sola vez.
"""

from __future__ import annotations

import json
import reprlib
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any, Generic, TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError

from revisia.audit.state import RunState, derive_state
from revisia.config import STAGES, ReviewProtocol
from revisia.exclusions import ExclusionBreakdown
from revisia.exports import PrismaCounts
from revisia.extraction_agreement import ExtractionAgreement
from revisia.meta_analysis import MetaAnalysisResult
from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import HumanDecision
from revisia.provenance.ledger import DecisionEntry, summarize_gates
from revisia.provenance.runmeta import RunMeta
from revisia.schemas.artifacts import GATED_STAGES, GateSummary, RunInfo
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision
from revisia.schemas.verification import VerificationReport

# `TypeVar` + `Generic` y no la sintaxis `class Loaded[T]` de 3.12: la suite
# también corre en 3.11 (spec 2026-10-04 §11; M24 es de la Ola 2).
T = TypeVar("T")

# El loader en C es órdenes de magnitud más rápido con manifiestos de miles de
# `llm_calls`; PyYAML sin libyaml no lo trae.
_YAML_LOADER: type = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

# Guarda contra el YAML hostil: UNA sola, por eventos del parser, SIEMPRE, antes de cargar.
#
# Cuatro vectores matan o cuelgan el proceso sin que ningún `except` lo atrape:
# - Anidamiento: `CSafeLoader` compone los nodos con recursión nativa de C, que
#   `sys.setrecursionlimit` no limita. Medido en Windows con Python 3.13, a ~2 670 niveles
#   (2 669-2 673 según la sintaxis) desborda la pila (0xC00000FD) y mata el proceso sin
#   informe. Los manifiestos reales tienen profundidad < 20; el límite uniforme de 500
#   niveles queda ≈ 5× bajo el crash.
# - Claves de fusión (`<<`): `flatten_mapping` copia los pares de cada alias sin memoizar,
#   así que `aN: &aN {<<: [*a(N-1) ×9]}` los multiplica ×9 por nivel (el nivel 8 ya tarda
#   segundos; el 10, minutos y decenas de GB). El motor nunca escribe `<<`: se rechaza. Los
#   alias normales (`*a`) comparten nodos y siguen permitidos.
# - Enteros larguísimos: el resolver YAML 1.1 de PyYAML tiene los enteros sexagesimales
#   (`1:1:1:…`) y su construcción hace aritmética de enteros grandes, cuadrática en la longitud
#   (un escalar plano de 400 KB tarda ~15 s). El motor escribe números de unas pocas cifras:
#   se rechaza todo escalar de más de `_YAML_MAX_ESCALAR_NUMERICO` (1 000) caracteres que el
#   resolver del propio loader resolvería a `int` o `float` (o que lleve esa etiqueta explícita),
#   sin construir su valor.
# - Claves enteras que colisionan: `i·(2⁶¹−1)` da hash 0 para todo `i`, y N claves así llenan el
#   diccionario en O(N²) (40 000 claves ≈ 16 s). Se rechaza el documento con más de
#   `_YAML_MAX_CLAVES_ENTERAS` (10 000) claves de mapa planas que resuelvan a `int`; el límite
#   es del documento y no de cada mapa, porque cien mapas de 9 999 claves costarían lo mismo que
#   uno solo de un millón. Los valores enteros (`seed: 7`) y las claves de texto no cuentan.
#   Un ALIAS en posición de clave (`*a1 : 1`, con `a1` un entero anclado en un valor) no es un
#   escalar y esquivaba el contador: 40 000 ≈ 15 s, 80 000 ≈ 105 s. El motor nunca escribe un
#   alias como clave (`safe_dump` no ancla escalares: `SafeRepresenter.ignore_aliases`), así que
#   se rechaza cualquiera, de cualquier tamaño; en valores siguen permitidos. Las claves
#   complejas (`? [a, b]`) no hacen falta: el `SafeLoader` las rechaza al construir (no son
#   hashables) con un «YAML inválido» limpio.
#
# Se mide por **eventos** del parser, no con regex sobre el texto: el parser ya resolvió
# comillas, escapes, comentarios, el BOM y los saltos de línea que libyaml reconoce (U+2028,
# U+2029 y U+0085, además de `\n`). Unas regex físicas por línea (`^` + `re.MULTILINE`) se
# esquivaban con cualquiera de ellos y dejaban pasar el desbordamiento (tercera revisión de
# la Tarea 4). La pila del parser de libyaml vive en el heap: solo el compositor recursa, y
# aquí no se compone. El recorrido solo cuesta algo apreciable en manifiestos de miles de
# llamadas (coste medido en el informe de la tarea).
#
# Se aplica con el loader que luego carga (`CSafeLoader` si existe) y funciona igual con el
# `SafeLoader` de Python puro, para que el veredicto no dependa de tener libyaml.
_YAML_MAX_DEPTH = 500  # niveles de colección (mapas/listas), también el mapa raíz
_YAML_MAX_ESCALAR_NUMERICO = 1_000  # caracteres de un escalar que resuelve a int o float
_YAML_MAX_CLAVES_ENTERAS = 10_000  # claves de mapa planas que resuelven a int, por documento
_YAML_MERGE_TAG = "tag:yaml.org,2002:merge"
_YAML_INT_TAG = "tag:yaml.org,2002:int"
_YAML_FLOAT_TAG = "tag:yaml.org,2002:float"
# Con qué carácter puede empezar un entero plano (YAML 1.1: `+5`, `-5`, `0x1F`, `1_000`, `1:30`):
# evita resolver cada clave de texto de un manifiesto de miles de llamadas.
_YAML_INICIO_ENTERO = frozenset("+-0123456789")

_YAML_ERR_DEPTH = (
    f"estructura YAML demasiado anidada (más de {_YAML_MAX_DEPTH} niveles de colecciones "
    "anidadas); no se carga para no desbordar la pila del intérprete"
)
_YAML_ERR_MERGE = (
    "claves de fusión YAML (<<) no admitidas en artefactos del motor; no se carga para no "
    "multiplicar sus pares en memoria"
)
_YAML_ERR_NUMERO = (
    f"escalar numérico de más de {_YAML_MAX_ESCALAR_NUMERICO} caracteres no admitido en "
    "artefactos del motor; no se carga porque construirlo cuesta tiempo cuadrático"
)
_YAML_ERR_CLAVES = (
    f"más de {_YAML_MAX_CLAVES_ENTERAS} claves enteras en el documento, no admitidas en "
    "artefactos del motor; no se carga porque las que colisionan en el hash cuestan tiempo "
    "cuadrático"
)
_YAML_ERR_ALIAS_CLAVE = (
    "alias como clave de mapping: no admitido en artefactos del motor; no se carga porque los "
    "alias de enteros que colisionan en el hash cuestan tiempo cuadrático"
)


@dataclass(frozen=True)
class Loaded(Generic[T]):  # noqa: UP046 (compatibilidad con 3.11)
    """Resultado de cargar un artefacto: nunca una excepción.

    Attributes:
        path: ruta relativa al directorio de la corrida, con ``/``.
        present: el fichero existe.
        value: el contenido cargado (``None`` si falta o no se pudo cargar;
            en un ``.jsonl`` con líneas corruptas, las líneas legibles).
        error: por qué no se pudo cargar o validar (``None`` si se pudo).
    """

    path: str
    present: bool
    value: T | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.present and self.error is None


class SearchFailure(BaseModel):
    """Una entrada de ``01_search/failures.json``."""

    db: str
    error: str


def _type_names(root: type | tuple[type, ...]) -> str:
    kinds = root if isinstance(root, tuple) else (root,)
    names = {dict: "mapa", list: "lista"}
    return " o ".join(names.get(k, k.__name__) for k in kinds)


def _root_name(value: object) -> str:
    return {dict: "mapa", list: "lista"}.get(type(value), type(value).__name__)


# `repr` de un valor del manifiesto, siempre acotado. Una bomba de alias YAML (`*a` repetido
# nivel tras nivel) carga en milisegundos porque PyYAML comparte los nodos, pero `repr`/`str`
# la recorren entera: 9**10 hojas, el auditor cuelga sin informe (segunda revisión de la
# Tarea 4). `reprlib.repr` con sus límites por defecto no basta (una bomba de 10 niveles da
# ~400 KB): 2 niveles y 3 elementos por colección acotan el coste y el tamaño del detalle.
_SHORT_REPR = reprlib.Repr()
_SHORT_REPR.maxlevel = 2
_SHORT_REPR.maxlist = _SHORT_REPR.maxtuple = _SHORT_REPR.maxdict = _SHORT_REPR.maxset = 3
_SHORT_REPR.maxstring = _SHORT_REPR.maxother = 60


def _acotar(text: str, limit: int) -> str:
    """``text`` recortado a ``limit`` y siempre codificable en UTF-8.

    Un JSON con ``"\\ud800"`` (un sustituto suelto, U+D800) deja en la cadena un carácter
    que ``str`` admite pero que ``write_text(..., encoding="utf-8")`` rechaza con
    ``UnicodeEncodeError``: ``revisia audit`` moría al escribir ``audit.md`` (revisión de la
    Tarea 6). Se escapa el sustituto (``backslashreplace``) **después** de recortar, para que
    el coste siga acotado por ``limit``, y se recorta otra vez porque el escape alarga el
    texto (1 → 6 caracteres).
    """
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    seguro = text.encode("utf-8", "backslashreplace").decode("utf-8")
    return seguro if len(seguro) <= limit else seguro[: limit - 1] + "…"


def short_repr(value: object, *, limit: int = 120) -> str:
    """``repr`` acotado en coste y en longitud para mostrar valores no confiables del manifiesto."""
    return _acotar(_SHORT_REPR.repr(value), limit)


def short_text(value: object, *, limit: int = 120) -> str:
    """Valor del manifiesto para un detalle: las cadenas tal cual (recortadas), lo demás acotado.

    Una cadena no puede ser una bomba de alias, y sin comillas el detalle se lee igual que
    antes de acotarlo. Una fecha (``datetime.date`` o ``datetime.datetime``: PyYAML carga
    ``executed: 2026-10-04`` sin comillas como ``date``) va en ISO-8601, no como el ``repr``
    ``datetime.date(2026, 10, 4)``. Todo lo demás (listas, mapas) pasa por :func:`short_repr`.
    El resultado es siempre codificable en UTF-8 (:func:`_acotar`).
    """
    if isinstance(value, str):
        return _acotar(value, limit)
    if isinstance(value, date):
        return _acotar(value.isoformat(), limit)
    return short_repr(value, limit=limit)


# Detalle de los checks que leen el manifiesto cuando este no se pudo leer: la causa ya está en
# la fila `manifest`, así que aquí es un N/A (§9.2). Lo comparten `provenance` y
# `response_overlap`.
NA_MANIFIESTO = "no aplica: el manifiesto no se pudo leer (ver `manifest`)."

# Ídem para los checks que leen el protocolo registrado en el manifiesto (``thresholds``,
# ``search_window`` y ``registration``): sin manifiesto, o con ``protocol`` ausente o inválido, la
# causa ya está en otra fila (``manifest`` o ``schemas``) y aquí es un N/A (§9.2).
NA_PROTOCOLO = "no aplica: sin protocolo legible en el manifiesto (ver las filas en FAIL)."


def sufijo_mas(resto: int, unidad: str = "") -> str:
    """`` (+N más)`` de una lista acotada, o `` (+N <unidad> más)`` si hay que decir qué falta.

    Una fila con dos listas acotadas (en ``schemas``, los errores de un artefacto y los
    artefactos con error) no puede dar el mismo ``(+N más)`` para las dos: el lector no sabría
    qué le falta por ver (revisión de la fase 1 de PR-E). ``unidad`` va en **singular**
    (``"error"``, ``"artefacto"``) y aquí se pluraliza: ``+1 error más``, ``+2 errores más``.
    ``""`` si no queda resto.
    """
    if resto <= 0:
        return ""
    if not unidad:
        return f" (+{resto} más)"
    plural = unidad + ("s" if unidad[-1] in "aeiou" else "es")
    return f" (+{resto} {unidad if resto == 1 else plural} más)"


def format_validation(exc: ValidationError, *, limit: int = 3) -> str:
    """``loc: msg; loc: msg (+k errores más)`` a partir de una ``ValidationError``."""
    errors = exc.errors()
    parts = [
        f"{'.'.join(str(p) for p in err['loc']) or '(raíz)'}: {err['msg']}"
        for err in errors[:limit]
    ]
    return "; ".join(parts) + sufijo_mas(len(errors) - limit, "error")


def read_text(run_dir: Path, rel: str) -> Loaded[str]:
    """Lee un fichero de texto UTF-8.

    ``exists()``/``is_file()`` también pueden fallar (permisos, rutas inválidas):
    van dentro del ``try`` y un fallo que no sea de decodificación queda como
    ``error`` con el tipo de la excepción, no como excepción.
    """
    path = run_dir / rel
    try:
        if not path.exists():
            return Loaded(rel, False)
        if not path.is_file():
            return Loaded(rel, True, error="no es un fichero")
        return Loaded(rel, True, path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return Loaded(rel, True, error="no es texto UTF-8 (¿UTF-16 o binario?)")
    except Exception as exc:  # fail-closed: «nunca lanzan» (spec §9.1) vale para todo `Exception`
        return Loaded(rel, True, error=f"no se pudo leer ({type(exc).__name__})")


def _json_error(exc: Exception) -> str:
    """``JSON inválido`` con el mensaje del parser; de una excepción inesperada, su tipo."""
    detail = str(exc) if isinstance(exc, ValueError | RecursionError) else type(exc).__name__
    return f"JSON inválido ({detail})"


def read_json(
    run_dir: Path, rel: str, *, root: type | tuple[type, ...] = (dict, list)
) -> Loaded[Any]:
    """Lee un JSON y comprueba el tipo de su raíz."""
    text = read_text(run_dir, rel)
    if not text.ok:
        return Loaded(rel, text.present, error=text.error)
    try:
        value = json.loads(text.value)
    except Exception as exc:  # `ValueError`/`RecursionError` son lo normal; ninguna debe escapar
        return Loaded(rel, True, error=_json_error(exc))
    if not isinstance(value, root):
        return Loaded(rel, True, error=f"la raíz es {_root_name(value)}, no {_type_names(root)}")
    return Loaded(rel, True, value)


def _yaml_guard(text: str) -> str | None:
    """Por qué el YAML se rechaza sin cargarlo, o ``None`` si pasa la guarda.

    Recorre los eventos del parser (pila en el heap: aquí no hay la recursión nativa que
    sí tiene el compositor y que desborda) y rechaza el anidamiento por encima de
    ``_YAML_MAX_DEPTH``, cualquier clave de fusión, los escalares numéricos de más de
    ``_YAML_MAX_ESCALAR_NUMERICO`` caracteres, los documentos con más de
    ``_YAML_MAX_CLAVES_ENTERAS`` claves enteras planas y cualquier alias en posición de clave.
    Ver el comentario de las constantes.

    Un ``yaml.YAMLError`` (YAML mal formado; también el ``ReaderError`` por un carácter de
    control, que el loader de Python puro lanza al construirse) no es un problema de
    anidamiento: ya lo informará la carga, así que se devuelve ``None``.

    Una clave de fusión es un escalar plano ``<<`` o cualquier nodo con la etiqueta
    explícita ``!!merge``: la etiqueta, no el texto, es lo que activa ``flatten_mapping``
    (``!!merge "<<"`` y ``!!merge cualquier-cosa`` también fusionan). Un escalar plano trae
    ``style == ""`` con libyaml y ``None`` con Python puro: se mira con ``not style``.

    Para saber si un escalar o un alias es una clave se lleva, por cada mapa abierto, cuántos
    nodos hijos ha visto (los pares van clave, valor, clave, valor…); una secuencia no lleva
    cuenta.
    """
    loader = None
    try:
        loader = _YAML_LOADER(text)
        abiertas: list[list[int] | None] = []  # una por colección abierta: `None` = secuencia
        claves_enteras = 0
        while loader.check_event():
            event = loader.get_event()
            es_clave = False
            if isinstance(event, yaml.NodeEvent) and abiertas and abiertas[-1] is not None:
                es_clave = abiertas[-1][0] % 2 == 0
                abiertas[-1][0] += 1
            if isinstance(event, yaml.AliasEvent):
                if es_clave:
                    return _YAML_ERR_ALIAS_CLAVE
            elif isinstance(event, yaml.ScalarEvent):
                if event.tag == _YAML_MERGE_TAG or (event.value == "<<" and not event.style):
                    return _YAML_ERR_MERGE
                largo = len(event.value) > _YAML_MAX_ESCALAR_NUMERICO
                if largo or (es_clave and (event.tag or event.value[:1] in _YAML_INICIO_ENTERO)):
                    tag = _etiqueta_escalar(loader, event)
                    if largo and tag in (_YAML_INT_TAG, _YAML_FLOAT_TAG):
                        return _YAML_ERR_NUMERO
                    if es_clave and tag == _YAML_INT_TAG:
                        claves_enteras += 1
                        if claves_enteras > _YAML_MAX_CLAVES_ENTERAS:
                            return _YAML_ERR_CLAVES
            elif isinstance(event, yaml.SequenceStartEvent | yaml.MappingStartEvent):
                if event.tag == _YAML_MERGE_TAG:
                    return _YAML_ERR_MERGE
                abiertas.append(None if isinstance(event, yaml.SequenceStartEvent) else [0])
                if len(abiertas) > _YAML_MAX_DEPTH:
                    return _YAML_ERR_DEPTH
            elif isinstance(event, yaml.SequenceEndEvent | yaml.MappingEndEvent):
                abiertas.pop()
        return None
    except yaml.YAMLError:
        return None
    finally:
        if loader is not None:
            loader.dispose()


def _etiqueta_escalar(loader: Any, event: yaml.ScalarEvent) -> str | None:
    """Etiqueta con la que se construiría el escalar, sin construir su valor.

    Es la regla de ``compose_scalar_node`` con el ``Resolver`` del propio loader (YAML 1.1:
    ``1:30`` es un entero sexagesimal y ``1_000`` un entero): una etiqueta explícita manda; sin
    ella, o con la no específica ``!``, se resuelve por la forma del texto, y eso solo ocurre en
    los escalares planos (``event.implicit[0]``).
    """
    if event.tag is None or event.tag == "!":
        return loader.resolve(yaml.ScalarNode, event.value, event.implicit)
    return event.tag


def read_yaml(run_dir: Path, rel: str, *, root: type | tuple[type, ...] = dict) -> Loaded[Any]:
    """Lee un YAML (``CSafeLoader`` si está disponible) y comprueba su raíz.

    Antes de cargar, ``_yaml_guard`` rechaza el YAML con miles de niveles de anidamiento
    (desbordaría la pila nativa del loader en C y mataría el proceso) y el que lleva claves
    de fusión (cuelgan la carga): revisiones de la Tarea 4. También rechaza (revisiones de la
    fase 1 de PR-E) los escalares numéricos de más de 1 000 caracteres (su construcción es
    cuadrática), los documentos con más de 10 000 claves enteras planas y todo alias en
    posición de clave (las claves enteras que colisionan en el hash cuestan O(N²) al cargar,
    escritas como escalares o como alias de enteros anclados): el motor no escribe nada de
    eso. Los alias en valores siguen permitidos. PyYAML tampoco lanza solo
    ``YAMLError``: una etiqueta explícita como ``!!timestamp foo`` o ``!!bool maybe``
    produce ``AttributeError``/``KeyError``, por eso se captura ``Exception``, guarda
    incluida («nunca lanza» vale también para ella).
    """
    text = read_text(run_dir, rel)
    if not text.ok:
        return Loaded(rel, text.present, error=text.error)
    try:
        problem = _yaml_guard(text.value)
        if problem:
            return Loaded(rel, True, error=problem)
        value = yaml.load(text.value, Loader=_YAML_LOADER)
    except Exception as exc:  # fail-closed: no solo `YAMLError` (ver la docstring)
        return Loaded(rel, True, error=f"YAML inválido ({type(exc).__name__})")
    if not isinstance(value, root):
        return Loaded(rel, True, error=f"la raíz es {_root_name(value)}, no {_type_names(root)}")
    return Loaded(rel, True, value)


def read_jsonl(run_dir: Path, rel: str) -> Loaded[list[tuple[int, Any]]]:
    """Lee un ``.jsonl``: ``value`` = ``[(número de línea, objeto)]`` legibles.

    Una línea que no es JSON no se descarta en silencio: queda en ``error``,
    una por línea de texto y con su número de línea (las líneas en blanco se
    ignoran). Antes de la Ola 1 el auditor las saltaba (auditoría 2026-09-03).

    Las líneas se parten **solo por** ``"\\n"``: ``str.splitlines`` también corta
    en U+2028, U+2029 y U+0085, que ``model_dump_json`` escribe tal cual dentro
    de un ``reason``, y partiría una entrada válida del ledger en dos «líneas
    corruptas» (revisión de la Tarea 4).
    """
    text = read_text(run_dir, rel)
    if not text.ok:
        return Loaded(rel, text.present, error=text.error)
    lines: list[tuple[int, Any]] = []
    errors: list[str] = []
    for number, raw in enumerate(text.value.split("\n"), start=1):
        line = raw.removesuffix("\r")  # CRLF; `read_text` ya normaliza, pero no se depende de ello
        if not line.strip():
            continue
        try:
            lines.append((number, json.loads(line)))
        except Exception as exc:  # fail-closed: la línea queda como error, no como excepción
            errors.append(f"línea {number}: {_json_error(exc)}")
    return Loaded(rel, True, lines, "\n".join(errors) or None)


def validate(loaded: Loaded[Any], adapter: TypeAdapter[T]) -> Loaded[T]:  # noqa: UP047
    """Valida un artefacto cargado contra su modelo (sin lanzar)."""
    if not loaded.ok:
        return Loaded(loaded.path, loaded.present, error=loaded.error)
    try:
        return Loaded(loaded.path, True, adapter.validate_python(loaded.value))
    except ValidationError as exc:
        return Loaded(loaded.path, True, error=format_validation(exc))
    except RecursionError:
        return Loaded(loaded.path, True, error="estructura demasiado anidada")
    except Exception as exc:  # un validador propio puede lanzar algo que pydantic no envuelve
        return Loaded(loaded.path, True, error=f"no se pudo validar ({type(exc).__name__})")


# Artefactos JSON de la corrida y el modelo contra el que se validan.
ARTIFACT_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "01_search/failures.json": TypeAdapter(list[SearchFailure]),
    "03_screening/decisions.json": TypeAdapter(list[ScreeningDecision]),
    "03_screening/metrics.json": TypeAdapter(ScreeningMetrics),
    "03_screening/exclusions.json": TypeAdapter(ExclusionBreakdown),
    "04_fulltext/decisions.json": TypeAdapter(list[ScreeningDecision]),
    "05_extraction/extractions.json": TypeAdapter(dict[str, ExtractionRecord]),
    "05_extraction/agreement.json": TypeAdapter(ExtractionAgreement),
    "06_synthesis/verification.json": TypeAdapter(VerificationReport),
    "07_rob/assessments.json": TypeAdapter(dict[str, RoBAssessment]),
    "08_meta/meta_analysis.json": TypeAdapter(MetaAnalysisResult),
}

# Secciones de ``manifest.yml`` con modelo (las copias de los artefactos y los
# bloques que escribe el motor).
MANIFEST_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "protocol": TypeAdapter(ReviewProtocol),
    "counts": TypeAdapter(PrismaCounts),
    "llm_calls": TypeAdapter(list[RunMeta]),
    "models_used": TypeAdapter(list[str]),
    "deterministic_token_level": TypeAdapter(bool),
    "screening_metrics": TypeAdapter(ScreeningMetrics),
    "verification": TypeAdapter(VerificationReport),
    "exclusions": TypeAdapter(ExclusionBreakdown),
    "extraction_agreement": TypeAdapter(ExtractionAgreement),
    "meta_analysis": TypeAdapter(MetaAnalysisResult),
    "risk_of_bias": TypeAdapter(dict[str, RoBAssessment]),
}

_DECISION_ADAPTER: TypeAdapter[HumanDecision] = TypeAdapter(HumanDecision)
_RUN_INFO_ADAPTER: TypeAdapter[RunInfo] = TypeAdapter(RunInfo)


class RunArtifacts:
    """Artefactos de una corrida, cargados bajo demanda y una sola vez."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self._cache: dict[tuple[str, str], Loaded[Any]] = {}

    def _memo(self, kind: str, rel: str, load: Any) -> Loaded[Any]:
        key = (kind, rel)
        if key not in self._cache:
            self._cache[key] = load()
        return self._cache[key]

    def exists(self, rel: str) -> bool:
        return (self.run_dir / rel).exists()

    def text(self, rel: str) -> Loaded[str]:
        return self._memo("text", rel, lambda: read_text(self.run_dir, rel))

    def json(self, rel: str) -> Loaded[Any]:
        return self._memo("json", rel, lambda: read_json(self.run_dir, rel))

    def yaml(self, rel: str) -> Loaded[Any]:
        return self._memo("yaml", rel, lambda: read_yaml(self.run_dir, rel))

    def jsonl(self, rel: str) -> Loaded[list[tuple[int, Any]]]:
        return self._memo("jsonl", rel, lambda: read_jsonl(self.run_dir, rel))

    def artifact(self, rel: str) -> Loaded[Any]:
        """Artefacto JSON de :data:`ARTIFACT_ADAPTERS`, validado contra su modelo."""
        return self._memo("model", rel, lambda: validate(self.json(rel), ARTIFACT_ADAPTERS[rel]))

    def decision(self, gate: str) -> Loaded[HumanDecision]:
        """``<gate>/decision.yml`` validado como ``HumanDecision``."""
        rel = f"{gate}/decision.yml"
        return self._memo("decision", rel, lambda: validate(self.yaml(rel), _DECISION_ADAPTER))

    def run_info(self) -> Loaded[RunInfo]:
        """``run.json`` validado (ausente en corridas anteriores a la Ola 1)."""
        return self._memo(
            "run_info", "run.json", lambda: validate(self.json("run.json"), _RUN_INFO_ADAPTER)
        )


def load_run(run_dir: str | Path) -> RunArtifacts:
    """Prepara la carga de los artefactos de ``run_dir`` (nada se lee todavía)."""
    return RunArtifacts(Path(run_dir))


@dataclass(frozen=True)
class LedgerView:
    """El ledger validado línea a línea.

    Attributes:
        present: ``decisions_ledger.jsonl`` existe.
        entries: ``(número de línea, entrada)`` de las líneas válidas.
        errors: una por línea que no es JSON o no valida ``DecisionEntry``.
        read_error: el fichero no se pudo leer entero.
    """

    present: bool
    entries: tuple[tuple[int, DecisionEntry], ...]
    errors: tuple[str, ...]
    read_error: str | None

    @property
    def usable(self) -> bool:
        """Se lee entero, sin líneas corruptas y con al menos una entrada."""
        return self.present and not self.read_error and not self.errors and bool(self.entries)

    @property
    def decisions(self) -> list[DecisionEntry]:
        return [entry for _, entry in self.entries]


_DECISION_ENTRY = TypeAdapter(DecisionEntry)


class AuditContext:
    """Lo que comparten los checks de una corrida, calculado una vez."""

    def __init__(self, artifacts: RunArtifacts) -> None:
        self.art = artifacts
        self.run_dir = artifacts.run_dir
        self._sections: dict[str, Loaded[Any]] = {}

    @cached_property
    def manifest(self) -> Loaded[Any]:
        return self.art.yaml("manifest.yml")

    @cached_property
    def manifest_dict(self) -> dict[str, Any] | None:
        """El manifiesto si se pudo leer y su raíz es un mapa."""
        return self.manifest.value if self.manifest.ok else None

    def manifest_section(self, key: str) -> Loaded[Any]:
        """Sección ``key`` de :data:`MANIFEST_ADAPTERS`, validada.

        ``present`` es ``False`` si el manifiesto no se pudo leer o no tiene esa
        clave.
        """
        if key not in self._sections:
            rel = f"manifest.yml#{key}"
            manifest = self.manifest_dict or {}
            if key not in manifest:
                self._sections[key] = Loaded(rel, False)
            else:
                raw = Loaded(rel, True, manifest[key])
                self._sections[key] = validate(raw, MANIFEST_ADAPTERS[key])
        return self._sections[key]

    @cached_property
    def llm_calls(self) -> list[dict[str, Any]]:
        """Las llamadas del manifiesto que son mapas (las demás las marca ``schemas``)."""
        calls = (self.manifest_dict or {}).get("llm_calls")
        return [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []

    @cached_property
    def ledger(self) -> LedgerView:
        raw = self.art.jsonl("decisions_ledger.jsonl")
        if not raw.present or raw.value is None:
            return LedgerView(raw.present, (), (), raw.error)
        entries: list[tuple[int, DecisionEntry]] = []
        # `split("\n")` y no `splitlines()` (U+2028…, como en `read_jsonl`); sin error, `[]`.
        errors = raw.error.split("\n") if raw.error else []
        for number, obj in raw.value:
            try:
                entries.append((number, _DECISION_ENTRY.validate_python(obj)))
            except ValidationError as exc:
                errors.append(f"línea {number}: {format_validation(exc, limit=2)}")
        return LedgerView(True, tuple(entries), tuple(errors), None)

    @cached_property
    def gates(self) -> dict[str, GateSummary]:
        """Decisión efectiva por etapa (el reductor único del ledger, D12)."""
        return summarize_gates(self.ledger.decisions)

    @cached_property
    def requests(self) -> frozenset[str]:
        """Gates con ``review_request.yml`` en disco."""
        return frozenset(
            g for g in GATED_STAGES if (self.run_dir / g / "review_request.yml").is_file()
        )

    @cached_property
    def run_info(self) -> RunInfo | None:
        loaded = self.art.run_info()
        return loaded.value if loaded.ok else None

    @cached_property
    def state(self) -> RunState:
        """Estado deducido; ante un error interno, ``unknown`` (se exige todo)."""
        try:
            return derive_state(
                run_info=self.run_info,
                gates=self.gates,
                requests=self.requests,
                ledger_ok=self.ledger.usable,
            )
        except Exception:  # fail-closed: un error propio nunca relaja la auditoría
            return RunState("unknown", frozenset(STAGES))

    @cached_property
    def protocol(self) -> ReviewProtocol | None:
        """El protocolo tal como lo registró el manifiesto (``None`` si no valida)."""
        loaded = self.manifest_section("protocol")
        return loaded.value if loaded.ok else None
