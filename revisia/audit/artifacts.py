"""Carga robusta de los artefactos de una corrida (spec 2026-10-04 §9.1).

Los loaders **nunca lanzan**: devuelven un :class:`Loaded` con el valor o con
el error (``OSError``, ``UnicodeDecodeError``, JSON/YAML inválido, raíz de tipo
inesperado, ``ValidationError``, ``RecursionError``, YAML demasiado anidado y
cualquier otra excepción del parser). Antes de la Ola 1 un
``manifest.yml`` con raíz de lista reventaba el auditor con ``AttributeError``
y una línea corrupta del ledger se descartaba en silencio (auditoría
2026-09-03, A11/C3): un auditor que revienta o que ignora lo ilegible no
verifica nada. «Nunca lanzan» incluye lo que ningún ``except`` atrapa: un YAML
con miles de niveles de anidamiento desborda la pila nativa de ``CSafeLoader`` y
mata el proceso sin informe, así que se rechaza antes de cargarlo (revisión de
la Tarea 4).

``AuditContext`` reúne lo que los checks comparten (manifiesto, ledger,
decisiones efectivas, estado, protocolo) y lo calcula una sola vez.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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

# Guarda contra el anidamiento hostil. `CSafeLoader` compone los nodos con recursión
# nativa de C, que `sys.setrecursionlimit` no limita: medido en Windows con Python
# 3.13, a ~2 700 niveles (igual con `[`, con `- ` encadenados y con sangría de un
# espacio por nivel) desborda la pila (0xC00000FD) y mata el proceso sin que ningún
# `except` lo atrape. Los manifiestos reales tienen profundidad < 20, de modo que
# los límites van con holgura y rechazan sin cargar. Se aplican también con el
# `SafeLoader` de Python puro para que el veredicto no dependa de tener libyaml.
_YAML_MAX_FLOW_DEPTH = 500  # niveles netos de `[`/`{` fuera de comillas y comentarios
_YAML_MAX_INDENT = 2000  # espacios de sangría de una línea
_YAML_MAX_BLOCK_CHAIN = 500  # indicadores `- `/`? `/`: ` encadenados al inicio de una línea

# Comillas (dobles o simples) y comentarios se consumen enteros: los corchetes que
# contienen no abren niveles. Es una aproximación a la gramática de YAML (ignora
# los escapes `\"` y las comillas multilínea), suficiente para una guarda; una
# comilla suelta sin pareja en su línea no casa, así que el escaneo es lineal.
_YAML_FLOW_TOKEN = re.compile(r""""[^"\n]*"|'[^'\n]*'|(?<![^\s])#[^\n]*|[\[\]{}]""")
_YAML_DEEP_INDENT = re.compile(rf"^ {{{_YAML_MAX_INDENT + 1},}}[^ \r\n]", re.MULTILINE)
_YAML_DEEP_CHAIN = re.compile(rf"^ *(?:[-?:][ \t]+){{{_YAML_MAX_BLOCK_CHAIN + 1},}}", re.MULTILINE)


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


def format_validation(exc: ValidationError, *, limit: int = 3) -> str:
    """``loc: msg; loc: msg (+k más)`` a partir de una ``ValidationError``."""
    errors = exc.errors()
    parts = [
        f"{'.'.join(str(p) for p in err['loc']) or '(raíz)'}: {err['msg']}"
        for err in errors[:limit]
    ]
    if len(errors) > limit:
        parts.append(f"+{len(errors) - limit} más")
    return "; ".join(parts)


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


def _yaml_nesting_problem(text: str) -> str | None:
    """Por qué el YAML se rechaza sin cargarlo, o ``None`` si pasa la guarda.

    Ver las constantes ``_YAML_MAX_*``: el desbordamiento de pila de
    ``CSafeLoader`` no se puede atrapar, así que se previene con una pasada
    barata sobre el texto (lineal; sin cargar nada).
    """
    if _YAML_DEEP_INDENT.search(text):
        return f"una línea con más de {_YAML_MAX_INDENT} espacios de sangría"
    if _YAML_DEEP_CHAIN.search(text):
        return f"más de {_YAML_MAX_BLOCK_CHAIN} indicadores `- `/`? ` encadenados en una línea"
    # `count` es de C y acota la profundidad: casi todo manifiesto se libra del escaneo.
    if text.count("[") + text.count("{") > _YAML_MAX_FLOW_DEPTH:
        depth = 0
        for token in _YAML_FLOW_TOKEN.finditer(text):
            char = token.group()
            if char in "[{":
                depth += 1
                if depth > _YAML_MAX_FLOW_DEPTH:
                    return f"más de {_YAML_MAX_FLOW_DEPTH} niveles de `[`/`{{`"
            elif char in "]}":
                depth = max(0, depth - 1)
    return None


def read_yaml(run_dir: Path, rel: str, *, root: type | tuple[type, ...] = dict) -> Loaded[Any]:
    """Lee un YAML (``CSafeLoader`` si está disponible) y comprueba su raíz.

    Un YAML con miles de niveles de anidamiento se rechaza antes de cargarlo:
    desbordaría la pila nativa del loader en C y mataría el proceso (revisión
    de la Tarea 4). PyYAML tampoco lanza solo ``YAMLError``: una etiqueta
    explícita como ``!!timestamp foo`` o ``!!bool maybe`` produce
    ``AttributeError``/``KeyError``, por eso se captura ``Exception``.
    """
    text = read_text(run_dir, rel)
    if not text.ok:
        return Loaded(rel, text.present, error=text.error)
    problem = _yaml_nesting_problem(text.value)
    if problem:
        return Loaded(
            rel,
            True,
            error=f"estructura YAML demasiado anidada ({problem}); no se carga para no "
            "desbordar la pila del intérprete",
        )
    try:
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
        errors = (raw.error or "").splitlines()
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
