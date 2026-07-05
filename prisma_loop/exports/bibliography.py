"""Exportador de bibliografía · BibTeX de los estudios incluidos.

Determinista: a partir de los ``SearchRecord`` incluidos produce un ``.bib``
estable (sin red ni LLM). La clave de cita se deriva del ``record_id`` (idealmente
el DOI), garantizando unicidad y reproducibilidad entre corridas.
"""

from __future__ import annotations

from prisma_loop.schemas.records import SearchRecord


def _bibtex_key(record_id: str) -> str:
    """Clave de cita BibTeX válida derivada del ``record_id`` (determinista)."""
    key = "".join(c if c.isalnum() else "_" for c in record_id).strip("_")
    return key or "ref"


def _escape(value: str) -> str:
    """Neutraliza caracteres que romperían un campo BibTeX entre llaves."""
    return value.replace("{", "(").replace("}", ")").strip()


def render_bibtex(records: list[SearchRecord]) -> str:
    """Renderiza la bibliografía de los estudios incluidos en formato BibTeX."""
    if not records:
        return "% Sin estudios incluidos.\n"

    entries: list[str] = []
    for record in records:
        kind = "article" if record.year else "misc"
        fields: list[tuple[str, str]] = [("title", _escape(record.title))]
        if record.authors:
            fields.append(("author", _escape(" and ".join(record.authors))))
        if record.year:
            fields.append(("year", str(record.year)))
        if record.doi:
            fields.append(("doi", _escape(record.doi)))
        if record.url:
            fields.append(("url", _escape(record.url)))
        if record.source_db and record.source_db != "unknown":
            fields.append(("note", f"source: {_escape(record.source_db)}"))

        body = ",\n".join(f"  {key} = {{{val}}}" for key, val in fields)
        entries.append(f"@{kind}{{{_bibtex_key(record.record_id)},\n{body}\n}}")

    return "\n\n".join(entries) + "\n"
