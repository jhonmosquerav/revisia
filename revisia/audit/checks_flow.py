"""Checks del flujo PRISMA: ``stage_artifacts``, ``arithmetic``, ``exclusions``, ``deliverable``.

``arithmetic`` verifica las relaciones entre artefactos de la spec 2026-10-04
§4.4 (las que ya se pueden comprobar con lo que hay en disco) más las de §9.3:
la reconstrucción C3 declaraba 120 identificados con 140 llamadas para 120
registros cribados por dos modelos, y el auditor anterior no sumaba nada.
Sin ``run.json`` (corrida anterior a la Ola 1) se aplican las relaciones v0.7
del embudo (un ``unclear`` a texto completo contaba como incluido): esa
corrida ya no es publicable (D13), pero el diagnóstico sigue siendo útil.

Los artefactos son entrada no confiable (revisiones de la Tarea 4): ningún check lanza,
cuelga ni vuelca un valor leído de ellos sin acotar. Los conteos y las decisiones llegan
ya validados contra su modelo (``schemas`` informa lo que no valida y aquí queda como
«no verificable»), pero el manifiesto trae valores sin modelo (``models_used``, las
llamadas, las copias de los artefactos) y los números validados pueden ser absurdos (un
entero de 4 000 cifras, una matriz que desborda ``math.sqrt``). Por eso todo valor que
entra en un detalle pasa por ``short_text``/``short_repr``, toda lista que se muestra
va acotada (``_ids``, ``_limitar``) y cada familia de relaciones corre protegida: una
excepción inesperada es una relación rota con su tipo, no un «error interno».

El auditor es fail-closed (revisión de la Tarea 7): cada relación termina verificada, rota (FAIL)
o no verificable (WARN), y ninguna se omite en silencio. Lo que el motor escribe siempre
(``counts``, ``protocol``, ``models_used`` y las copias de exclusiones, RoB y verificación en el
manifiesto, las decisiones, extracciones y evaluaciones, ``agreement.json`` cuando el protocolo
declara un 2.º extractor y hay incluidos) y falta es manipulación, así que la relación queda rota;
lo mismo un CSV PRISMA2020 que existe y no se lee. El WARN se reserva para lo que de verdad no se
puede saber: un valor que no valida y marca ``schemas``, un dato que manifiestos de antes de la
Ola 1 pudieron no traer (``excluded_ta_human/ai``, solo sin ``run.json``) y el CSV PRISMA2020
ausente, cuyo FAIL ya da la fila ``deliverable``.

Lo que el motor aún no ha escrito no se exige (``state.py``): ``arithmetic`` y ``deliverable``
solo corren con ``reporte`` alcanzado, y ``exclusions``, que corre desde ``screening_ft``,
exige el manifiesto solo desde entonces (se escribe al evaluar el gate final). Tampoco se exige lo
que el motor crea al primer uso: con 0 registros tras la deduplicación no hay diario de T/A ni
llamadas a la IA hasta la síntesis (``_cribado_con_trabajo``).

Un ``llm_calls.jsonl`` que existe y no se puede leer no se sustituye por la copia del manifiesto
(``AuditContext.llm_calls_ilegible``): las relaciones que lo necesitan son no verificables y
``schemas`` da el FAIL.

Con ``run.json`` (corrida de la Ola 1; la rama la decide la presencia del fichero, como en
``stage_artifacts`` y ``deliverable``) ``arithmetic`` aplica las relaciones 1-13 de §4.4 sobre lo
que el motor escribe desde PR-B..PR-D: la búsqueda y el dedup (1, 4), el orden del cribado T/A
(5), los informes buscados (6), la recuperación y los rescates del texto completo (7, 8), la
lista 16b (9), los incluidos (10), el CSV PRISMA2020 (11), los diarios frente a
``llm_calls.jsonl`` (12) y cada consolidado frente a su diario (13), más la matriz de confusión
recalculada desde ``gold.json`` (D6). Las relaciones v0.7 del embudo no se aplican a esas
corridas: con el PRISMA estricto (D2) un no recuperado no se criba con IA ni cuenta como
evaluado salvo que un humano lo rescate, y una corrida legítima sin ningún texto recuperado
incumplía ``excluded_ta + fulltext_assessed == screened`` y ``len(decisions FT) ==
fulltext_assessed`` (Tarea 14).

Los diarios se leen con el lector del auditor (``RunArtifacts.jsonl``/``jsonl_models``), que
nunca toca el fichero: ``orchestration.journal.read_jsonl`` recorta una última línea truncada al
leer, y un auditor no puede reparar lo que audita. La relación 12 es de inclusión y no de
igualdad de totales: cada meta de cada línea está, idéntica, en ``llm_calls.jsonl``, pero
``llm_calls.jsonl`` puede tener llamadas que ningún diario cita (huérfanas de una caída, válidas
según §4.3) y le pueden faltar llamadas pagadas que no llegaron a registrarse (el miembro
anterior del ensemble T/A cuando el siguiente falla a mitad del registro, o el juez de grounding
cuando la verificación se cae a medias: el registro se recalcula entero al reanudar y su línea de
diario lleva las metas completas). Contar totales daría FAIL a corridas legítimas reanudadas; la
cota inferior de llamadas (§9.3) sigue delatando decisiones sin las llamadas que las produjeron.
Inclusión no es reutilización: cada línea de ``llm_calls.jsonl`` respalda como mucho una posición
de meta en todos los diarios (si no, una meta copiada taparía la llamada que falta) y los
miembros de una línea de T/A tienen roles distintos.

El gold del protocolo (``00_protocol/gold.yml``, la instantánea) ancla las métricas: si no está
vacío, el motor escribe ``03_screening/gold.json`` (con esas claves como mínimo; ``gold_labels=``
solo cambia valores o añade ids, D6) y ``metrics.json``, así que borrarlos no puede ser la forma de
no recalcular un recall bajo el umbral (D7).

Los efectos del protocolo (``00_protocol/effects.yml``) anclan igual el meta-análisis (revisión
final de la Ola 1, E1): con efectos declarados, ``08_meta/meta_analysis.json``, su copia en el
manifiesto, ``deliverable/meta_analisis.md`` y ``interop/effects_metafor.csv`` son obligatorios,
el resultado se recalcula con ``meta_analyze`` sobre esos efectos, ``meta_analisis.md`` y el CSV de
metafor son lo que el motor renderiza de ese cálculo y el CSV PRISMA2020 declara ``k`` estudios en
el meta-análisis. Antes, borrar los cuatro o multiplicar la estimación dejaba la corrida APTA. Sin
efectos, un meta-análisis en disco es inventado. Si ``effects.yml`` existe pero el auditor no lo lee
(``<<``, YAML roto, no valida como lo valida el motor), la relación está rota: el motor valida el
fichero antes de empezar, así que esa instantánea no la escribió él.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import weakref
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from revisia.audit.artifacts import (
    LLM_CALLS_ILEGIBLE,
    NA_MANIFIESTO,
    AuditContext,
    short_repr,
    short_text,
)
from revisia.audit.model import Verdict
from revisia.config import STAGES, ReviewProtocol
from revisia.exclusions import compute_exclusion_breakdown, compute_ft_excluded
from revisia.exports import (
    PrismaCounts,
    render_flow_diagram,
    render_flow_markdown,
    render_forest_markdown,
    render_metafor_csv,
)
from revisia.extraction_agreement import select_double_extraction_subset
from revisia.llm.ensemble import recall_biased_label
from revisia.meta_analysis import MetaAnalysisResult, meta_analyze
from revisia.metrics import confusion, kappa_from_matrix, mcc, wmcc
from revisia.orchestration.snapshot import SNAPSHOT_DIR
from revisia.protocol_files import EffectsFile
from revisia.provenance.runmeta import sha256_text
from revisia.schemas.artifacts import JOURNAL_PATHS, TRANSIENT_FULLTEXT_REASONS, JournalEntry
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision
from revisia.schemas.verification import VerificationReport

TA = "03_screening/decisions.json"
FT = "04_fulltext/decisions.json"
CSV = "deliverable/interop/prisma2020_flow.csv"
EXTRACTIONS = "05_extraction/extractions.json"
ASSESSMENTS = "07_rob/assessments.json"
AGREEMENT = "05_extraction/agreement.json"
EXCLUSIONS = "03_screening/exclusions.json"
RETRIEVAL = "04_fulltext/retrieval.json"
SEARCH_RECORDS = "01_search/records.json"
DEDUP_REPORT = "02_dedup/dedup.json"
EXCLUDED = "04_fulltext/excluded.json"
GOLD = "03_screening/gold.json"
GOLD_PROTOCOLO = f"{SNAPSHOT_DIR}/gold.yml"
GOLD_Y_METRICAS = "§9.3 · metrics.json junto a gold.json"
METRICS = "03_screening/metrics.json"
VERIFICATION = "06_synthesis/verification.json"
DOCUMENTO = "deliverable/documento.md"
EFECTOS_PROTOCOLO = f"{SNAPSHOT_DIR}/effects.yml"
META = "08_meta/meta_analysis.json"
META_MD = "deliverable/meta_analisis.md"
METAFOR_CSV = "deliverable/interop/effects_metafor.csv"
PRISMA_FLOW = "deliverable/prisma_flow.md"
TEXTOS = "04_fulltext/texts"
# Campos del resultado del meta-análisis que dependen de si `scipy` está instalado (p-valores
# exactos o aproximados): el auditor puede correr en otro entorno que el motor y no los compara.
_META_SEGUN_ENTORNO = {"p_value", "p_method"}

# Campos que el humano (o el gate) añade a una decisión de cribado: el diario guarda la propuesta
# de la IA sin ellos y el consolidado se compara con él quitándolos (relación 13 de §4.4).
_CAMPOS_HUMANOS = ("human_label", "final_label", "human_reason", "human_actor")
# Etiquetas finales de T/A con las que un registro pasa a texto completo (sesgo a recall).
_PASAN_TA = frozenset({"include", "unclear"})

_MAX = 6  # relaciones, ficheros o artefactos que se listan en un detalle
_MAX_IDS = 3  # ids de registro que se listan dentro de una relación
_LIMITE_ITEM = 240  # caracteres de una relación rota o no verificable en el detalle
_LIMITE_ID = 60  # caracteres de un id, un nombre de modelo o una celda del CSV
_LIMITE_NUMERO = 40  # caracteres de un número del manifiesto (un entero puede tener 4 000 cifras)
_LIMITE_ERROR = 100  # caracteres del motivo de un artefacto que no se pudo cargar

# Artefactos que toda etapa alcanzada deja en disco (spec §4.2; los de la Ola 1
# llegan con PR-B..PR-D).
STAGE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "screening_ta": (TA,),
    "screening_ft": (FT, EXCLUSIONS),
    "extraccion": (EXTRACTIONS,),
    "rob": (ASSESSMENTS,),
    "sintesis": ("06_synthesis/verification.json",),
    "reporte": ("manifest.yml",),
}
# Artefactos de la Ola 1 (spec §4.2): solo se exigen con run.json. Los diarios que dependen de que
# la etapa tuviera trabajo no están aquí sino en `_journals_ola1`: el de la recuperación
# (`04_fulltext/retrieval.jsonl`; el motor no escribe en él los fallos transitorios, así que una
# corrida cuyas recuperaciones fallaron todas por la red no lo tiene) y el de T/A con
# `llm_calls.jsonl` (el motor los crea al cribar el primer registro y con 0 registros no existen).
STAGE_ARTIFACTS_OLA1: dict[str, tuple[str, ...]] = {
    "protocolo": ("run.json", "00_protocol/protocol.yml"),
    "busqueda": ("01_search/records.json", "01_search/log.json"),
    "dedup": ("02_dedup/records.json", "02_dedup/dedup.json"),
    "screening_ft": (RETRIEVAL, "04_fulltext/excluded.json"),
    "sintesis": ("06_synthesis/journal.jsonl", "06_synthesis/verification.jsonl"),
}
SCREENING_JOURNAL = "03_screening/journal.jsonl"
LLM_CALLS = "llm_calls.jsonl"
DEDUP_RECORDS = "02_dedup/records.json"
RETRIEVAL_JOURNAL = "04_fulltext/retrieval.jsonl"
# Artefactos que existen si el manifiesto registra su copia.
CONDITIONAL_ARTIFACTS: dict[str, tuple[str, str]] = {
    "screening_metrics": ("screening_ta", "03_screening/metrics.json"),
    "extraction_agreement": ("extraccion", AGREEMENT),
    "meta_analysis": ("rob", "08_meta/meta_analysis.json"),
}
# Copias del manifiesto que deben coincidir con su fichero (§9.3).
MANIFEST_COPIES: dict[str, str] = {
    "exclusions": EXCLUSIONS,
    "screening_metrics": "03_screening/metrics.json",
    "verification": "06_synthesis/verification.json",
    "risk_of_bias": ASSESSMENTS,
    "extraction_agreement": AGREEMENT,
    "meta_analysis": "08_meta/meta_analysis.json",
}
# De esas copias, las que el motor escribe en toda corrida (el resto depende del gold, de la
# doble extracción declarada o de que el protocolo aporte ``effects.yml``).
COPIAS_SIEMPRE_ESCRITAS: tuple[str, ...] = ("exclusions", "risk_of_bias", "verification")

DELIVERABLE_FILES: tuple[str, ...] = (
    "documento.md",
    "prisma_flow.md",
    "metodologia.md",
    "tabla_extraccion.md",
    "risk_of_bias.md",
    "referencias.bib",
    "checklist_2020.md",
    "checklist_traice.md",
    "checklist_s.md",
    "checklist_abstracts.md",
    "interop/prisma2020_flow.csv",
)


_SUFIJO_MAS = re.compile(r" \(\+\d+ más\)")


def _repartir(largos: Sequence[int], total: int) -> list[int]:
    """Reparte ``total`` caracteres entre tramos de esos ``largos``, por igual.

    Cada tramo recibe lo que necesita hasta su parte igual; lo que no usan los cortos pasa a los
    largos, así que ninguno se queda sin sitio mientras otro lo acapara.
    """
    cuotas = [0] * len(largos)
    restante = total
    orden = sorted(range(len(largos)), key=largos.__getitem__)
    for puesto, i in enumerate(orden):
        cuotas[i] = min(largos[i], restante // (len(orden) - puesto))
        restante -= cuotas[i]
    return cuotas


def _acotar_item(item: str) -> str:
    """``item`` recortado a ``_LIMITE_ITEM`` sin partir los ``(+k más)`` que ``_ids`` dejó dentro.

    Cortar a ciegas daba «…, rrr… (+4 …»: el lector no sabía cuántos ids faltaban (revisión de la
    Tarea 7). Una relación puede llevar varios sufijos (los ids con voto distinto y los screeners
    configurados): se conservan todos enteros y solo se recortan los tramos de texto libre entre
    ellos, repartiendo el espacio entre los tramos (un tramo largo no deja sin sitio a los demás).
    """
    sufijos = list(_SUFIJO_MAS.finditer(item)) if len(item) > _LIMITE_ITEM else []
    fijo = sum(len(s.group()) for s in sufijos)
    if not sufijos or fijo > _LIMITE_ITEM // 2:  # sin sufijos (o texto hostil lleno de ellos)
        return short_text(item, limit=_LIMITE_ITEM)
    libres: list[str] = []
    inicio = 0
    for sufijo in sufijos:
        libres.append(item[inicio : sufijo.start()])
        inicio = sufijo.end()
    libres.append(item[inicio:])
    cuotas = _repartir([len(tramo) for tramo in libres], _LIMITE_ITEM - fijo)
    partes: list[str] = []
    for i, tramo in enumerate(libres):
        partes.append(short_text(tramo, limit=cuotas[i]) if cuotas[i] > 0 else "")
        if i < len(sufijos):
            partes.append(sufijos[i].group())
    return "".join(partes)


def _limitar(items: list[str]) -> str:
    """Hasta ``_MAX`` elementos, cada uno acotado, y cuántos más hay."""
    more = len(items) - _MAX
    shown = "; ".join(_acotar_item(item) for item in items[:_MAX])
    return shown + (f" (+{more} más)" if more > 0 else "")


def _ids(items: Sequence[object]) -> str:
    """Los primeros ``_MAX_IDS`` ids, cada uno acotado, y cuántos más hay."""
    more = len(items) - _MAX_IDS
    shown = ", ".join(short_text(item, limit=_LIMITE_ID) for item in items[:_MAX_IDS])
    return shown + (f" (+{more} más)" if more > 0 else "")


def _valor(value: object) -> str:
    """Un valor leído de un artefacto, para un detalle: ``repr`` acotado en coste y longitud."""
    return short_repr(value, limit=_LIMITE_NUMERO + _LIMITE_ID)


def _n(value: object) -> str:
    """Un número del manifiesto, para un detalle (un ``int`` puede tener miles de cifras)."""
    return short_repr(value, limit=_LIMITE_NUMERO)


def _primera_diferencia(actual: Sequence[str], esperado: Sequence[str]) -> str:
    """Dónde difieren dos secuencias de ids, acotado: la primera posición distinta y los largos.

    Un ``repr`` de las dos listas enteras no dice dónde está el problema y, con miles de ids, el
    recorte de ``_valor`` lo esconde.
    """
    largos = f"{len(actual)} frente a {len(esperado)} ids"
    for i, (a, b) in enumerate(zip(actual, esperado, strict=False)):
        if a != b:
            return (
                f"posición {i}: {short_text(a, limit=_LIMITE_ID)} ≠ "
                f"{short_text(b, limit=_LIMITE_ID)} ({largos})"
            )
    return largos


def _misma_secuencia(
    rel: _Relations, name: str, actual: Sequence[str], esperado: Sequence[str]
) -> None:
    """Relación ``actual == esperado`` (mismos ids, mismo orden) con un detalle legible."""
    iguales = list(actual) == list(esperado)
    rel.check(name, iguales, "" if iguales else _primera_diferencia(actual, esperado))


def _ola1(ctx: AuditContext) -> bool:
    """La corrida es de la Ola 1: tiene ``run.json`` (aunque no valide; eso lo marca ``schemas``).

    Decide la rama por la presencia del fichero, como ``stage_artifacts`` y ``deliverable``: un
    ``run.json`` presente e inválido no convierte la corrida en una v0.7, cuyas relaciones darían
    FAIL falsos sobre los artefactos de la Ola 1.
    """
    return ctx.art.exists("run.json")


def _ids_incluidos(ft: Sequence[ScreeningDecision], *, ola1: bool) -> list[str]:
    """Ids incluidos en unas decisiones a texto completo ya cargadas (ver :func:`included_ids`)."""
    labels = {"include"} if ola1 else _PASAN_TA
    return [d.record_id for d in ft if d.final_label in labels]


def included_ids(ctx: AuditContext) -> list[str] | None:
    """Incluidos según las decisiones a texto completo (``None`` si no se leen).

    Desde la Ola 1 (con ``run.json``), ``final_label == include``: un ``unclear`` lo resuelve un
    humano (D1) y nunca llega a extracción. Relaciones v0.7 (sin ``run.json``): ``include`` o
    ``unclear``, que es lo que aquel motor extraía.
    """
    ft = ctx.art.artifact(FT)
    return _ids_incluidos(ft.value, ola1=_ola1(ctx)) if ft.ok else None


def _requiere_doble_extraccion(ctx: AuditContext) -> bool:
    """El protocolo declara un 2.º extractor y hay (o puede haber) incluidos.

    Entonces el motor escribe siempre ``05_extraction/agreement.json`` y su copia en el
    manifiesto (pipeline: ``second_extractors and included``): que falten es manipulación, no
    una opción. Si las decisiones a texto completo no se leen, se supone que hay incluidos
    (fail-closed; esa ausencia ya la marcan otras filas).
    """
    protocol = ctx.protocol
    if protocol is None or not protocol.ensemble_llm.get("extraccion"):
        return False
    ids = included_ids(ctx)
    return ids is None or bool(ids)


def _recuperacion_con_diario(ctx: AuditContext) -> bool:
    """La recuperación de texto completo debe haber dejado diario.

    El motor escribe en ``04_fulltext/retrieval.jsonl`` los resultados definitivos (un texto
    recuperado o un fallo permanente) y no los transitorios (``TRANSIENT_FULLTEXT_REASONS``,
    que se reintentan al reanudar). Sin ningún resultado definitivo no hay diario. Si
    ``retrieval.json`` no se lee no se puede saber, y se exige (fail-closed).
    """
    retrieval = ctx.art.artifact(RETRIEVAL)
    if not retrieval.ok:
        return True
    return any(row.reason not in TRANSIENT_FULLTEXT_REASONS for row in retrieval.value)


def _cribado_con_trabajo(ctx: AuditContext) -> bool:
    """El cribado T/A tuvo algún registro que cribar (o no se puede saber que no).

    El motor crea el diario de T/A al cribar el primer registro y la primera llamada a la IA la
    registra ahí mismo: con 0 registros tras la deduplicación («0 estudios incluidos») no se
    cribó nada y no existe ninguno de los dos. Si ``02_dedup/records.json`` no se carga (falta,
    es ilegible o no valida) se supone que hubo registros (fail-closed; ``schemas`` y ``dedup``
    marcan el fichero).
    """
    dedup = ctx.art.artifact(DEDUP_RECORDS)
    return not dedup.ok or bool(dedup.value)


@dataclass(frozen=True)
class _GoldProtocolo:
    """El gold humano de la instantánea del protocolo (``00_protocol/gold.yml``).

    Attributes:
        claves: los ids etiquetados, como quedan en ``gold.json`` (cadenas JSON). Vacío si el
            protocolo no trae gold (sin fichero, fichero sin etiquetas, o ilegible).
        problema: por qué no se pudo leer un fichero que existe (acotado): entonces no se sabe
            si el motor escribió ``gold.json``.
    """

    claves: frozenset[str] = frozenset()
    problema: str = ""


def _gold_del_protocolo(ctx: AuditContext) -> _GoldProtocolo:
    """Los ids del gold de la instantánea, leídos como los lee el motor.

    ``protocol_files.GoldFile``: ``data.get("gold", data)`` (el mapa puede ir en la raíz o bajo
    ``gold``) y un documento vacío o sin etiquetas es «sin gold». Es el gold del *protocolo*: las
    etiquetas que se pasan por código (``gold_labels=``, D6) las suma el motor en ``gold.json``,
    que por eso puede traer más ids y otros valores pero nunca menos ids.
    """
    cargado = ctx.art.yaml_o_vacio(GOLD_PROTOCOLO)
    if not cargado.present:
        return _GoldProtocolo()
    if not cargado.ok:
        motivo = short_text(cargado.error, limit=_LIMITE_ERROR)
        return _GoldProtocolo(problema=f"{GOLD_PROTOCOLO} ilegible ({motivo})")
    datos = cargado.value or {}
    etiquetas = datos.get("gold", datos) or {}
    if not isinstance(etiquetas, dict):
        return _GoldProtocolo(problema=f"{GOLD_PROTOCOLO} no es un mapa de etiquetas")
    try:
        # Las claves que `gold.json` guarda: un id numérico o booleano pasa por JSON como cadena.
        claves = frozenset(json.loads(json.dumps(dict.fromkeys(etiquetas, True))))
    except (TypeError, ValueError):
        return _GoldProtocolo(problema=f"{GOLD_PROTOCOLO} con ids que JSON no puede guardar")
    return _GoldProtocolo(claves)


@dataclass(frozen=True)
class _EfectosProtocolo:
    """Los efectos del meta-análisis de la instantánea (``00_protocol/effects.yml``).

    Attributes:
        efectos: los efectos validados como los valida el motor (``EffectsFile``), o ``None`` si
            el protocolo no declara ninguno (sin fichero, o ``effects`` vacío) o no se pudo leer.
        resultado: ``meta_analyze`` de esos efectos, el que el motor tuvo que escribir.
        problema: por qué un fichero que existe no se pudo leer o no valida (acotado).
        calculo: el mismo ``meta_analyze`` como modelo, el que el motor pasa a los renders de
            ``meta_analisis.md`` y ``effects_metafor.csv``.
    """

    efectos: EffectsFile | None = None
    resultado: dict[str, Any] | None = None
    problema: str = ""
    calculo: MetaAnalysisResult | None = None


# Los efectos ya leídos de cada contexto: los consultan `stage_artifacts`, `deliverable` y tres
# familias de `arithmetic`, y validarlos recalcula el meta-análisis (sin `scipy`, cada cálculo
# reintenta importarlo). Débil: muere con el contexto de la auditoría.
_EFECTOS_LEIDOS: weakref.WeakKeyDictionary[AuditContext, _EfectosProtocolo] = (
    weakref.WeakKeyDictionary()
)


def _efectos_del_protocolo(ctx: AuditContext) -> _EfectosProtocolo:
    """Los efectos de la instantánea, leídos y validados como los lee el motor (E1).

    ``protocol_files.EffectsFile`` es el mismo modelo con el que el motor valida el fichero al
    cargar el protocolo (k ≥ 2, datos de la medida, varianza positiva): el auditor no puede dar
    por bueno un ``effects.yml`` que el motor habría rechazado. Solo con ``run.json``: sin
    instantánea (una corrida v0.7) no hay protocolo congelado con el que anclar nada. Se calcula
    una vez por contexto.
    """
    leidos = _EFECTOS_LEIDOS.get(ctx)
    if leidos is None:
        leidos = _EFECTOS_LEIDOS[ctx] = _leer_efectos_del_protocolo(ctx)
    return leidos


def _leer_efectos_del_protocolo(ctx: AuditContext) -> _EfectosProtocolo:
    """Cuerpo de :func:`_efectos_del_protocolo` (sin memoizar)."""
    if not _ola1(ctx):
        return _EfectosProtocolo()
    cargado = ctx.art.yaml_o_vacio(EFECTOS_PROTOCOLO)
    if not cargado.present:
        return _EfectosProtocolo()
    if not cargado.ok:
        motivo = short_text(cargado.error, limit=_LIMITE_ERROR)
        return _EfectosProtocolo(problema=f"{EFECTOS_PROTOCOLO} ilegible ({motivo})")
    try:
        efectos = EffectsFile.model_validate(cargado.value)
    except ValueError as exc:  # `ValidationError` es un `ValueError`
        # Solo el tipo: el mensaje de pydantic citaría el valor hostil.
        return _EfectosProtocolo(
            problema=f"{EFECTOS_PROTOCOLO} no valida como lo valida el motor ({type(exc).__name__})"
        )
    if not efectos.effects:
        return _EfectosProtocolo()
    calculo = meta_analyze(efectos.effects, efectos.measure)
    return _EfectosProtocolo(efectos, calculo.model_dump(), calculo=calculo)


def _journals_ola1(ctx: AuditContext) -> list[tuple[str, str]]:
    """Diarios y llamadas que existen si su etapa tuvo trabajo: el cribado T/A con algún
    registro (su diario y ``llm_calls.jsonl``), la recuperación con algún resultado definitivo,
    FT con algún recuperado, extracción y RoB con algún incluido, 2.º extractor con doble
    extracción.

    ``llm_calls.jsonl`` existe una vez que hubo una llamada a la IA: con registros la hace el
    cribado y sin ellos la primera es la síntesis, que el motor siempre hace (se exige entonces
    con la síntesis alcanzada).
    """
    required: list[tuple[str, str]] = []
    reached = ctx.state.reached
    if "screening_ta" in reached and _cribado_con_trabajo(ctx):
        required += [("screening_ta", SCREENING_JOURNAL), ("screening_ta", LLM_CALLS)]
    elif "sintesis" in reached:
        required.append(("sintesis", LLM_CALLS))
    ft = ctx.art.artifact(FT)
    if "screening_ft" in reached:
        if _recuperacion_con_diario(ctx):
            required.append(("screening_ft", RETRIEVAL_JOURNAL))
        if ft.ok and any(d.votes for d in ft.value):
            required.append(("screening_ft", "04_fulltext/journal.jsonl"))
    extractions = ctx.art.artifact(EXTRACTIONS)
    if extractions.ok and extractions.value:
        if "extraccion" in reached:
            required.append(("extraccion", "05_extraction/journal.jsonl"))
        if "rob" in reached:
            required.append(("rob", "07_rob/journal.jsonl"))
    if "extraccion" in reached and ctx.art.exists(AGREEMENT):
        required.append(("extraccion", "05_extraction/journal_2.jsonl"))
    return required


def check_stage_artifacts(ctx: AuditContext) -> Verdict:
    """PRISMA 16/27: cada etapa alcanzada dejó sus artefactos (§4.2)."""
    required: list[tuple[str, str]] = []
    for stage, rels in STAGE_ARTIFACTS.items():
        if stage in ctx.state.reached:
            required += [(stage, rel) for rel in rels]
    manifest = ctx.manifest_dict or {}
    for key, (stage, rel) in CONDITIONAL_ARTIFACTS.items():
        if key in manifest and stage in ctx.state.reached:
            required.append((stage, rel))
    # La doble extracción declarada en el protocolo se exige aunque el manifiesto no la registre
    # (quitar la copia no puede ser la forma de quitar el fichero).
    doble = ("extraccion", AGREEMENT)
    if doble[0] in ctx.state.reached and doble not in required and _requiere_doble_extraccion(ctx):
        required.append(doble)
    if ctx.art.exists("run.json"):
        for stage, rels in STAGE_ARTIFACTS_OLA1.items():
            if stage in ctx.state.reached:
                required += [(stage, rel) for rel in rels]
        required += _journals_ola1(ctx)
        # Con gold en la instantánea el motor escribe el gold efectivo y sus métricas (D6): se
        # exigen aunque el manifiesto no registre la copia (quitarla no puede ser la forma de
        # quitar los ficheros).
        if "screening_ta" in ctx.state.reached and _gold_del_protocolo(ctx).claves:
            required += [
                ("screening_ta", rel)
                for rel in (GOLD, METRICS)
                if ("screening_ta", rel) not in required
            ]
        # Con efectos en la instantánea el motor escribe el meta-análisis (en la síntesis) y su
        # entregable (en el reporte): se exigen aunque el manifiesto no registre la copia (E1).
        if _efectos_del_protocolo(ctx).efectos is not None:
            ya = {rel for _, rel in required}
            if "sintesis" in ctx.state.reached and META not in ya:
                required.append(("sintesis", META))
            if "reporte" in ctx.state.reached:
                required += [("reporte", rel) for rel in (META_MD, METAFOR_CSV) if rel not in ya]
    missing = [f"{stage}: {rel}" for stage, rel in required if not ctx.art.exists(rel)]
    if missing:
        return "FAIL", f"faltan artefactos de etapas alcanzadas: {_limitar(missing)}."
    stages = sorted({stage for stage, _ in required}, key=STAGES.index)
    return "PASS", (
        f"{len(required)} artefactos de {len(stages)} etapas alcanzadas presentes "
        f"({', '.join(stages)})."
    )


@dataclass(frozen=True)
class _Relation:
    name: str
    ok: bool | None  # None = no verificable
    detail: str = ""


class _Relations:
    """Acumula relaciones verificadas, rotas y no verificables."""

    def __init__(self) -> None:
        self.items: list[_Relation] = []

    def eq(self, name: str, left: Any, right: Any) -> None:
        self.items.append(_Relation(name, bool(left == right), f"{_valor(left)} ≠ {_valor(right)}"))

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.items.append(_Relation(name, ok, detail))

    def unverifiable(self, name: str, why: str) -> None:
        self.items.append(_Relation(name, None, why))

    def ausente(self, name: str, que: str) -> None:
        """Falta algo que el motor escribe siempre: es manipulación (rota), no incertidumbre.

        «No verificable» queda para lo que de verdad no se puede saber: un valor que no valida
        (la fila ``schemas`` lo marca) o un dato que corridas antiguas pudieron no traer.
        """
        self.check(name, False, f"{que} (el motor siempre lo escribe)")

    def guard(self, family: str, fn: Callable[[], None]) -> None:
        """Corre una familia de relaciones: lo inesperado es una relación rota, no una excepción.

        Los valores de los artefactos pueden ser absurdos aunque validen su modelo, y ``arithmetic``
        no puede dejar de dar una fila (``_run_one`` lo convertiría en «error interno» sin la
        relación que falló). Se informa solo el tipo de la excepción: su mensaje podría llevar el
        valor hostil entero.
        """
        try:
            fn()
        except Exception as exc:  # fail-closed: una relación que no se pudo calcular no se cumple
            self.check(family, False, f"no se pudo calcular ({type(exc).__name__})")


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, abs_tol=1e-9)


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


@dataclass(frozen=True)
class _Csv:
    """Lo que se pudo leer de ``interop/prisma2020_flow.csv``.

    Attributes:
        values: ``data → n`` si el fichero se leyó como CSV.
        ausente: el fichero no existe (la fila ``deliverable`` ya lo marca).
        problema: por qué un fichero que existe no se pudo leer (acotado).
    """

    values: dict[str, str] | None = None
    ausente: bool = False
    problema: str = ""


def _read_csv(ctx: AuditContext) -> _Csv:
    loaded = ctx.art.text(CSV)
    if not loaded.present:
        return _Csv(ausente=True)
    if not loaded.ok:
        return _Csv(problema=f"{CSV} ilegible ({short_text(loaded.error, limit=_LIMITE_ERROR)})")
    try:
        rows = list(csv.DictReader(io.StringIO(loaded.value)))
    except (csv.Error, ValueError) as exc:  # p. ej. un campo mayor que `csv.field_size_limit()`
        # Solo el tipo: el mensaje de `csv.Error` puede citar el contenido hostil.
        return _Csv(problema=f"{CSV} no se pudo leer como CSV ({type(exc).__name__})")
    return _Csv(values={row.get("data", ""): row.get("n", "") for row in rows})


def _screeners(protocol: ReviewProtocol | None) -> list[str] | None:
    if protocol is None:
        return None
    try:
        return [f"{c.provider}:{c.model}" for c in protocol.screeners_for("screening_ta")]
    except KeyError:
        return None


def _seccion(ctx: AuditContext, rel: _Relations, key: str, name: str) -> Any | None:
    """La sección ``key`` del manifiesto, o ``None`` tras registrar por qué no sirve para ``name``.

    Ausente es una relación rota (el motor siempre la escribe: un manifiesto sin ``counts`` o sin
    ``protocol`` no puede salir de una corrida); inválida es no verificable (``schemas`` la marca).
    Ninguna relación que dependa de la sección se omite en silencio.
    """
    loaded = ctx.manifest_section(key)
    if loaded.ok:
        return loaded.value
    if not loaded.present:
        rel.ausente(name, f"{key} ausente en el manifiesto")
    else:
        rel.unverifiable(name, f"manifest.{key} inválido (ver `schemas`)")
    return None


def _artefacto(ctx: AuditContext, rel: _Relations, path: str, name: str) -> Any | None:
    """El artefacto ``path`` validado, o ``None`` tras registrar por qué no sirve para ``name``.

    Mismo criterio que :func:`_seccion`: ausente es rota (el motor lo escribe siempre; además lo
    marca ``stage_artifacts``), inválido es no verificable (``schemas``).
    """
    loaded = ctx.art.artifact(path)
    if loaded.ok:
        return loaded.value
    if not loaded.present:
        rel.ausente(name, f"{path} ausente")
    else:
        rel.unverifiable(name, f"{path} inválido (ver `schemas`)")
    return None


def _funnel(ctx: AuditContext, rel: _Relations) -> None:
    counts = _seccion(ctx, rel, "counts", "conteos del embudo")
    if counts is None:
        return
    ola1 = _ola1(ctx)
    rel.eq(
        "1 · Σ identified_by_source == identified",
        sum(counts.identified_by_source.values()),
        counts.identified,
    )
    rel.eq(
        "4 · screened == identified − duplicates_removed − removed_*",
        counts.screened,
        counts.identified
        - counts.duplicates_removed
        - counts.removed_automation
        - counts.removed_other,
    )
    if ola1:
        _conteos_ola1(rel, counts)
    else:
        # v0.7: un `unclear` a texto completo contaba como evaluado e incluido y no había no
        # recuperados. Con el PRISMA estricto (D2) no vale: los no recuperados sin rescate no
        # son evaluados ni excluidos en T/A.
        rel.eq(
            "v0.7 · excluded_ta + fulltext_assessed == screened",
            counts.excluded_ta + counts.fulltext_assessed,
            counts.screened,
        )
    rel.eq(
        "10 · included == fulltext_assessed − excluded_ft",
        counts.included,
        counts.fulltext_assessed - counts.excluded_ft,
    )
    rel.eq(
        "9 · Σ ft_exclusion_reasons == excluded_ft",
        sum(counts.ft_exclusion_reasons.values()),
        counts.excluded_ft,
    )
    name_6 = "6 · excluded_ta_human + excluded_ta_ai == excluded_ta"
    human, ai = counts.excluded_ta_human, counts.excluded_ta_ai
    if human is None and ai is None:
        if ola1:
            # El motor de la Ola 1 escribe siempre el desglose: quitarlo no puede ser la forma
            # de no verificar la relación.
            rel.check(name_6, False, "counts sin excluded_ta_human/ai (el motor escribe ambos)")
        else:
            # Un manifiesto anterior al desglose humano/IA pudo no traerlos: no se puede saber.
            rel.unverifiable(name_6, "counts sin excluded_ta_human/ai (manifiesto sin desglose)")
    elif human is None or ai is None:
        rel.check(
            name_6, False, "solo uno de excluded_ta_human/ai presente (el motor escribe ambos)"
        )
    else:
        rel.eq(name_6, human + ai, counts.excluded_ta)

    ta = _artefacto(ctx, rel, TA, "relaciones del cribado T/A")
    ft = _artefacto(ctx, rel, FT, "relaciones del texto completo")
    if ta is not None:
        _cribado_ta(ctx, rel, counts, ta)
    if ft is not None and ta is not None:
        if ola1:
            _texto_completo_ola1(ctx, rel, counts, ta, ft)
        else:
            _texto_completo(rel, counts, ta, ft)
    elif ft is not None:
        rel.unverifiable("relaciones del texto completo", f"dependen de {TA} (ver arriba)")


def _conteos_ola1(rel: _Relations, counts: PrismaCounts) -> None:
    """Relaciones 6, 8 y 9 entre los conteos de la Ola 1 (PRISMA estricto, D2).

    Un informe buscado es evaluado salvo que no se recuperara y nadie lo rescatara: un rescate
    humano cuenta como evaluado (D2), así que ``fulltext_assessed = fulltext_sought −
    fulltext_not_retrieved`` y no ``screened − excluded_ta``.
    """
    rel.eq(
        "6 · fulltext_sought == screened − excluded_ta",
        counts.fulltext_sought,
        counts.screened - counts.excluded_ta,
    )
    rel.eq(
        "8 · fulltext_assessed == fulltext_sought − fulltext_not_retrieved",
        counts.fulltext_assessed,
        counts.fulltext_sought - counts.fulltext_not_retrieved,
    )
    rel.eq(
        "9 · excluded_ft_human + excluded_ft_ai == excluded_ft",
        counts.excluded_ft_human + counts.excluded_ft_ai,
        counts.excluded_ft,
    )


def _cribado_ta(
    ctx: AuditContext, rel: _Relations, counts: PrismaCounts, ta: list[ScreeningDecision]
) -> None:
    rel.eq(f"5 · len({TA}) == screened", len(ta), counts.screened)
    rel.eq(
        "6 · excluded_ta == #(final T/A == exclude)",
        counts.excluded_ta,
        sum(1 for d in ta if d.final_label == "exclude"),
    )
    bad_ensemble = [
        d.record_id
        for d in ta
        if d.votes and d.ensemble_label != recall_biased_label([v.label for v in d.votes])
    ]
    rel.check(
        "5 · ensemble_label == recall_biased_label(votes)", not bad_ensemble, _ids(bad_ensemble)
    )
    bad_final = [d.record_id for d in ta if d.final_label != (d.human_label or d.ensemble_label)]
    rel.check("5 · final_label == human_label or ensemble_label", not bad_final, _ids(bad_final))
    if _ola1(ctx):
        _cribado_ta_ola1(ctx, rel, counts, ta)
    name_votos = "§9.3 · un voto por screener T/A configurado"
    protocol = _seccion(ctx, rel, "protocol", name_votos)
    if protocol is None:
        return
    screeners = _screeners(protocol)
    if screeners is None:
        rel.unverifiable(name_votos, "el protocolo no declara proveedor para screening_ta")
        return
    bad_votes = [
        d.record_id
        for d in ta
        if len(d.votes) != len(screeners) or any(v.model not in screeners for v in d.votes)
    ]
    rel.check(name_votos, not bad_votes, f"{_ids(bad_votes)} (screeners: {_ids(screeners)})")


def _cribado_ta_ola1(
    ctx: AuditContext, rel: _Relations, counts: PrismaCounts, ta: list[ScreeningDecision]
) -> None:
    """Relaciones 5 y 6 que solo se pueden comprobar con los artefactos de la Ola 1.

    El motor criba ``02_dedup/records.json`` en su orden y escribe una decisión por registro: una
    decisión de más, de menos o reordenada no sale del pipeline.
    """
    name_orden = f"5 · {TA} en el orden de {DEDUP_RECORDS}"
    deduped = _artefacto(ctx, rel, DEDUP_RECORDS, name_orden)
    if deduped is not None:
        _misma_secuencia(rel, name_orden, [d.record_id for d in ta], [r.record_id for r in deduped])
    rel.eq(
        "6 · fulltext_sought == #(final T/A ∈ {include, unclear})",
        counts.fulltext_sought,
        sum(1 for d in ta if d.final_label in _PASAN_TA),
    )


def _busqueda_y_dedup(ctx: AuditContext, rel: _Relations) -> None:
    """Relaciones 1 y 4 de §4.4: los conteos salen de ``01_search/`` y ``02_dedup/``.

    La reconstrucción C3 declaraba 40/40/40 identificados por base frente a 28 registros
    (auditoría 2026-09-03): con los registros de la búsqueda (antes del dedup) y el informe del
    dedup en disco, ``identified``, ``identified_by_source``, ``duplicates_removed`` y ``screened``
    se recalculan. Σ ``n_returned`` del log de búsqueda lo compara ``search_log``.
    """
    counts = _seccion(ctx, rel, "counts", "relaciones de la búsqueda y el dedup")
    if counts is None:
        return
    records = _artefacto(
        ctx, rel, SEARCH_RECORDS, f"1 · {SEARCH_RECORDS} (identified, identified_by_source)"
    )
    if records is not None:
        rel.eq(f"1 · identified == len({SEARCH_RECORDS})", counts.identified, len(records))
        rel.eq(
            "1 · identified_by_source == Counter(source_db) de records.json",
            dict(sorted(counts.identified_by_source.items())),
            dict(sorted(Counter(r.source_db for r in records).items())),
        )
    dedup = _artefacto(ctx, rel, DEDUP_REPORT, f"4 · {DEDUP_REPORT} (n_in, n_out, duplicates)")
    deduped = _artefacto(ctx, rel, DEDUP_RECORDS, f"4 · {DEDUP_RECORDS} (ids, screened)")
    if dedup is not None:
        rel.eq("4 · dedup.n_in == identified", dedup.n_in, counts.identified)
        rel.eq(
            "4 · n_in − n_out == len(duplicates) == duplicates_removed",
            (dedup.n_in - dedup.n_out, len(dedup.duplicates)),
            (counts.duplicates_removed, counts.duplicates_removed),
        )
    if deduped is not None:
        repetidos = sorted(i for i, n in Counter(r.record_id for r in deduped).items() if n > 1)
        rel.check(f"4 · ids de {DEDUP_RECORDS} únicos", not repetidos, _ids(repetidos))
        _diario_dentro_del_dedup(ctx, rel, deduped)
    if dedup is not None and deduped is not None:
        rel.eq(
            f"4 · n_out == screened == len({DEDUP_RECORDS})",
            (dedup.n_out, len(deduped)),
            (counts.screened, counts.screened),
        )


def _diario_dentro_del_dedup(
    ctx: AuditContext, rel: _Relations, deduped: list[SearchRecord]
) -> None:
    """Relación 4: todo ``record_id`` del diario de T/A está en ``02_dedup/records.json``.

    Sacar un registro ya cribado de ``02_dedup/records.json`` y de las decisiones, disfrazado de
    duplicado, y ajustar a mano el informe del dedup, los conteos, el desglose, las métricas y el
    CSV deja cuadradas todas las demás relaciones. El motor criba el resultado del dedup y su
    diario conserva la línea del registro que ya no está.
    """
    name = f"4 · ids de {SCREENING_JOURNAL} ⊆ ids de {DEDUP_RECORDS}"
    if not deduped:  # sin registros que cribar no hay diario
        rel.check(name, True)
        return
    diario = ctx.art.jsonl(SCREENING_JOURNAL)
    if not diario.present:
        rel.ausente(name, f"{SCREENING_JOURNAL} ausente con {len(deduped)} registro(s) cribados")
        return
    if diario.value is None:
        rel.unverifiable(name, f"{SCREENING_JOURNAL} ilegible (ver `schemas`)")
        return
    # Del JSON tal cual: una línea que no valida su modelo sigue diciendo qué registro cribó.
    en_el_diario: set[str] = set()
    sin_id = 0
    for _, linea in diario.value:
        record_id = linea.get("record_id") if isinstance(linea, dict) else None
        if isinstance(record_id, str):
            en_el_diario.add(record_id)
        else:
            sin_id += 1
    fuera = sorted(en_el_diario - {r.record_id for r in deduped})
    if fuera:
        rel.check(name, False, _ids(fuera))
    elif sin_id or diario.error:
        rel.unverifiable(name, f"{SCREENING_JOURNAL} con líneas sin record_id (ver `schemas`)")
    else:
        rel.check(name, True)


def _texto_completo_ola1(
    ctx: AuditContext,
    rel: _Relations,
    counts: PrismaCounts,
    ta: list[ScreeningDecision],
    ft: list[ScreeningDecision],
) -> None:
    """Relaciones 7-10 de §4.4 con la recuperación, los rescates y la lista 16b (D2, M11).

    PRISMA estricto: un informe sin texto completo no se criba con IA (sin voto ni propuesta) y
    solo cuenta como evaluado si un humano lo rescata con una razón (D2). Así, un rescatado tiene
    etiqueta humana y ningún voto, un no recuperado sin rescate no tiene ni lo uno ni lo otro, y
    ``fulltext_rescued + fulltext_not_retrieved`` son los no recuperados.
    """
    pasan = [d.record_id for d in ta if d.final_label in _PASAN_TA]
    ids_ft = [d.record_id for d in ft]
    _misma_secuencia(rel, "7 · ids de 04_fulltext == pasan T/A", ids_ft, pasan)
    _recuperacion(ctx, rel, ft, ids_ft)
    _propuestas_ft(rel, ft)
    no_recuperados = [d for d in ft if d.fulltext_status == "not_retrieved"]
    rel.eq(
        "8 · fulltext_not_retrieved == #(no recuperado sin humano)",
        counts.fulltext_not_retrieved,
        sum(1 for d in no_recuperados if d.human_label is None),
    )
    rel.eq(
        "8 · fulltext_rescued == #(no recuperado con humano)",
        counts.fulltext_rescued,
        sum(1 for d in no_recuperados if d.human_label is not None),
    )
    rel.eq(
        "8 · fulltext_assessed == #(final FT ≠ null)",
        counts.fulltext_assessed,
        sum(1 for d in ft if d.final_label is not None),
    )
    excluidos = [d for d in ft if d.final_label == "exclude"]
    rel.eq("9 · excluded_ft == #(final FT == exclude)", counts.excluded_ft, len(excluidos))
    _lista_16b(ctx, rel, counts, ft, excluidos)
    rel.eq(
        "10 · included == #(final FT == include)",
        counts.included,
        sum(1 for d in ft if d.final_label == "include"),
    )


def _recuperacion(
    ctx: AuditContext, rel: _Relations, ft: list[ScreeningDecision], ids_ft: list[str]
) -> None:
    """Relación 7: recuperado ⇔ ``retrieval.available`` ⇔ un voto de la IA (D2).

    ``retrieval.json`` tiene una fila por informe buscado, en su orden, también los fallos
    transitorios que el diario no guarda (§14, fila 24a). Un informe recuperado lleva exactamente
    un voto; uno no recuperado no se criba con la IA: ni votos ni propuesta (``votes == []`` y
    ``ensemble_label`` nulo; si un humano lo rescata es solo con su etiqueta, D2). Una decisión
    sin ``fulltext_status`` no sale del motor de la Ola 1 y no cuenta para ningún lado: se marca.
    """
    name = "7 · retrieved ⇔ retrieval.available ⇔ un voto"
    retrieval = _artefacto(ctx, rel, RETRIEVAL, name)
    if retrieval is None:
        return
    ids_recuperacion = [r.record_id for r in retrieval]
    _misma_secuencia(rel, f"7 · ids de {RETRIEVAL} == ids de 04_fulltext", ids_recuperacion, ids_ft)
    disponible = {r.record_id: r.available for r in retrieval}

    def _coherente(d: ScreeningDecision) -> bool:
        if d.fulltext_status is None:
            return False
        recuperado = d.fulltext_status == "retrieved"
        if disponible.get(d.record_id) is not recuperado:
            return False
        if recuperado:
            return len(d.votes) == 1
        return not d.votes and d.ensemble_label is None

    malos = [d.record_id for d in ft if not _coherente(d)]
    rel.check(name, not malos, _ids(malos))
    _textos_en_cache(ctx, rel, retrieval)


def _textos_en_cache(ctx: AuditContext, rel: _Relations, retrieval: list[Any]) -> None:
    """Los textos de ``04_fulltext/texts/`` son los que registra ``retrieval.json`` (E5, FG2).

    Un texto recuperado se guarda en ``04_fulltext/texts/<sha256(id)[:16]>.txt`` (bytes UTF-8) y
    ``retrieval.json`` lleva su ``text_file``, ``text_sha256`` y ``n_chars``: un texto editado o
    borrado después cambia lo que la IA cribó, extrajo y verificó sin que nada lo viera. La ruta se
    calcula del ``record_id`` (nunca se abre la del artefacto, que es entrada no confiable) y el
    texto se lee en bytes (sin traducir saltos de línea), como lo escribe el motor.
    """
    name = f"7 · textos de {TEXTOS} == text_sha256/n_chars de {RETRIEVAL}"
    malos: list[str] = []
    for row in retrieval:
        if not row.available:
            continue
        esperado = f"{TEXTOS}/{sha256_text(row.record_id)[:16]}.txt"
        if row.text_file != esperado:
            malos.append(row.record_id)
            continue
        try:
            texto = (ctx.run_dir / esperado).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            malos.append(row.record_id)
            continue
        if sha256_text(texto) != row.text_sha256 or len(texto) != row.n_chars:
            malos.append(row.record_id)
    rel.check(name, not malos, f"texto ausente, ilegible o distinto: {_ids(malos)}")


def _propuestas_ft(rel: _Relations, ft: list[ScreeningDecision]) -> None:
    """Relación 7 tras aprobar FT: propuesta, etiqueta final, ``unclear`` y rescates (D1, D2)."""
    malos = [
        d.record_id
        for d in ft
        if d.ensemble_label
        != (recall_biased_label([v.label for v in d.votes]) if d.votes else None)
    ]
    rel.check(
        "7 · ensemble_label FT == propuesta de su voto (null si no se recuperó)",
        not malos,
        _ids(malos),
    )
    malos = [d.record_id for d in ft if d.final_label != (d.human_label or d.ensemble_label)]
    rel.check("7 · final_label FT == human_label or ensemble_label", not malos, _ids(malos))
    malos = [d.record_id for d in ft if d.final_label == "unclear"]
    rel.check("7 · ningún final FT == unclear (lo resuelve un humano, D1)", not malos, _ids(malos))
    malos = [
        d.record_id
        for d in ft
        if d.fulltext_status == "not_retrieved"
        and d.human_label is not None
        and not (d.human_reason or "").strip()
    ]
    rel.check("7 · un rescate lleva human_reason (D2)", not malos, _ids(malos))


def _lista_16b(
    ctx: AuditContext,
    rel: _Relations,
    counts: PrismaCounts,
    ft: list[ScreeningDecision],
    excluidos: list[ScreeningDecision],
) -> None:
    """Relación 9: la lista 16b (``excluded.json``) frente a las decisiones FT y los conteos.

    Además de las igualdades de §4.4, la lista se recalcula con ``compute_ft_excluded``, la
    misma función con la que la escribe el motor (razón humana si el humano excluyó; si no, el
    primer criterio de la IA): así no se puede cambiar una razón, un título o un origen sin que
    se note, ni pasar exclusiones de la IA a humanas en los conteos.
    """
    reports = _artefacto(ctx, rel, EXCLUDED, f"9 · lista 16b ({EXCLUDED})")
    if reports is None:
        return
    rel.eq(f"9 · excluded_ft == len({EXCLUDED})", counts.excluded_ft, len(reports))
    rel.eq(
        "9 · ft_exclusion_reasons == Counter(reason) de excluded.json",
        dict(sorted(counts.ft_exclusion_reasons.items())),
        dict(sorted(Counter(r.reason for r in reports).items())),
    )
    humanos = {d.record_id for d in excluidos if d.human_label == "exclude"}
    malos = [
        r.record_id for r in reports if (r.reason_source == "human") != (r.record_id in humanos)
    ]
    rel.check("9 · reason_source == human ⇔ human_label == exclude", not malos, _ids(malos))
    rel.eq(
        "9 · excluded_ft_human/ai == reason_source de excluded.json",
        (counts.excluded_ft_human, counts.excluded_ft_ai),
        (
            sum(1 for r in reports if r.reason_source == "human"),
            sum(1 for r in reports if r.reason_source == "ai"),
        ),
    )
    name = f"9 · {EXCLUDED} == compute_ft_excluded({FT})"
    deduped = _artefacto(ctx, rel, DEDUP_RECORDS, name)
    if deduped is None:
        return
    esperado = [r.model_dump() for r in compute_ft_excluded(ft, deduped)]
    actual = [r.model_dump() for r in reports]
    distintos = [a.get("record_id", "?") for a, e in zip(actual, esperado, strict=False) if a != e]
    detalle = f"{_ids(distintos)} ({len(actual)} frente a {len(esperado)} informes)"
    rel.check(name, actual == esperado, detalle)


def _texto_completo(
    rel: _Relations,
    counts: PrismaCounts,
    ta: list[ScreeningDecision],
    ft: list[ScreeningDecision],
) -> None:
    passed = {d.record_id for d in ta if d.final_label in _PASAN_TA}
    in_ft = {d.record_id for d in ft}
    rel.check("7 · ids de 04_fulltext == pasan T/A", in_ft == passed, _ids(sorted(in_ft ^ passed)))
    rel.eq(f"v0.7 · len({FT}) == fulltext_assessed", len(ft), counts.fulltext_assessed)
    rel.eq(
        "9 · excluded_ft == #(final FT == exclude)",
        counts.excluded_ft,
        sum(1 for d in ft if d.final_label == "exclude"),
    )
    bad = [
        d.record_id
        for d in ft
        if len(d.votes) != 1 or d.final_label != (d.human_label or d.ensemble_label)
    ]
    rel.check("v0.7 · un voto FT y final == human or ensemble", not bad, _ids(bad))
    rel.eq(
        "v0.7 · included == #(final FT ∈ {include, unclear})",
        counts.included,
        len(_ids_incluidos(ft, ola1=False)),
    )


def _included_artifacts(ctx: AuditContext, rel: _Relations) -> None:
    ids = included_ids(ctx)
    if ids is None:
        rel.unverifiable("10 · artefactos de los incluidos", f"{FT} ausente o inválido")
    assessments = None
    for path in (EXTRACTIONS, ASSESSMENTS):
        value = _artefacto(ctx, rel, path, f"10 · claves de {path}")
        if path == ASSESSMENTS:
            assessments = value
        if value is None or ids is None:
            continue
        rel.check(
            f"10 · claves de {path} == incluidos",
            set(value) == set(ids),
            _ids(sorted(set(value) ^ set(ids))),
        )
        bad = [k for k, v in value.items() if v.study_id != k]
        rel.check(f"10 · study_id == clave en {path}", not bad, _ids(bad))
    _herramienta_rob(ctx, rel, assessments)
    _doble_extraccion(ctx, rel, ids)
    _total_excluidos(ctx, rel)


def _herramienta_rob(
    ctx: AuditContext, rel: _Relations, assessments: dict[str, Any] | None
) -> None:
    if assessments is None:  # ya registrado como ausente o inválido
        return
    name = "§9.3 · assessment.tool == protocol.rob_tool"
    protocol = _seccion(ctx, rel, "protocol", name)
    if protocol is None:
        return
    tools = sorted({a.tool for a in assessments.values()})
    rel.check(
        name,
        all(t == protocol.rob_tool for t in tools),
        f"{_ids(tools)} ≠ {_valor(protocol.rob_tool)}",
    )


def _doble_extraccion(ctx: AuditContext, rel: _Relations, ids: list[str] | None) -> None:
    name = "§9.3 · extraction_agreement.n_studies == subconjunto de doble extracción"
    # Sin `protocol` no se sabe si se declaró un 2.º extractor: la relación queda rota por
    # ausencia (o no verificable si el protocolo no valida), no omitida.
    _seccion(ctx, rel, "protocol", "§9.3 · doble extracción declarada en el protocolo")
    agreement = ctx.art.artifact(AGREEMENT)
    if agreement.ok:
        if ids is None:
            rel.unverifiable(name, f"{FT} ausente o inválido")
            return
        subset = select_double_extraction_subset([SearchRecord(record_id=i, title="") for i in ids])
        rel.eq(name, agreement.value.n_studies, len(subset))
    elif not agreement.present:
        if _requiere_doble_extraccion(ctx):
            rel.check(
                f"§9.3 · {AGREEMENT} de la doble extracción declarada",
                False,
                f"{AGREEMENT} ausente (el protocolo declara un 2.º extractor y hay incluidos)",
            )
    else:
        rel.unverifiable(name, f"{AGREEMENT} inválido (ver `schemas`)")


def _total_excluidos(ctx: AuditContext, rel: _Relations) -> None:
    name = "10 · exclusions.total_excluded == excluded_ta + excluded_ft"
    exclusions = _artefacto(ctx, rel, EXCLUSIONS, name)
    if exclusions is None:
        return
    counts = _seccion(ctx, rel, "counts", name)
    if counts is None:
        return
    rel.eq(name, exclusions.total_excluded, counts.excluded_ta + counts.excluded_ft)


def _csv(ctx: AuditContext, rel: _Relations) -> None:
    name = "11 · CSV PRISMA2020"
    c = _seccion(ctx, rel, "counts", name)
    if c is None:
        return
    leido = _read_csv(ctx)
    if leido.ausente:  # `deliverable` ya da el FAIL por el fichero que falta
        rel.unverifiable(name, f"{CSV} ausente (ver `deliverable`)")
        return
    if leido.values is None:  # el motor siempre escribe un CSV legible
        rel.check(name, False, leido.problema)
        return
    # Relación 11. v0.7 (sin run.json): buscados = evaluados y ningún no recuperado (un informe
    # sin texto se cribaba con el resumen). Desde la Ola 1, las cajas reales del texto completo.
    ola1 = _ola1(ctx)
    expected = {
        "database_results": c.identified,
        "duplicates": c.duplicates_removed,
        "records_screened": c.screened,
        "records_excluded": c.excluded_ta,
        "dbr_sought_reports": c.fulltext_sought if ola1 else c.fulltext_assessed,
        "dbr_notretrieved_reports": c.fulltext_not_retrieved if ola1 else 0,
        "dbr_assessed": c.fulltext_assessed,
        "new_studies": c.included,
    }
    for key, value in expected.items():
        rel.eq(f"11 · CSV {key}", leido.values.get(key), str(value))
    if ola1:
        protocolo = _efectos_del_protocolo(ctx)
        if protocolo.problema:
            rel.unverifiable("11 · CSV total_studies_ma/total_reports_ma", protocolo.problema)
            return
        k = len(protocolo.efectos.effects) if protocolo.efectos is not None else 0
        for key in ("total_studies_ma", "total_reports_ma"):
            rel.eq(f"11 · CSV {key} == k de {EFECTOS_PROTOCOLO}", leido.values.get(key), str(k))


def _calls(ctx: AuditContext, rel: _Relations) -> None:
    manifest = ctx.manifest_dict or {}
    calls = ctx.llm_calls
    # Con `llm_calls.jsonl` ilegible `calls` está vacío (no se cae a la copia del manifiesto): las
    # relaciones que se apoyan en las llamadas quedan no verificables, y `schemas` da el FAIL.
    ilegible = ctx.llm_calls_ilegible is not None
    name = "§9.3 · models_used == modelos de llm_calls"
    # `models_used` y las llamadas no pasan por un modelo aquí: una cadena, un mapa o una
    # lista anidada (bomba de alias) no se compara ni se ordena, `schemas` ya lo marca.
    models: set[str] = set()
    malformed = 0
    for call in calls:
        provider, model = call.get("provider"), call.get("model")
        if isinstance(provider, str) and isinstance(model, str):
            models.add(f"{provider}:{model}")
        else:
            malformed += 1
    declared_section = ctx.manifest_section("models_used")
    if not declared_section.present:
        # El motor siempre escribe `models_used` (`RunContext.write_manifest`): sin él no hay
        # nada que cotejar con las llamadas y la corrida no puede quedar publicable.
        rel.ausente(name, "models_used ausente en el manifiesto")
    elif not declared_section.ok:
        # Presente pero de otro tipo: `schemas` valida `models_used` y marca FAIL.
        rel.unverifiable(name, "models_used no es una lista de cadenas (ver `schemas`)")
    elif ilegible:
        rel.unverifiable(name, LLM_CALLS_ILEGIBLE)
    elif malformed:
        # Una llamada sin provider/model textuales no valida `RunMeta`: lo marca `schemas`.
        rel.unverifiable(
            name, f"{malformed} llamada(s) sin provider/model textuales (ver `schemas`)"
        )
    else:
        declared: list[str] = declared_section.value
        rel.check(
            name,
            sorted(declared) == sorted(models),
            f"declarados {_ids(sorted(declared))}; en llamadas {_ids(sorted(models))}",
        )
    name_det = "§9.3 · deterministic_token_level == all(deterministic)"
    if ilegible:
        rel.unverifiable(name_det, LLM_CALLS_ILEGIBLE)
    else:
        rel.eq(
            name_det,
            manifest.get("deterministic_token_level"),
            all(c.get("deterministic") is True for c in calls) if calls else True,
        )
    if ctx.art.exists(LLM_CALLS):
        # Los demás checks leen `llm_calls.jsonl` (la fuente) y `manifest` lee la copia del
        # manifiesto: sin esta igualdad, editar una de las dos pasaría desapercibido. `==` y no un
        # volcado: con un valor hostil (bomba de alias) termina cuando las formas difieren.
        name_copia = "§4.3 · manifest.llm_calls == líneas de llm_calls.jsonl"
        if ilegible:  # sin leer el fichero no hay con qué comparar la copia
            rel.unverifiable(name_copia, LLM_CALLS_ILEGIBLE)
        else:
            rel.check(
                name_copia,
                bool(manifest.get("llm_calls") == calls),
                "distintas (o en otro orden)",
            )
    c = _seccion(ctx, rel, "counts", "§9.3 · cota inferior de llamadas")
    if c is None:
        return
    screeners = _screeners(ctx.protocol)
    # Sin protocolo legible se supone un solo screener: es la cota más baja posible, así que sigue
    # siendo una cota inferior válida (la ausencia del protocolo la marcan otras relaciones).
    members = len(screeners) if screeners else 1
    agreement = ctx.art.artifact(AGREEMENT)
    doubles = agreement.value.n_studies if agreement.ok else 0
    if not _ola1(ctx):
        # Sin run.json el motor es el v0.7, que nunca rescata textos completos: un
        # `fulltext_rescued` distinto de cero solo servía para bajar la cota (revisión de la
        # Tarea 7). Se exige cero y la cota no descuenta rescates.
        rescued = 0
        rel.check(
            "v0.7 · fulltext_rescued == 0 (el motor v0.7 no rescata textos completos)",
            c.fulltext_rescued == 0,
            f"{_n(c.fulltext_rescued)} ≠ 0",
        )
    else:
        rescued = c.fulltext_rescued
    by_ai = c.fulltext_assessed - rescued
    floor = c.screened * members + by_ai + 2 * c.included + doubles + 1
    name_cota = "§9.3 · llamadas ≥ cota inferior de las decisiones"
    if ilegible:
        rel.unverifiable(name_cota, LLM_CALLS_ILEGIBLE)
        return
    rel.check(
        name_cota,
        len(calls) >= floor,
        f"{len(calls)} llamadas < {_n(floor)} = {_n(c.screened)}·{members} + {_n(by_ai)} + "
        f"2·{_n(c.included)} + {_n(doubles)} + 1",
    )


def _gold_anclado(ctx: AuditContext, rel: _Relations, protocolo: _GoldProtocolo) -> None:
    """§9.3 (D6): ``gold.json`` trae como mínimo los ids del gold de la instantánea del protocolo.

    ``gold.json`` es el gold efectivo: el fichero del protocolo más las etiquetas por código
    (``gold_labels=``), que pueden cambiar valores y añadir ids pero no quitarlos. Sin este
    ancla, borrar ``gold.json``, ``metrics.json`` y la copia del manifiesto dejaría sin
    verificar un recall bajo el umbral (D7).
    """
    name = "§9.3 · gold.json con el gold del protocolo"
    if protocolo.problema:
        rel.unverifiable(name, protocolo.problema)
        return
    if not protocolo.claves:  # el protocolo no trae gold: el motor no escribe gold.json
        return
    gold = ctx.art.artifact(GOLD)
    if not gold.present:
        rel.ausente(name, f"{GOLD} ausente con gold en {GOLD_PROTOCOLO}")
        return
    if not gold.ok:
        rel.unverifiable(name, f"{GOLD} inválido (ver `schemas`)")
        return
    faltan = sorted(protocolo.claves - set(gold.value))
    rel.check(name, not faltan, f"faltan en {GOLD}: {_ids(faltan)}")


def _metrics(ctx: AuditContext, rel: _Relations) -> None:
    ola1 = _ola1(ctx)
    protocolo = _gold_del_protocolo(ctx) if ola1 else _GoldProtocolo()
    if ola1:
        _gold_anclado(ctx, rel, protocolo)
    loaded = ctx.art.artifact(METRICS)
    if not loaded.present:
        # El motor escribe gold.json y metrics.json juntos (`_screen_ta`, si hay gold): quitar
        # las métricas no puede ser la forma de no recalcularlas. Hay gold si el protocolo
        # trae etiquetas o si `gold.json` existe (etiquetas pasadas por código).
        con = [
            *([f"{GOLD} presente"] if ola1 and ctx.art.exists(GOLD) else []),
            *([f"gold en {GOLD_PROTOCOLO}"] if protocolo.claves else []),
        ]
        if con:
            rel.check(
                GOLD_Y_METRICAS,
                False,
                f"{METRICS} ausente con {' y '.join(con)} (el motor escribe los dos)",
            )
        return
    if not loaded.ok:
        rel.unverifiable("§9.3 · métricas desde la matriz", "metrics.json inválido")
        return
    m = loaded.value
    tp, fp, fn, tn = m.tp, m.fp, m.fn, m.tn
    rel.eq("§9.3 · n == tp+fp+fn+tn", m.n, tp + fp + fn + tn)
    recomputed: dict[str, Callable[[], float | None]] = {
        "recall": lambda: _ratio(tp, tp + fn),
        "lost_evidence": lambda: _ratio(fn, tp + fn),
        "precision": lambda: _ratio(tp, tp + fp),
        "mcc": lambda: mcc(tp, fp, fn, tn),
        "wmcc": lambda: wmcc(tp, fp, fn, tn, fn_weight=m.wmcc_fn_weight),
        "cohen_kappa": lambda: kappa_from_matrix(tp, fp, fn, tn),
    }
    for name, compute in recomputed.items():
        label = f"§9.3 · {name} recalculado desde la matriz"
        try:
            value = compute()
        except (ArithmeticError, ValueError):  # una matriz de enteros enormes desborda `sqrt`
            rel.check(label, False, "no calculable: la matriz desborda el cálculo")
            continue
        declared = getattr(m, name)
        rel.check(label, _close(declared, value), f"{_valor(declared)} ≠ {_valor(value)}")
    name = "§9.3 · wmcc_fn_weight == protocolo"
    protocol = _seccion(ctx, rel, "protocol", name)
    if protocol is not None:
        rel.eq(name, m.wmcc_fn_weight, float(protocol.thresholds.get("wmcc_fn_weight", 10.0)))
    if _ola1(ctx):
        _matriz_desde_gold(ctx, rel, (tp, fp, fn, tn))


def _matriz_desde_gold(
    ctx: AuditContext, rel: _Relations, declarada: tuple[int, int, int, int]
) -> None:
    """§9.3 (F2): la matriz de ``metrics.json`` sale de ``decisions.json`` y ``gold.json``.

    Recalcular las métricas desde la matriz no basta: una matriz inventada (como la κ de C3) es
    coherente consigo misma. Desde la Ola 1 el motor escribe el gold efectivo (D6) y la matriz se
    recalcula con la propuesta de la IA (``ensemble_label``), como ``compute_screening_metrics``:
    con ``final_label`` mediría humano + IA.
    """
    name = "§9.3 · matriz == recálculo desde decisions.json y gold.json (ensemble_label, D6)"
    gold = ctx.art.artifact(GOLD)
    if not gold.present:
        rel.check(name, False, f"{GOLD} ausente con {METRICS} presente (el motor escribe los dos)")
        return
    if not gold.ok:
        rel.unverifiable(name, f"{GOLD} inválido (ver `schemas`)")
        return
    ta = ctx.art.artifact(TA)
    if not ta.ok:
        rel.unverifiable(name, f"{TA} ausente o inválido (ver arriba)")
        return
    by_id = {d.record_id: d for d in ta.value}
    pares = [
        (by_id[rid].ensemble_label != "exclude", truth)
        for rid, truth in gold.value.items()
        if rid in by_id
    ]
    rel.eq(name, declarada, confusion([p for p, _ in pares], [t for _, t in pares]))


def _copies(ctx: AuditContext, rel: _Relations) -> None:
    manifest = ctx.manifest_dict or {}
    for key, path in MANIFEST_COPIES.items():
        loaded = ctx.art.json(path)
        if key not in manifest and not loaded.present:
            nombre = f"§9.3 · copia `{key}` del manifiesto"
            if key in COPIAS_SIEMPRE_ESCRITAS:
                # Ni el fichero ni su copia: el motor escribe ambos siempre (la ausencia del
                # fichero la marca también `stage_artifacts`, pero esta relación no se omite).
                rel.ausente(nombre, f"{path} y su copia ausentes")
            elif key == "extraction_agreement" and _requiere_doble_extraccion(ctx):
                rel.check(
                    nombre,
                    False,
                    f"{path} y su copia ausentes (el protocolo declara un 2.º extractor)",
                )
            elif key == "meta_analysis" and _efectos_del_protocolo(ctx).efectos is not None:
                rel.check(
                    nombre, False, f"{path} y su copia ausentes ({EFECTOS_PROTOCOLO} con efectos)"
                )
            continue
        if key not in manifest:
            rel.check(f"§9.3 · copia `{key}` del manifiesto", False, f"{path} sin copia")
        elif not loaded.present:
            rel.check(f"§9.3 · copia `{key}` del manifiesto", False, f"{path} ausente")
        elif not loaded.ok:
            rel.unverifiable(f"§9.3 · copia `{key}` del manifiesto", f"{path} ilegible")
        else:
            # `==` y no un volcado a JSON/`repr`: con un valor hostil (bomba de alias) la
            # comparación termina en cuanto las formas difieren o se agota el JSON, que es finito.
            rel.check(
                f"§9.3 · copia `{key}` del manifiesto == {path}",
                bool(manifest[key] == loaded.value),
                "distinta",
            )


def _clave(item: object) -> str:
    """Forma canónica de un valor JSON, para comparar sin depender del orden de las claves."""
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def _sin_humanos(item: object) -> str:
    """:func:`_clave` de un consolidado o de una salida de diario sin ``_CAMPOS_HUMANOS``."""
    if isinstance(item, dict):
        item = {k: v for k, v in item.items() if k not in _CAMPOS_HUMANOS}
    return _clave(item)


@dataclass(frozen=True)
class _Llamadas:
    """``llm_calls.jsonl`` para la relación 12: sus líneas en forma canónica o por qué no.

    Attributes:
        claves: :func:`_clave` de cada línea y cuántas veces aparece (``None`` si no se puede
            leer o falta). Cada aparición respalda como mucho una posición de meta.
        ausente: el fichero no existe (el motor lo escribe antes que cualquier diario).
    """

    claves: Counter[str] | None
    ausente: bool = False


def _llamadas(ctx: AuditContext) -> _Llamadas:
    """Las llamadas de ``llm_calls.jsonl``, la fuente (D3), nunca la copia del manifiesto.

    La copia la compara ``_calls``; aquí no se usa porque es YAML no confiable (una bomba de
    alias no se puede volcar a JSON) y porque el motor escribe cada llamada en ``llm_calls.jsonl``
    antes que en su diario.
    """
    if not ctx.art.exists(LLM_CALLS):
        return _Llamadas(None, ausente=True)
    raw = ctx.art.jsonl(LLM_CALLS)
    if raw.value is None:
        return _Llamadas(None)
    return _Llamadas(Counter(_clave(obj) for _, obj in raw.value))


def _llamadas_esperadas(
    stage: str, entry: JournalEntry, miembros: int | None, modo: str | None
) -> set[int] | None:
    """Llamadas que lleva una línea del diario de ``stage`` (relación 12; §14, fila 24c).

    T/A, una por miembro del ensemble; la recuperación, ninguna; FT, extracción (ambos
    extractores), RoB y síntesis, una. La verificación, una por cita que el juez juzga (las que
    existen en el corpus, con su fuente) en modo ``agent`` y ninguna en los demás modos; con el
    protocolo ilegible, cualquiera de las dos. ``None`` si no se puede saber: el protocolo no
    declara el ensemble T/A o la salida de la verificación no valida.
    """
    if stage == "screening_ta":
        return {miembros} if miembros else None
    if stage == "fulltext_retrieval":
        return {0}
    if stage == "verificacion":
        try:
            informe = VerificationReport.model_validate(entry.output)
        except Exception:  # fail-closed: una salida que no valida no da un número
            return None
        juzgadas = sum(1 for c in informe.checks if c.exists_in_corpus)
        if modo is None:
            return {0, juzgadas}
        return {juzgadas} if modo == "agent" else {0}
    return {1}


def _diarios(ctx: AuditContext, rel: _Relations) -> None:
    """Relación 12 de §4.4: los diarios frente a ``llm_calls.jsonl``.

    Cada meta de cada línea válida aparece idéntica en ``llm_calls.jsonl``, con la etapa y el
    registro de su línea, y cada línea lleva las llamadas que hace su etapa. Inclusión y no
    igualdad de totales (docstring del módulo). Un diario ausente no tiene metas que comprobar:
    su ausencia, si el motor lo escribe, la marcan la relación 13 (el consolidado sin su diario)
    y ``stage_artifacts``.
    """
    llamadas = _llamadas(ctx)
    screeners = _screeners(ctx.protocol)
    miembros = len(screeners) if screeners else None
    modo = ctx.protocol.grounding if ctx.protocol is not None else None
    usadas: Counter[str] = Counter()  # posiciones de meta que ya respalda cada llamada
    for stage, path in JOURNAL_PATHS.items():
        raw = ctx.art.jsonl(path)
        if not raw.present:
            continue
        name_metas = f"12 · metas de {path} en llm_calls.jsonl"
        name_n = f"12 · llamadas por línea en {path}"
        if raw.value is None:
            rel.unverifiable(name_metas, f"{path} ilegible (ver `schemas`)")
            rel.unverifiable(name_n, f"{path} ilegible (ver `schemas`)")
            continue
        modelos = ctx.art.jsonl_models(path)
        revision = _revisar_diario(
            stage, raw.value, dict(modelos.value or []), llamadas, usadas, miembros, modo
        )
        invalidas = f"{path} con líneas inválidas (ver `schemas`)" if modelos.error else ""
        if revision.problemas:
            rel.check(name_metas, False, _ids(revision.problemas))
        elif revision.con_metas and llamadas.ausente:
            rel.ausente(name_metas, f"{LLM_CALLS} ausente con metas en {path}")
        elif revision.con_metas and llamadas.claves is None:
            rel.unverifiable(name_metas, LLM_CALLS_ILEGIBLE)
        elif invalidas:
            rel.unverifiable(name_metas, invalidas)
        else:
            rel.check(name_metas, True)
        if revision.mal_contadas:
            rel.check(name_n, False, _ids(revision.mal_contadas))
        elif revision.sin_saber:
            rel.unverifiable(
                name_n,
                f"{revision.sin_saber} línea(s) sin número esperado de llamadas (protocolo sin "
                "ensemble T/A o salida de verificación inválida)",
            )
        elif invalidas:
            rel.unverifiable(name_n, invalidas)
        else:
            rel.check(name_n, True)


@dataclass
class _RevisionDiario:
    """Lo que la relación 12 encontró en las líneas válidas de un diario.

    Attributes:
        problemas: líneas con una meta que no está en ``llm_calls.jsonl`` (o cuya llamada ya
            respalda otra meta), una meta de otra etapa o registro, miembros de T/A con el mismo
            rol, o la línea misma de otra etapa (``"línea N …"``, sin repetir).
        mal_contadas: líneas con un número de llamadas distinto del de su etapa.
        sin_saber: líneas cuyo número esperado de llamadas no se puede saber.
        con_metas: alguna línea cita alguna llamada.
    """

    problemas: list[str] = field(default_factory=list)
    mal_contadas: list[str] = field(default_factory=list)
    sin_saber: int = 0
    con_metas: bool = False


def _revisar_diario(
    stage: str,
    lineas: list[tuple[int, Any]],
    validas: dict[int, JournalEntry],
    llamadas: _Llamadas,
    usadas: Counter[str],
    miembros: int | None,
    modo: str | None,
) -> _RevisionDiario:
    """Recorre las líneas de un diario para la relación 12 (las inválidas las marca ``schemas``).

    Las metas se comparan en crudo (``lineas``: el JSON tal cual) y no desde el modelo: «aparece
    idéntica» incluye los campos que ``LLMCall`` ignoraría o normalizaría. ``usadas`` cuenta, en
    todos los diarios, las posiciones de meta que respalda cada llamada: una línea de
    ``llm_calls.jsonl`` respalda una sola (una meta copiada no puede tapar la llamada que falta)
    y los miembros del ensemble T/A de una línea tienen roles distintos.
    """
    revision = _RevisionDiario()
    for numero, obj in lineas:
        entry = validas.get(numero)
        if entry is None:
            continue
        if entry.stage != stage:
            etapa = short_text(entry.stage, limit=_LIMITE_ID)
            revision.problemas.append(f"línea {numero} (etapa {etapa})")
            continue
        metas = obj.get("metas") or []
        revision.con_metas = revision.con_metas or bool(metas)
        for meta in metas:
            if meta.get("stage") != stage or meta.get("record_id") != entry.record_id:
                revision.problemas.append(f"línea {numero} (meta de otra etapa o registro)")
            elif llamadas.claves is not None:
                clave = _clave(meta)
                usadas[clave] += 1
                if clave not in llamadas.claves:
                    revision.problemas.append(f"línea {numero}")
                elif usadas[clave] > llamadas.claves[clave]:
                    revision.problemas.append(f"línea {numero} (llamada citada por otra meta)")
        if stage == "screening_ta":
            roles = [_clave(meta.get("role")) for meta in metas]
            if len(set(roles)) != len(roles):
                revision.problemas.append(f"línea {numero} (roles repetidos)")
        esperado = _llamadas_esperadas(stage, entry, miembros, modo)
        if esperado is None:
            revision.sin_saber += 1
        elif len(metas) not in esperado:
            se_esperan = "/".join(map(str, sorted(esperado)))
            revision.mal_contadas.append(f"línea {numero}: {len(metas)} (se esperan {se_esperan})")
    revision.problemas = list(dict.fromkeys(revision.problemas))
    return revision


@dataclass(frozen=True)
class _Diario:
    """Las salidas del diario de una etapa por registro, para la relación 13.

    Attributes:
        path: ruta del diario.
        presente: el fichero existe.
        legible: se pudo leer como texto (sus líneas inválidas las marca ``schemas``).
        invalidas: alguna línea no es JSON o no valida ``JournalEntry``.
        salidas: ``record_id → {_sin_humanos(output)}`` de las líneas válidas de su etapa.
    """

    path: str
    presente: bool = False
    legible: bool = False
    invalidas: bool = False
    salidas: dict[str, set[str]] = field(default_factory=dict)


def _diario(ctx: AuditContext, stage: str) -> _Diario:
    path = JOURNAL_PATHS[stage]
    raw = ctx.art.jsonl(path)
    if not raw.present:
        return _Diario(path)
    if raw.value is None:
        return _Diario(path, presente=True)
    modelos = ctx.art.jsonl_models(path)
    salidas: dict[str, set[str]] = {}
    for _, entry in modelos.value or []:
        if entry.stage == stage:
            salidas.setdefault(entry.record_id, set()).add(_sin_humanos(entry.output))
    return _Diario(path, True, True, modelos.error is not None, salidas)


def _contra_diario(
    rel: _Relations, name: str, diario: _Diario, items: Iterable[tuple[str, object]]
) -> None:
    """Relación 13: cada ``(record_id, consolidado)`` coincide con una línea de su diario.

    Un consolidado sin nada que respaldar se verifica (no hay registro sin línea). Con registros,
    un diario ausente es manipulación (el motor escribe la línea antes que el consolidado), uno
    ilegible es no verificable (``schemas``), y un registro sin línea igual es una relación rota,
    salvo que el diario tenga líneas inválidas: la que falta podría ser una de ellas.
    """
    items = list(items)
    if not items:
        rel.check(name, True)
        return
    if not diario.presente:
        rel.ausente(name, f"{diario.path} ausente con {len(items)} registro(s) consolidados")
        return
    if not diario.legible:
        rel.unverifiable(name, f"{diario.path} ilegible (ver `schemas`)")
        return
    malos = [rid for rid, item in items if _sin_humanos(item) not in diario.salidas.get(rid, ())]
    if malos and diario.invalidas:
        rel.unverifiable(
            name,
            f"{_ids(malos)} sin línea igual; {diario.path} tiene líneas inválidas (ver `schemas`)",
        )
    else:
        rel.check(name, not malos, _ids(malos))


def _consolidado(ctx: AuditContext, rel: _Relations, path: str, name: str) -> Any | None:
    """El consolidado ``path`` en crudo (JSON) si valida su modelo; si no, se registra por qué."""
    if _artefacto(ctx, rel, path, name) is None:
        return None
    return ctx.art.json(path).value


def _consolidados(ctx: AuditContext, rel: _Relations) -> None:
    """Relación 13 de §4.4: cada consolidado coincide, sin campos humanos, con su diario.

    Se compara el JSON en crudo (no los modelos): un campo que el modelo ignora o normaliza
    también cuenta. Las decisiones T/A y FT pierden antes los campos humanos que añade el gate.
    Sin diario quedan, por diseño, los no recuperados a texto completo (sin llamada a la IA,
    relación 7) y los fallos transitorios de la recuperación, que el motor no escribe para
    reintentarlos al reanudar (§14, fila 24a).
    """
    for path, stage, elegir in (
        (TA, "screening_ta", lambda d: True),
        (FT, "screening_ft", lambda d: d.get("fulltext_status") == "retrieved"),
    ):
        name = f"13 · {path} == una línea de {JOURNAL_PATHS[stage]}"
        decisions = _consolidado(ctx, rel, path, name)
        if decisions is not None:
            items = [(d["record_id"], d) for d in decisions if elegir(d)]
            _contra_diario(rel, name, _diario(ctx, stage), items)
    name = f"13 · {RETRIEVAL} == una línea de {JOURNAL_PATHS['fulltext_retrieval']}"
    filas = _consolidado(ctx, rel, RETRIEVAL, name)
    if filas is not None:
        definitivas = [
            (f["record_id"], {k: v for k, v in f.items() if k != "record_id"})
            for f in filas
            if f.get("reason") not in TRANSIENT_FULLTEXT_REASONS
        ]
        _contra_diario(rel, name, _diario(ctx, "fulltext_retrieval"), definitivas)
    for path, stage in ((EXTRACTIONS, "extraccion"), (ASSESSMENTS, "rob")):
        name = f"13 · {path} == una línea de {JOURNAL_PATHS[stage]}"
        por_estudio = _consolidado(ctx, rel, path, name)
        if por_estudio is not None:
            _contra_diario(rel, name, _diario(ctx, stage), por_estudio.items())
    name = f"13 · {VERIFICATION} == una línea de {JOURNAL_PATHS['verificacion']}"
    verification = _consolidado(ctx, rel, VERIFICATION, name)
    if verification is not None:
        _contra_diario(rel, name, _diario(ctx, "verificacion"), [("verificacion", verification)])
    _documento(ctx, rel)
    _doble_extraccion_en_diario(ctx, rel)


def _normalizar(texto: str) -> str:
    return texto.replace("\r\n", "\n").replace("\r", "\n")


def _documento(ctx: AuditContext, rel: _Relations) -> None:
    """Relación 13 para la síntesis: ``documento.md`` lleva la narrativa de su diario.

    ``documento.md`` es el consolidado de la síntesis (el motor lo reescribe con la narrativa en
    cada invocación que llega al reporte); una narrativa que no sale de ninguna línea del diario
    no la produjo ninguna llamada registrada. Ausente o ilegible lo marca ``deliverable``.
    """
    path = JOURNAL_PATHS["sintesis"]
    name = f"13 · {DOCUMENTO} contiene la narrativa de una línea de {path}"
    texto = ctx.art.text(DOCUMENTO)
    if not texto.ok:
        estado = "ausente" if not texto.present else "ilegible"
        rel.unverifiable(name, f"{DOCUMENTO} {estado} (ver `deliverable`)")
        return
    raw = ctx.art.jsonl(path)
    if not raw.present:
        rel.ausente(name, f"{path} ausente")
        return
    if raw.value is None:
        rel.unverifiable(name, f"{path} ilegible (ver `schemas`)")
        return
    modelos = ctx.art.jsonl_models(path)
    todas = [
        e.output["narrative"]
        for _, e in modelos.value or []
        if e.stage == "sintesis" and isinstance(e.output.get("narrative"), str)
    ]
    # Una narrativa vacía (o en blanco) está en cualquier documento: no respalda ninguno.
    narrativas = [n for n in todas if n.strip()]
    documento = _normalizar(texto.value)
    if any(_normalizar(n) in documento for n in narrativas):
        rel.check(name, True)
    elif modelos.error is not None:
        rel.unverifiable(name, f"{path} con líneas inválidas (ver `schemas`)")
    elif todas and not narrativas:
        # Un modelo que devolvió una síntesis vacía deja un documento sin narrativa: no hay
        # texto que contrastar (ni un FAIL falso, ni una relación verificada).
        rel.unverifiable(name, f"las {len(todas)} narrativa(s) del diario están vacías")
    else:
        rel.check(name, False, f"ninguna de las {len(narrativas)} narrativas del diario")


def _meta_distinto(actual: Any, esperado: Any, donde: str = "") -> str | None:
    """Primer campo en que el meta-análisis en disco difiere del recalculado (o ``None``).

    Los números se comparan con tolerancia relativa (la misma cuenta en otra plataforma puede
    diferir en el último bit) y se ignoran los p-valores que dependen de ``scipy``. Es el JSON
    completo: una clave de más en disco (que el recálculo no tiene) también es una diferencia.
    """
    if isinstance(esperado, dict):
        if not isinstance(actual, dict):
            return donde or "raíz"
        for clave, valor in esperado.items():
            if clave in _META_SEGUN_ENTORNO:
                continue
            if clave not in actual:
                return f"{donde}.{clave}".lstrip(".")
            diferencia = _meta_distinto(actual[clave], valor, f"{donde}.{clave}")
            if diferencia is not None:
                return diferencia
        extra = next((clave for clave in actual if clave not in esperado), None)
        return None if extra is None else f"{donde}.{extra}".lstrip(".")
    if isinstance(esperado, list):
        if not isinstance(actual, list) or len(actual) != len(esperado):
            return donde or "raíz"
        for i, (a, e) in enumerate(zip(actual, esperado, strict=True)):
            diferencia = _meta_distinto(a, e, f"{donde}[{i}]")
            if diferencia is not None:
                return diferencia
        return None
    if isinstance(esperado, float) and isinstance(actual, int | float):
        if isinstance(actual, bool) or not math.isclose(
            actual, esperado, rel_tol=1e-9, abs_tol=1e-12
        ):
            return donde
        return None
    return None if actual == esperado and type(actual) is type(esperado) else donde


def _meta_analisis(ctx: AuditContext, rel: _Relations) -> None:
    """§8.1 (E1): el meta-análisis en disco es ``meta_analyze`` de los efectos del protocolo.

    Con efectos en ``00_protocol/effects.yml``, ``08_meta/meta_analysis.json`` se recalcula y se
    compara campo a campo (una estimación multiplicada por 3 deja de pasar); sin efectos, un
    meta-análisis en disco no lo escribió el motor. Su copia en el manifiesto la comparan las
    relaciones de copias. Lo que el revisor lee, ``meta_analisis.md``, y el CSV de metafor
    también son lo que el motor renderiza de ese cálculo (:func:`_meta_entregables`).
    """
    name = f"§8.1 · {META} == meta_analyze({EFECTOS_PROTOCOLO})"
    protocolo = _efectos_del_protocolo(ctx)
    if protocolo.problema:
        # Fail-closed: el motor valida `effects.yml` (y rechaza `<<`) antes de empezar, así que
        # una instantánea cuyo `effects.yml` no se lee o no valida no la escribió él. Si fuera
        # «no verificable», el auditor dejaría de exigir el meta-análisis y borrarlo (con su
        # copia, el entregable y el CSV) dejaría la corrida APTA.
        rel.check(name, False, protocolo.problema)
        return
    loaded = ctx.art.json(META)
    if protocolo.efectos is None:
        if loaded.present:
            rel.check(name, False, f"{META} sin efectos en {EFECTOS_PROTOCOLO}")
        return
    if not loaded.present:
        rel.ausente(name, f"{META} ausente con efectos en {EFECTOS_PROTOCOLO}")
    elif not loaded.ok:
        rel.unverifiable(name, f"{META} ilegible")
    else:
        diferencia = _meta_distinto(loaded.value, protocolo.resultado)
        rel.check(name, diferencia is None, f"distinto en `{short_text(diferencia)}`")
    _meta_entregables(ctx, rel, protocolo)


# Las líneas del forest con un p-valor que depende de `scipy` (el Q de heterogeneidad y el Egger:
# exactos con `scipy`, aproximados sin él): se comparan hasta el `p=`.
_P_SEGUN_ENTORNO = re.compile(r"^(- (?:Q = |Intercepto = ).*?\bp=).*$", re.MULTILINE)


def _meta_entregables(ctx: AuditContext, rel: _Relations, protocolo: _EfectosProtocolo) -> None:
    """§8.1 (E1): ``meta_analisis.md`` y el CSV de metafor son los que el motor renderiza.

    El motor los escribe con ``render_forest_markdown`` (con el ``display`` de ``effects.yml``) y
    ``render_metafor_csv`` del mismo ``meta_analyze`` que ``meta_analysis.json``: una cifra
    cambiada a mano en el informe que lee quien revisa (la estimación, un intervalo, I²) no la
    vería ninguna relación que mirara solo el JSON. Los p-valores de Q y de Egger dependen de
    ``scipy`` y no cuentan, como en el JSON; el resto del texto sí, con los saltos de línea
    normalizados (y sin el salto final del forest, que el motor no escribe).
    """
    efectos, calculo = protocolo.efectos, protocolo.calculo
    if efectos is None or calculo is None:
        return
    forest = render_forest_markdown(calculo, display=efectos.display)
    esperados = (
        (META_MD, _P_SEGUN_ENTORNO.sub(r"\1", forest)),
        (METAFOR_CSV, render_metafor_csv(calculo)),
    )
    for path, esperado in esperados:
        name = f"§8.1 · {path} == render(meta_analyze({EFECTOS_PROTOCOLO}))"
        texto = ctx.art.text(path)
        if not texto.ok:
            estado = "ausente" if not texto.present else "ilegible"
            rel.unverifiable(name, f"{path} {estado} (ver `deliverable`)")
            continue
        actual = _normalizar(texto.value)
        if path == META_MD:
            actual = _P_SEGUN_ENTORNO.sub(r"\1", actual.rstrip())
        rel.check(name, actual == esperado, "distinto del que escribe el motor")


def _diagrama_prisma(ctx: AuditContext, rel: _Relations) -> None:
    """16a (E5, FG6): ``prisma_flow.md`` es el diagrama y la tabla de ``manifest.counts``.

    El motor lo escribe con ``render_flow_diagram`` y ``render_flow_markdown`` de los mismos
    conteos que van al manifiesto: un diagrama editado a mano (otra cifra en una caja) lo
    leería quien abre el entregable sin que ninguna relación lo viera.
    """
    name = f"16a · {PRISMA_FLOW} == render(manifest.counts)"
    counts = _seccion(ctx, rel, "counts", name)
    if counts is None:
        return
    texto = ctx.art.text(PRISMA_FLOW)
    if not texto.ok:
        estado = "ausente" if not texto.present else "ilegible"
        rel.unverifiable(name, f"{PRISMA_FLOW} {estado} (ver `deliverable`)")
        return
    esperado = render_flow_diagram(counts) + "\n\n" + render_flow_markdown(counts) + "\n"
    rel.check(name, _normalizar(texto.value) == esperado, "distinto del que escribe el motor")


def _doble_extraccion_en_diario(ctx: AuditContext, rel: _Relations) -> None:
    """Relación 13 para el 2.º extractor: ``agreement.json`` se apoya en ``journal_2.jsonl``.

    El acuerdo se calcula con una extracción por estudio del subconjunto de doble extracción, y
    cada una deja su línea en el diario del 2.º extractor antes de escribir ``agreement.json``.
    Sin ``agreement.json`` no hay doble extracción (si el protocolo la declara, lo marcan
    ``§9.3`` y ``stage_artifacts``).
    """
    agreement = ctx.art.artifact(AGREEMENT)
    if not agreement.present:
        return
    path = JOURNAL_PATHS["extraccion_2"]
    name = f"13 · {AGREEMENT} respaldado por {path}"
    if not agreement.ok:
        rel.unverifiable(name, f"{AGREEMENT} inválido (ver `schemas`)")
        return
    ids = included_ids(ctx)
    if ids is None:
        rel.unverifiable(name, f"{FT} ausente o inválido")
        return
    subset = select_double_extraction_subset([SearchRecord(record_id=i, title="") for i in ids])
    diario = _diario(ctx, "extraccion_2")
    if subset and not diario.presente:
        rel.ausente(name, f"{path} ausente con {len(subset)} estudio(s) de doble extracción")
        return
    if subset and not diario.legible:
        rel.unverifiable(name, f"{path} ilegible (ver `schemas`)")
        return
    sin_linea = [r.record_id for r in subset if r.record_id not in diario.salidas]
    if sin_linea and diario.invalidas:
        rel.unverifiable(name, f"{path} con líneas inválidas (ver `schemas`)")
    else:
        rel.check(name, not sin_linea, f"sin línea: {_ids(sin_linea)}")


def collect_relations(ctx: AuditContext) -> list[_Relation]:
    """Todas las relaciones de ``arithmetic`` (la fila solo muestra las primeras de cada clase).

    Las familias de la Ola 1 (búsqueda y dedup, diarios, consolidados) solo con ``run.json``: sin
    él no existen esos artefactos y se aplican las relaciones v0.7.
    """
    rel = _Relations()
    families: list[tuple[str, Callable[[AuditContext, _Relations], None]]] = [
        ("relaciones del embudo", _funnel),
        ("relaciones de los incluidos", _included_artifacts),
        ("relaciones del CSV PRISMA2020", _csv),
        ("relaciones de las llamadas IA", _calls),
        ("relaciones de las métricas", _metrics),
        ("relaciones de las copias del manifiesto", _copies),
    ]
    if _ola1(ctx):
        families[1:1] = [("relaciones de la búsqueda y el dedup", _busqueda_y_dedup)]
        families += [
            ("relaciones de los diarios (12)", _diarios),
            ("relaciones de los consolidados (13)", _consolidados),
            ("relaciones del meta-análisis (§8.1)", _meta_analisis),
            ("relaciones del diagrama PRISMA (16a)", _diagrama_prisma),
        ]
    for family, fn in families:
        rel.guard(family, partial(fn, ctx, rel))
    return rel.items


def check_arithmetic(ctx: AuditContext) -> Verdict:
    """PRISMA 16 / trAIce R1: los artefactos cuadran entre sí (§4.4, §9.3)."""
    if ctx.manifest_dict is None:
        return "N/A", NA_MANIFIESTO
    relations = collect_relations(ctx)
    broken = [f"{r.name}: {r.detail}" for r in relations if r.ok is False]
    unverifiable = [f"{r.name} ({r.detail})" for r in relations if r.ok is None]
    verified = sum(1 for r in relations if r.ok)
    mode = "" if _ola1(ctx) else " (relaciones v0.7: corrida sin run.json)"
    if broken:
        return "FAIL", f"{len(broken)} relación(es) rota(s){mode}: {_limitar(broken)}."
    if unverifiable:
        return "WARN", (
            f"{verified} relaciones verificadas{mode}; no verificables: {_limitar(unverifiable)}."
        )
    return "PASS", f"{verified} relaciones verificadas{mode}."


def check_exclusions(ctx: AuditContext) -> Verdict:
    """trAIce R1: el desglose humano/IA coincide con el recálculo desde las decisiones."""
    loaded = ctx.art.artifact("03_screening/exclusions.json")
    if not loaded.present:
        return "FAIL", "03_screening/exclusions.json ausente: sin desglose humano/IA (trAIce R1)."
    if not loaded.ok:
        error = short_text(loaded.error, limit=_LIMITE_ERROR)
        return "FAIL", f"03_screening/exclusions.json inválido ({error})."
    ta, ft = ctx.art.artifact(TA), ctx.art.artifact(FT)
    if not (ta.ok and ft.ok):
        return "FAIL", (
            f"no se puede recalcular el desglose: falta o no valida {TA if not ta.ok else FT}."
        )
    declared = loaded.value
    recomputed = compute_exclusion_breakdown([*ta.value, *ft.value])
    diffs = [
        f"{field} {_n(getattr(declared, field))} ≠ {_n(getattr(recomputed, field))}"
        for field in type(recomputed).model_fields
        if getattr(declared, field) != getattr(recomputed, field)
    ]
    unverifiable: list[str] = []
    pendiente = ""
    counts = ctx.manifest_section("counts")
    if not counts.present:
        # El motor escribe el manifiesto al evaluar el gate final (spec §4.2): una corrida
        # detenida antes (pausa, rechazo o interrupción en extracción o RoB) todavía no lo tiene
        # y exigirlo daría un FAIL falso. Desde `reporte` es manipulación (`state.reached`).
        if "reporte" in ctx.state.reached:
            diffs.append("counts ausente en el manifiesto (el motor siempre lo escribe)")
        else:
            if ctx.manifest_dict is None:
                pendiente = " El manifiesto aún no existe: sus conteos se verificarán al reanudar."
            else:
                pendiente = " sin conteos en el manifiesto todavía: se verificarán al reanudar."
    elif not counts.ok:
        unverifiable.append("manifest.counts inválido (ver `schemas`)")
    elif counts.value.excluded_ta_human is None and counts.value.excluded_ta_ai is None:
        if _ola1(ctx):
            # El motor de la Ola 1 escribe siempre el desglose: que falte es manipulación.
            diffs.append("counts sin excluded_ta_human/ai (el motor escribe ambos)")
        else:
            # Un manifiesto anterior al desglose humano/IA pudo no traerlos: no se sabe.
            unverifiable.append("counts sin excluded_ta_human/ai (manifiesto sin desglose)")
    elif counts.value.excluded_ta_human is None or counts.value.excluded_ta_ai is None:
        diffs.append("counts con solo uno de excluded_ta_human/ai (el motor escribe ambos)")
    else:
        ta_only = compute_exclusion_breakdown(ta.value)
        c = counts.value
        if (c.excluded_ta_human, c.excluded_ta_ai) != (ta_only.excluded_human, ta_only.excluded_ai):
            diffs.append(
                f"counts.excluded_ta_human/ai {_n(c.excluded_ta_human)}/{_n(c.excluded_ta_ai)} ≠ "
                f"{_n(ta_only.excluded_human)}/{_n(ta_only.excluded_ai)} (solo T/A)"
            )
    if diffs:
        return "FAIL", f"distinto del recálculo desde las decisiones: {'; '.join(diffs)}."
    if unverifiable:
        return "WARN", (
            f"coincide con el recálculo ({recomputed.total_excluded} exclusiones) pero no se "
            f"pudo verificar: {'; '.join(unverifiable)}."
        )
    return "PASS", (
        f"coincide con el recálculo: {recomputed.total_excluded} exclusiones "
        f"({recomputed.excluded_human} humanas, {recomputed.excluded_ai} IA).{pendiente}"
    )


def check_deliverable(ctx: AuditContext) -> Verdict:
    """PRISMA 16/16b/17/18/27: entregable completo y sin ficheros vacíos."""
    required = list(DELIVERABLE_FILES)
    if ctx.art.exists("run.json"):
        required.append("excluidos_texto_completo.md")  # 16b (desde la Ola 1)
    protocolo = _efectos_del_protocolo(ctx)
    if (
        "meta_analysis" in (ctx.manifest_dict or {})
        or ctx.art.exists(META)
        or protocolo.efectos is not None
    ):
        required.append("meta_analisis.md")
    if protocolo.efectos is not None:
        # Con efectos en la instantánea el motor escribe siempre el CSV de metafor (E1).
        required.append("interop/effects_metafor.csv")
    problems: list[str] = []
    for name in required:
        loaded = ctx.art.text(f"deliverable/{name}")
        if not loaded.present:
            problems.append(f"{name} (falta)")
        elif not loaded.ok or not loaded.value.strip():
            reason = "vacío" if loaded.ok else short_text(loaded.error, limit=_LIMITE_ERROR)
            problems.append(f"{name} ({reason})")
    if problems:
        return "FAIL", f"Entregable incompleto: {_limitar(problems)}."
    aviso = _meta_sin_incluidos(ctx, protocolo)
    if aviso is not None:
        return "WARN", f"Entregable completo ({len(required)} artefactos); {aviso}."
    return "PASS", f"Entregable completo ({len(required)} artefactos)."


def _meta_sin_incluidos(ctx: AuditContext, protocolo: _EfectosProtocolo) -> str | None:
    """WARN si algún estudio del meta-análisis no está entre los incluidos, o no hay incluidos (E1).

    El meta-análisis usa los efectos declarados en ``effects.yml``, no los derivados de la
    extracción: ligarlo a los incluidos queda para la Ola 2. No es un FAIL (el demo tiene k = 4
    con menos incluidos), pero el entregable presenta un meta-análisis ajeno a la selección. Es
    la misma condición con la que ``metodologia.md`` lo declara (``exports.methods``): cualquier
    ``study_id`` fuera de los incluidos, o cero incluidos; no solo k mayor que los incluidos.
    """
    if protocolo.efectos is None:
        return None
    estudios = [e.study_id for e in protocolo.efectos.effects]
    ids = included_ids(ctx)
    if ids is None:
        return None
    fuera = sorted(set(estudios) - set(ids))
    if ids and not fuera:
        return None
    cuales = (
        "la revisión no incluyó ningún estudio"
        if not ids
        else (
            f"{len(fuera)} de los {len(estudios)} estudios del meta-análisis no están entre los "
            f"{len(ids)} incluidos ({_ids(fuera)})"
        )
    )
    return (
        f"los efectos de {EFECTOS_PROTOCOLO} no salen de la extracción de esta corrida (Ola 2): "
        f"{cuales}. `metodologia.md` ya lo declara con ⚠; mantén esa declaración en el manuscrito"
    )
