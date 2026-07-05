"""Exportador de la tabla de características de los estudios incluidos.

Convierte los formularios de extracción (``ExtractionRecord``) en una tabla
Markdown legible — el "Table 1 / Characteristics of included studies" que toda
revisión sistemática necesita. Determinista (sin red ni LLM). Las columnas son
la unión ordenada de los campos definidos en ``extraction_form.yml``; los campos
``needs_review`` se marcan para que el revisor humano sepa qué auditar.
"""

from __future__ import annotations

from prisma_loop.schemas.extraction import ExtractionRecord
from prisma_loop.schemas.records import SearchRecord

_TITLE = "# Características de los estudios incluidos"
_LEGEND = "_⚠️ = campo pendiente de verificación humana (needs_review)._"


def _cell(value: str) -> str:
    """Escapa un valor para una celda de tabla Markdown (sin pipes ni saltos)."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def render_extraction_table(
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
) -> str:
    """Renderiza la tabla de extracción de los estudios incluidos."""
    lines = [_TITLE, ""]
    if not included:
        lines.append("_(sin estudios incluidos)_")
        return "\n".join(lines)

    # Unión ordenada de los campos extraídos (preserva el orden de aparición).
    keys: list[str] = []
    for record in included:
        extraction = extractions.get(record.record_id)
        if extraction:
            for key in extraction.fields:
                if key not in keys:
                    keys.append(key)

    # Sin campos extraídos: tabla mínima estudio + título.
    if not keys:
        lines += ["| Estudio | Título |", "|---|---|"]
        for record in included:
            lines.append(f"| {_cell(record.record_id)} | {_cell(record.title)} |")
        return "\n".join(lines)

    lines.append("| Estudio | " + " | ".join(_cell(k) for k in keys) + " |")
    lines.append("|---|" + "|".join("---" for _ in keys) + "|")
    for record in included:
        extraction = extractions.get(record.record_id)
        cells: list[str] = []
        for key in keys:
            field = extraction.fields.get(key) if extraction else None
            if field is None or field.value is None:
                cells.append("—")
            else:
                mark = " ⚠️" if field.status == "needs_review" else ""
                cells.append(_cell(field.value) + mark)
        lines.append(f"| {_cell(record.record_id)} | " + " | ".join(cells) + " |")

    lines += ["", _LEGEND]
    return "\n".join(lines)
