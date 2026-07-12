"""Agente de deduplicación (⚙️ determinista).

Elimina duplicados antes del screening (prep de la §5). Estrategia idempotente
y reproducible: clave por DOI normalizado cuando existe; si no, por título
normalizado (minúsculas, sin puntuación ni espacios redundantes). Conserva el
primer registro visto —fusionando en él las claves de ``extra`` que aporten los
duplicados (p. ej. un PMCID de PubMed cuando el conservado viene de OpenAlex)—
y reporta cuántos se descartaron.
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


def _merge_extra(kept: SearchRecord, duplicate: SearchRecord) -> None:
    """Rellena en el registro conservado las claves de ``extra`` que aporta el
    duplicado y que faltan (o están vacías). No sobreescribe valores presentes."""
    for key, value in duplicate.extra.items():
        if value and not kept.extra.get(key):
            kept.extra[key] = value


def deduplicate(records: list[SearchRecord]) -> tuple[list[SearchRecord], int]:
    """Deduplica una lista de registros.

    Conserva el primer registro de cada clave y le fusiona las claves de
    ``extra`` que aporten los duplicados posteriores (sin pisar las suyas), para
    no perder identificadores útiles —como el PMCID— por el orden de las bases.

    Returns:
        Tupla ``(únicos, n_descartados)``, preservando el orden de aparición.
    """
    seen: dict[str, SearchRecord] = {}
    unique: list[SearchRecord] = []
    discarded = 0
    for record in records:
        key = dedup_key(record)
        kept = seen.get(key)
        if kept is not None:
            discarded += 1
            _merge_extra(kept, record)
            continue
        seen[key] = record
        unique.append(record)
    return unique, discarded
