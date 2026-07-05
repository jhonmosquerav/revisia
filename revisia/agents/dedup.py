"""Agente de deduplicación (⚙️ determinista).

Elimina duplicados antes del screening (prep de la §5). Estrategia idempotente
y reproducible: clave por DOI normalizado cuando existe; si no, por título
normalizado (minúsculas, sin puntuación ni espacios redundantes). Conserva el
primer registro visto y reporta cuántos se descartaron.
"""

from __future__ import annotations

import re

from revisia.schemas.records import SearchRecord

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _title_key(title: str) -> str:
    return _NON_ALNUM.sub(" ", title.lower()).strip()


def dedup_key(record: SearchRecord) -> str:
    """Clave de deduplicación de un registro (DOI > título normalizado)."""
    if record.doi:
        return f"doi:{record.doi.lower().strip()}"
    return f"title:{_title_key(record.title)}"


def deduplicate(records: list[SearchRecord]) -> tuple[list[SearchRecord], int]:
    """Deduplica una lista de registros.

    Returns:
        Tupla ``(únicos, n_descartados)``, preservando el orden de aparición.
    """
    seen: set[str] = set()
    unique: list[SearchRecord] = []
    discarded = 0
    for record in records:
        key = dedup_key(record)
        if key in seen:
            discarded += 1
            continue
        seen.add(key)
        unique.append(record)
    return unique, discarded
