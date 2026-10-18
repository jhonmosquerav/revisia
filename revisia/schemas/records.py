"""Registro bibliográfico · unidad de trabajo a lo largo del pipeline.

Un ``SearchRecord`` representa un estudio candidato desde que se identifica en
una base hasta que se incluye o excluye. ``record_id`` debe ser estable entre
ejecuciones (idealmente el DOI; si no, un hash determinista del título) para
garantizar reproducibilidad y deduplicación idempotente.
"""

from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel, Field, model_validator

# Sustitutos UTF-16 sueltos (U+D800-U+DFFF): `json.loads('"\ud800"')`, lo que hace
# `httpx.Response.json()` con un `\ud800` escapado en la respuesta de una base, los deja en un
# `str` de Python, pero no se pueden codificar en UTF-8 (el primer `write_json` revienta).
_SUSTITUTOS = re.compile(f"[{chr(0xD800)}-{chr(0xDFFF)}]")
_REEMPLAZO = chr(0xFFFD)  # U+FFFD, el carácter de sustitución de Unicode

# TypeVar clásico y no PEP 695 (`def f[T]`): la suite también corre en 3.11.
T = TypeVar("T")


def replace_surrogates(value: T) -> T:  # noqa: UP047
    """``value`` con cada sustituto suelto cambiado por U+FFFD, recorriendo mapas y listas.

    Revisión final de la Ola 1 (A4): un sustituto suelto llegaba a ``SearchRecord`` desde una
    API y reventaba en ``01_search/records.json`` con un ``UnicodeEncodeError`` (rc 3 y la
    búsqueda repetida en cada reanudación, con un ``.tmp`` huérfano). Las claves de los mapas
    también se sanean.
    """
    result: object = value
    if isinstance(value, str):
        result = _SUSTITUTOS.sub(_REEMPLAZO, value)
    elif isinstance(value, dict):
        result = {replace_surrogates(k): replace_surrogates(v) for k, v in value.items()}
    elif isinstance(value, list | tuple):
        result = type(value)(replace_surrogates(v) for v in value)
    return result  # type: ignore[return-value]  # mismo tipo que `value`


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

    @model_validator(mode="before")
    @classmethod
    def _sin_sustitutos(cls, data: object) -> object:
        """Todo texto del registro (``extra`` incluido) sin sustitutos sueltos (A4)."""
        return replace_surrogates(data) if isinstance(data, dict) else data
