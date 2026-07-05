"""Diagrama de flujo PRISMA 2020 · conteos por etapa (determinista).

El diagrama de cuatro fases (identificación → cribado → elegibilidad →
inclusión) con conteos es obligatorio en PRISMA 2020. Aquí se computa de forma
determinista a partir del recorrido real del pipeline y se renderiza como
Mermaid (portable, versionable en texto) y como tabla Markdown.
"""

from __future__ import annotations

from pydantic import BaseModel


class PrismaCounts(BaseModel):
    """Conteos del flujo PRISMA 2020.

    Attributes:
        identified: registros identificados en las búsquedas.
        duplicates_removed: duplicados eliminados antes del cribado.
        screened: registros cribados (título/abstract).
        excluded_ta: excluidos en cribado de título/abstract.
        fulltext_assessed: registros evaluados a texto completo.
        excluded_ft: excluidos en texto completo.
        included: estudios incluidos en la síntesis.
    """

    identified: int = 0
    duplicates_removed: int = 0
    screened: int = 0
    excluded_ta: int = 0
    fulltext_assessed: int = 0
    excluded_ft: int = 0
    included: int = 0


def render_flow_diagram(counts: PrismaCounts) -> str:
    """Renderiza el diagrama de flujo PRISMA 2020 en Mermaid."""
    return "\n".join(
        [
            "```mermaid",
            "flowchart TD",
            f'    A["Registros identificados\\n(n = {counts.identified})"]',
            f'    B["Duplicados eliminados\\n(n = {counts.duplicates_removed})"]',
            f'    C["Registros cribados\\n(n = {counts.screened})"]',
            f'    D["Excluidos en título/abstract\\n(n = {counts.excluded_ta})"]',
            f'    E["Evaluados a texto completo\\n(n = {counts.fulltext_assessed})"]',
            f'    F["Excluidos en texto completo\\n(n = {counts.excluded_ft})"]',
            f'    G["Estudios incluidos\\n(n = {counts.included})"]',
            "    A --> B",
            "    A --> C",
            "    C --> D",
            "    C --> E",
            "    E --> F",
            "    E --> G",
            "```",
        ]
    )


def render_flow_markdown(counts: PrismaCounts) -> str:
    """Renderiza los conteos como tabla Markdown."""
    rows = [
        ("Identificados", counts.identified),
        ("Duplicados eliminados", counts.duplicates_removed),
        ("Cribados (T/A)", counts.screened),
        ("Excluidos en T/A", counts.excluded_ta),
        ("Evaluados a texto completo", counts.fulltext_assessed),
        ("Excluidos en texto completo", counts.excluded_ft),
        ("Incluidos", counts.included),
    ]
    lines = ["| Etapa | n |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    return "\n".join(lines)
