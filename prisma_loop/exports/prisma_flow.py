"""Diagrama de flujo PRISMA 2020 · plantillas oficiales, con conteos reales.

Implementa la estructura de las **plantillas oficiales** del flow diagram
PRISMA 2020 (CC BY 4.0; Page MJ, et al. BMJ 2021;372:n71):

- **v1 · nuevas revisiones, solo bases de datos/registros** — el render por
  defecto, con las cajas oficiales: identificación (con desglose por base),
  eliminados antes del cribado (duplicados / automatización / otros), cribados,
  excluidos (con separación humano vs IA — nota ** de la plantilla oficial y
  requisito PRISMA-trAIce R1), informes buscados / no recuperados / evaluados,
  excluidos con **razones**, e incluidos.
- **v3 · revisiones actualizadas** — :func:`render_flow_updated` añade la
  columna "estudios de la versión previa" y los totales nuevos/acumulados;
  se alimenta de la memoria del investigador (living review).

Todo se computa de forma determinista del recorrido real del pipeline y se
renderiza como Mermaid (portable, versionable) + tabla Markdown.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

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
        fulltext_assessed: informes evaluados para elegibilidad.
        fulltext_abstract_only: de los evaluados, cuántos sin texto completo
            recuperable (se evaluaron con título/abstract; limitación declarada).
        excluded_ft: excluidos en la evaluación de elegibilidad.
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
    fulltext_assessed: int = 0
    fulltext_abstract_only: int = 0
    excluded_ft: int = 0
    ft_exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    included: int = 0


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


def _reason_lines(counts: PrismaCounts) -> str:
    if not counts.ft_exclusion_reasons:
        return ""
    ordered = sorted(counts.ft_exclusion_reasons.items(), key=lambda kv: (-kv[1], kv[0]))
    return "".join(f"<br/>{reason} (n = {n})" for reason, n in ordered)


def render_flow_diagram(counts: PrismaCounts) -> str:
    """Renderiza el flow diagram PRISMA 2020 (plantilla v1 oficial) en Mermaid."""
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
        f'        E["Informes evaluados para elegibilidad (n = {counts.fulltext_assessed})'
        + (
            f"<br/>(sin texto completo recuperable: n = {counts.fulltext_abstract_only})***"
            if counts.fulltext_abstract_only
            else ""
        )
        + '"]',
        f'        F["Informes excluidos (n = {counts.excluded_ft})' f'{_reason_lines(counts)}"]',
        "        C --> D",
        "        C --> E",
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
    if counts.fulltext_abstract_only:
        lines.append(
            "\\*** El motor evalúa la elegibilidad de todos los informes; los que no "
            "tienen texto completo en abierto se evalúan con título/abstract "
            "(limitación declarada, cuenta como 'no recuperado' a efectos de lectura)."
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
        f'        P["Estudios incluidos en la versión anterior (n = {previous_included})"' "]",
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
        ("Informes evaluados para elegibilidad", counts.fulltext_assessed),
    ]
    if counts.fulltext_abstract_only:
        rows.append(("— evaluados sin texto completo (solo T/A)", counts.fulltext_abstract_only))
    rows.append(("Excluidos en elegibilidad", counts.excluded_ft))
    for reason, n in sorted(counts.ft_exclusion_reasons.items(), key=lambda kv: (-kv[1], kv[0])):
        rows.append((f"— razón: {reason}", n))
    rows.append(("Incluidos", counts.included))
    lines = ["| Etapa | n |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    return "\n".join(lines)
