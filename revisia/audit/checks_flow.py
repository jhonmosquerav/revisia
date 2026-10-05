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
(``counts`` y ``protocol`` del manifiesto, las decisiones, extracciones y evaluaciones, el CSV
PRISMA2020 legible, ``agreement.json`` cuando el protocolo declara un 2.º extractor y hay
incluidos) y falta es manipulación, así que la relación queda rota; el WARN se reserva para lo
que de verdad no se puede saber (un valor que no valida y marca ``schemas``, o un dato que
manifiestos antiguos pudieron no traer, como ``excluded_ta_human/ai``).
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

from revisia.audit.artifacts import NA_MANIFIESTO, AuditContext, short_repr, short_text
from revisia.audit.model import Verdict
from revisia.config import ReviewProtocol
from revisia.exclusions import compute_exclusion_breakdown
from revisia.extraction_agreement import select_double_extraction_subset
from revisia.llm.ensemble import recall_biased_label
from revisia.metrics import kappa_from_matrix, mcc, wmcc
from revisia.schemas.records import SearchRecord

TA = "03_screening/decisions.json"
FT = "04_fulltext/decisions.json"
CSV = "deliverable/interop/prisma2020_flow.csv"
EXTRACTIONS = "05_extraction/extractions.json"
ASSESSMENTS = "07_rob/assessments.json"
AGREEMENT = "05_extraction/agreement.json"
EXCLUSIONS = "03_screening/exclusions.json"

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


def _acotar_item(item: str) -> str:
    """``item`` recortado a ``_LIMITE_ITEM`` sin partir el ``(+k más)`` que ``_ids`` dejó dentro.

    Cortar a ciegas daba «…, rrr… (+4 …»: el lector no sabía cuántos ids faltaban (revisión de la
    Tarea 7). Si el corte caería dentro de un sufijo (o antes de él), se recorta el contenido que
    lo precede y el sufijo se añade entero.
    """
    if len(item) > _LIMITE_ITEM:
        for sufijo in _SUFIJO_MAS.finditer(item):
            if sufijo.end() > _LIMITE_ITEM - 1:
                cola = " …" if item[sufijo.end() :] else ""
                reservado = len(sufijo.group()) + len(cola)
                contenido = short_text(item[: sufijo.start()], limit=_LIMITE_ITEM - reservado)
                return contenido + sufijo.group() + cola
    return short_text(item, limit=_LIMITE_ITEM)


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


def _ids_incluidos(ft: Sequence[Any]) -> list[str]:
    """Ids incluidos en unas decisiones a texto completo ya cargadas (``include`` o ``unclear``)."""
    return [d.record_id for d in ft if d.final_label in {"include", "unclear"}]


def included_ids(ctx: AuditContext) -> list[str] | None:
    """Incluidos según las decisiones a texto completo (``None`` si no se leen).

    Relaciones v0.7 (sin ``run.json``): ``include`` o ``unclear``.
    """
    ft = ctx.art.artifact(FT)
    return _ids_incluidos(ft.value) if ft.ok else None


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
    missing = [f"{stage}: {rel}" for stage, rel in required if not ctx.art.exists(rel)]
    if missing:
        return "FAIL", f"faltan artefactos de etapas alcanzadas: {_limitar(missing)}."
    stages = sorted({stage for stage, _ in required}, key=list(STAGE_ARTIFACTS).index)
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
        _texto_completo(rel, counts, ta, ft)
    elif ft is not None:
        rel.unverifiable("relaciones del texto completo", f"dependen de {TA} (ver arriba)")


def _cribado_ta(ctx: AuditContext, rel: _Relations, counts: Any, ta: list[Any]) -> None:
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


def _texto_completo(rel: _Relations, counts: Any, ta: list[Any], ft: list[Any]) -> None:
    passed = {d.record_id for d in ta if d.final_label in {"include", "unclear"}}
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
        len(_ids_incluidos(ft)),
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
    expected = {
        "database_results": c.identified,
        "duplicates": c.duplicates_removed,
        "records_screened": c.screened,
        "records_excluded": c.excluded_ta,
        "dbr_sought_reports": c.fulltext_assessed,  # v0.7: buscados = evaluados
        "dbr_notretrieved_reports": 0,
        "dbr_assessed": c.fulltext_assessed,
        "new_studies": c.included,
    }
    for key, value in expected.items():
        rel.eq(f"11 · CSV {key}", leido.values.get(key), str(value))


def _calls(ctx: AuditContext, rel: _Relations) -> None:
    manifest = ctx.manifest_dict or {}
    calls = ctx.llm_calls
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
    declared = manifest.get("models_used")
    if not (isinstance(declared, list) and all(isinstance(m, str) for m in declared)):
        rel.unverifiable(name, "models_used no es una lista de cadenas (ver `schemas`)")
    elif malformed:
        rel.unverifiable(
            name, f"{malformed} llamada(s) sin provider/model textuales (ver `schemas`)"
        )
    else:
        rel.check(
            name,
            sorted(declared) == sorted(models),
            f"declarados {_ids(sorted(declared))}; en llamadas {_ids(sorted(models))}",
        )
    rel.eq(
        "§9.3 · deterministic_token_level == all(deterministic)",
        manifest.get("deterministic_token_level"),
        all(c.get("deterministic") is True for c in calls) if calls else True,
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
    if ctx.run_info is None:
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
    rel.check(
        "§9.3 · llamadas ≥ cota inferior de las decisiones",
        len(calls) >= floor,
        f"{len(calls)} llamadas < {_n(floor)} = {_n(c.screened)}·{members} + {_n(by_ai)} + "
        f"2·{_n(c.included)} + {_n(doubles)} + 1",
    )


def _metrics(ctx: AuditContext, rel: _Relations) -> None:
    loaded = ctx.art.artifact("03_screening/metrics.json")
    if not loaded.present:
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


def _copies(ctx: AuditContext, rel: _Relations) -> None:
    manifest = ctx.manifest_dict or {}
    for key, path in MANIFEST_COPIES.items():
        loaded = ctx.art.json(path)
        if key not in manifest and not loaded.present:
            if key == "extraction_agreement" and _requiere_doble_extraccion(ctx):
                rel.check(
                    f"§9.3 · copia `{key}` del manifiesto",
                    False,
                    f"{path} y su copia ausentes (el protocolo declara un 2.º extractor)",
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


def collect_relations(ctx: AuditContext) -> list[_Relation]:
    """Todas las relaciones de ``arithmetic`` (la fila solo muestra las primeras de cada clase)."""
    rel = _Relations()
    families: tuple[tuple[str, Callable[[AuditContext, _Relations], None]], ...] = (
        ("relaciones del embudo", _funnel),
        ("relaciones de los incluidos", _included_artifacts),
        ("relaciones del CSV PRISMA2020", _csv),
        ("relaciones de las llamadas IA", _calls),
        ("relaciones de las métricas", _metrics),
        ("relaciones de las copias del manifiesto", _copies),
    )
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
    mode = " (relaciones v0.7: corrida sin run.json)" if ctx.run_info is None else ""
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
    counts = ctx.manifest_section("counts")
    if not counts.present:
        diffs.append("counts ausente en el manifiesto (el motor siempre lo escribe)")
    elif not counts.ok:
        unverifiable.append("manifest.counts inválido (ver `schemas`)")
    elif counts.value.excluded_ta_human is None and counts.value.excluded_ta_ai is None:
        # Un manifiesto anterior al desglose humano/IA pudo no traerlos: no se puede saber.
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
        f"({recomputed.excluded_human} humanas, {recomputed.excluded_ai} IA)."
    )


def check_deliverable(ctx: AuditContext) -> Verdict:
    """PRISMA 16/16b/17/18/27: entregable completo y sin ficheros vacíos."""
    required = list(DELIVERABLE_FILES)
    if "meta_analysis" in (ctx.manifest_dict or {}) or ctx.art.exists("08_meta/meta_analysis.json"):
        required.append("meta_analisis.md")
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
    return "PASS", f"Entregable completo ({len(required)} artefactos)."
