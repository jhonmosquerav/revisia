"""Diagrama de flujo PRISMA 2020 · plantillas oficiales, con conteos reales.

Implementa la estructura de las **plantillas oficiales** del flow diagram
PRISMA 2020 (CC BY 4.0; Page MJ, et al. BMJ 2021;372:n71):

- **v1 · nuevas revisiones, solo bases de datos/registros** — el render por
  defecto, con las cajas oficiales: identificación (con desglose por base),
  eliminados antes del cribado (duplicados / automatización / otros), cribados,
  excluidos (con separación humano vs IA — nota ** de la plantilla oficial y
  requisito PRISMA-trAIce R1), informes buscados / no recuperados / evaluados,
  excluidos con **razones** (también humano vs IA), e incluidos. Un informe sin
  texto completo no se evalúa: cuenta como "no recuperado" (PRISMA estricto, D2
  de la Ola 1; auditoría 2026-09-03, M11).
- **v3 · revisiones actualizadas** — :func:`render_flow_updated` añade la
  columna "estudios de la versión previa" y los totales nuevos/acumulados;
  se alimenta de la memoria del investigador (living review).

Todo se computa de forma determinista del recorrido real del pipeline y se
renderiza como Mermaid (portable, versionable) + tabla Markdown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from revisia.schemas.artifacts import ExcludedReport

_FOOTER = (
    "\n> Estructura de cajas según la plantilla oficial PRISMA 2020 (CC BY 4.0). "
    "Fuente: Page MJ, et al. BMJ 2021;372:n71. doi:10.1136/bmj.n71."
)


class PrismaCounts(BaseModel):
    """Conteos del flujo PRISMA 2020 (plantilla oficial v1).

    Attributes:
        identified: registros identificados en las búsquedas.
        identified_by_source: desglose por base (nota * de la plantilla oficial).
        duplicates_removed: duplicados eliminados antes del cribado.
        removed_automation: marcados inelegibles por herramientas automáticas
            antes del cribado (caja oficial; 0 si el motor no pre-filtra).
        removed_other: eliminados por otras razones antes del cribado.
        screened: registros cribados (título/abstract).
        excluded_ta: excluidos en cribado de título/abstract.
        excluded_ta_human: de los excluidos en T/A, cuántos por decisión humana
            (nota ** de la plantilla oficial · PRISMA-trAIce R1).
        excluded_ta_ai: de los excluidos en T/A, cuántos por la IA sin
            intervención humana.
        fulltext_sought: informes buscados para recuperación (pasaron T/A).
        fulltext_not_retrieved: informes buscados que no se recuperaron y que
            nadie rescató (caja "informes no recuperados").
        fulltext_rescued: no recuperados que el revisor consiguió por otra vía
            y evaluó (D2); cuentan como evaluados.
        fulltext_assessed: informes evaluados para elegibilidad
            (``fulltext_sought − fulltext_not_retrieved``).
        excluded_ft: excluidos en la evaluación de elegibilidad.
        excluded_ft_human: de los excluidos en elegibilidad, cuántos por
            decisión humana (PRISMA-trAIce R1).
        excluded_ft_ai: de los excluidos en elegibilidad, cuántos por la IA.
        ft_exclusion_reasons: razones de exclusión en texto completo → n
            (cajas "Reason 1..n" de la plantilla oficial).
        included: estudios incluidos en la síntesis.
    """

    identified: int = 0
    identified_by_source: dict[str, int] = Field(default_factory=dict)
    duplicates_removed: int = 0
    removed_automation: int = 0
    removed_other: int = 0
    screened: int = 0
    excluded_ta: int = 0
    excluded_ta_human: int | None = None
    excluded_ta_ai: int | None = None
    fulltext_sought: int = 0
    fulltext_not_retrieved: int = 0
    fulltext_rescued: int = 0
    fulltext_assessed: int = 0
    excluded_ft: int = 0
    excluded_ft_human: int = 0
    excluded_ft_ai: int = 0
    ft_exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    included: int = 0

    @model_validator(mode="before")
    @classmethod
    def _manifiesto_anterior_a_la_ola_1(cls, data: object) -> object:
        """Lee los conteos de un manifiesto v0.7 sin inventar nada (D13).

        Antes de la Ola 1 no existía ``fulltext_sought``: todo registro que
        pasaba T/A se "evaluaba" (con el abstract si no había texto completo) y
        ningún humano etiquetaba registros. Lo que de verdad pasó: buscados =
        evaluados, no recuperados = 0 y todas las exclusiones en elegibilidad
        son de la IA. ``fulltext_abstract_only`` se retira (contaba evaluaciones
        con el abstract, que ya no existen, D2).
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        data.pop("fulltext_abstract_only", None)
        if "fulltext_sought" not in data:
            data["fulltext_sought"] = data.get("fulltext_assessed", 0)
            data.setdefault("fulltext_not_retrieved", 0)
            if "excluded_ft_human" not in data and "excluded_ft_ai" not in data:
                data["excluded_ft_human"] = 0
                data["excluded_ft_ai"] = data.get("excluded_ft", 0)
        return data


def _by_source_lines(counts: PrismaCounts) -> str:
    if not counts.identified_by_source:
        return ""
    parts = [f"{db} (n = {n})" for db, n in sorted(counts.identified_by_source.items())]
    return "<br/>" + " · ".join(parts)


def _ta_split(counts: PrismaCounts) -> str:
    if counts.excluded_ta_human is None and counts.excluded_ta_ai is None:
        return ""
    human = counts.excluded_ta_human or 0
    ai = counts.excluded_ta_ai or 0
    return f"<br/>por humano (n = {human}) · por IA (n = {ai})**"


def _ft_split(counts: PrismaCounts) -> str:
    return (
        f"<br/>por humano (n = {counts.excluded_ft_human}) · por IA (n = {counts.excluded_ft_ai})**"
    )


def _reason_lines(counts: PrismaCounts) -> str:
    if not counts.ft_exclusion_reasons:
        return ""
    ordered = sorted(counts.ft_exclusion_reasons.items(), key=lambda kv: (-kv[1], kv[0]))
    return "".join(f"<br/>{reason} (n = {n})" for reason, n in ordered)


def render_flow_diagram(counts: PrismaCounts) -> str:
    """Renderiza el flow diagram PRISMA 2020 (plantilla v1 oficial) en Mermaid."""
    rescued = (
        f"<br/>(rescatados por el revisor: n = {counts.fulltext_rescued})***"
        if counts.fulltext_rescued
        else ""
    )
    lines = [
        "```mermaid",
        "flowchart TB",
        '    subgraph FASE_ID["Identificación de estudios vía bases de datos y registros"]',
        f'        A["Registros identificados (n = {counts.identified})*'
        f'{_by_source_lines(counts)}"]',
        '        B["Registros eliminados antes del cribado:'
        f"<br/>Duplicados (n = {counts.duplicates_removed})"
        f"<br/>Marcados inelegibles por automatización (n = {counts.removed_automation})"
        f'<br/>Otras razones (n = {counts.removed_other})"]',
        "        A --> B",
        "    end",
        '    subgraph FASE_SCR["Cribado"]',
        f'        C["Registros cribados (n = {counts.screened})"]',
        f'        D["Registros excluidos (n = {counts.excluded_ta}){_ta_split(counts)}"]',
        f'        S["Informes buscados para recuperación (n = {counts.fulltext_sought})"]',
        f'        N["Informes no recuperados (n = {counts.fulltext_not_retrieved})"]',
        f'        E["Informes evaluados para elegibilidad (n = {counts.fulltext_assessed})'
        f'{rescued}"]',
        f'        F["Informes excluidos (n = {counts.excluded_ft}){_ft_split(counts)}'
        f'{_reason_lines(counts)}"]',
        "        C --> D",
        "        C --> S",
        "        S --> N",
        "        S --> E",
        "        E --> F",
        "    end",
        '    subgraph FASE_INC["Incluidos"]',
        f'        G["Estudios incluidos en la revisión (n = {counts.included})'
        f'<br/>Informes de estudios incluidos (n = {counts.included})"]',
        "    end",
        "    A --> C",
        "    E --> G",
        "```",
        "",
        "\\* Desglose por base cuando el motor lo conoce (nota de la plantilla oficial).",
        "\\** Separación de exclusiones humano vs automatización: nota ** de la "
        "plantilla oficial y requisito PRISMA-trAIce (ítem R1).",
    ]
    if counts.fulltext_rescued:
        lines.append(
            "\\*** Informes que el motor no pudo recuperar en abierto y que el revisor "
            "consiguió por otra vía: los evaluó el humano, no la IA."
        )
    lines.append(_FOOTER)
    return "\n".join(lines)


def render_flow_updated(
    counts: PrismaCounts,
    *,
    previous_included: int,
    new_included: int,
    dropped_from_previous: int = 0,
) -> str:
    """Flow diagram para **revisiones actualizadas** (plantilla v3 · living review).

    Se alimenta de la memoria del investigador (``--brain``): la corrida previa
    aporta la columna "estudios incluidos en la versión anterior" y esta corrida
    los nuevos; el total consolida ambos (menos los retirados).
    """
    total = previous_included - dropped_from_previous + new_included
    lines = [
        "```mermaid",
        "flowchart TB",
        '    subgraph PREV["Estudios previos"]',
        f'        P["Estudios incluidos en la versión anterior (n = {previous_included})"]',
        "    end",
        '    subgraph NEW["Identificación de nuevos estudios (esta corrida)"]',
        f'        A["Registros identificados (n = {counts.identified})"]',
        f'        C["Registros cribados (n = {counts.screened})"]',
        f'        E["Informes evaluados (n = {counts.fulltext_assessed})"]',
        f'        N["Estudios nuevos incluidos (n = {new_included})"]',
        "        A --> C",
        "        C --> E",
        "        E --> N",
        "    end",
        '    subgraph TOT["Incluidos (acumulado)"]',
        f'        T["Total de estudios incluidos en la revisión (n = {total})'
        + (
            f"<br/>Retirados de la versión anterior (n = {dropped_from_previous})"
            if dropped_from_previous
            else ""
        )
        + '"]',
        "    end",
        "    P --> T",
        "    N --> T",
        "```",
        "",
        "> Plantilla oficial v3 (revisiones actualizadas) alimentada por la memoria "
        "del investigador (living review).",
        _FOOTER,
    ]
    return "\n".join(lines)


def render_flow_markdown(counts: PrismaCounts) -> str:
    """Renderiza los conteos como tabla Markdown (todas las cajas oficiales)."""
    rows: list[tuple[str, object]] = [
        ("Identificados", counts.identified),
    ]
    for db, n in sorted(counts.identified_by_source.items()):
        rows.append((f"— identificados en {db}", n))
    rows += [
        ("Duplicados eliminados", counts.duplicates_removed),
        ("Marcados inelegibles por automatización (pre-cribado)", counts.removed_automation),
        ("Eliminados por otras razones (pre-cribado)", counts.removed_other),
        ("Cribados (T/A)", counts.screened),
        ("Excluidos en T/A", counts.excluded_ta),
    ]
    if counts.excluded_ta_human is not None or counts.excluded_ta_ai is not None:
        rows += [
            ("— excluidos por humano", counts.excluded_ta_human or 0),
            ("— excluidos por IA", counts.excluded_ta_ai or 0),
        ]
    rows += [
        ("Informes buscados para recuperación", counts.fulltext_sought),
        ("Informes no recuperados", counts.fulltext_not_retrieved),
        ("Informes evaluados para elegibilidad", counts.fulltext_assessed),
    ]
    if counts.fulltext_rescued:
        rows.append(("— rescatados por el revisor", counts.fulltext_rescued))
    rows += [
        ("Excluidos en elegibilidad", counts.excluded_ft),
        ("— excluidos por humano (elegibilidad)", counts.excluded_ft_human),
        ("— excluidos por IA (elegibilidad)", counts.excluded_ft_ai),
    ]
    for reason, n in sorted(counts.ft_exclusion_reasons.items(), key=lambda kv: (-kv[1], kv[0])):
        rows.append((f"— razón: {reason}", n))
    rows.append(("Incluidos", counts.included))
    lines = ["| Etapa | n |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    return "\n".join(lines)


_ORIGEN = {"human": "humano", "ai": "IA"}


def _md_cell(value: object) -> str:
    """Celda de tabla Markdown: una sola línea y con ``|`` escapado."""
    return " ".join(str(value).split()).replace("|", "\\|")


def render_excluded_reports(reports: list[ExcludedReport]) -> str:
    """Informes excluidos en elegibilidad con su razón (PRISMA 2020, ítem 16b).

    Va a ``deliverable/excluidos_texto_completo.md``. Cada fila dice si la razón
    la dio un humano o la IA (PRISMA-trAIce R1): una exclusión de la IA que
    nadie revisó no se presenta como juicio humano.
    """
    lines = [
        "# Informes excluidos tras evaluar el texto completo",
        "",
        "PRISMA 2020, ítem 16b: informes evaluados para elegibilidad y excluidos, "
        "con su razón y quién la dio (PRISMA-trAIce R1).",
        "",
    ]
    if not reports:
        lines.append("_(ningún informe excluido en la evaluación de elegibilidad)_")
        return "\n".join(lines) + "\n"
    lines += ["| Informe | Año | DOI | Razón | Origen |", "|---|---|---|---|---|"]
    for rep in reports:
        year = "—" if rep.year is None else str(rep.year)
        doi = _md_cell(rep.doi) if rep.doi else "—"
        lines.append(
            f"| {_md_cell(rep.title)} (`{_md_cell(rep.record_id)}`) | {year} | {doi} "
            f"| {_md_cell(rep.reason)} | {_ORIGEN[rep.reason_source]} |"
        )
    return "\n".join(lines) + "\n"
