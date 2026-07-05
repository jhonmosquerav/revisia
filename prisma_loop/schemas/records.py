"""Registro bibliográfico · unidad de trabajo a lo largo del pipeline.

Un ``SearchRecord`` representa un estudio candidato desde que se identifica en
una base hasta que se incluye o excluye. ``record_id`` debe ser estable entre
ejecuciones (idealmente el DOI; si no, un hash determinista del título) para
garantizar reproducibilidad y deduplicación idempotente.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRecord(BaseModel):
    """Un estudio candidato identificado en la búsqueda."""

    record_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    source_db: str = "unknown"
    extra: dict = Field(default_factory=dict)
