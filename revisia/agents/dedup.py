"""Agente de deduplicación (⚙️ determinista).

Elimina duplicados antes del screening (prep de la §5). Estrategia idempotente
y reproducible: clave por DOI normalizado cuando existe; si no, por título
normalizado (minúsculas, sin puntuación ni espacios redundantes). Conserva el
primer registro visto —fusionando en él las claves de ``extra`` que aporten los
duplicados (p. ej. un PMCID de PubMed cuando el conservado viene de OpenAlex)—
y reporta cuántos se descartaron.

Ola 1 (spec 2026-10-04 §7): ``deduplicate_with_report`` deja la traza completa
(``02_dedup/dedup.json``) y desambigua los ``record_id`` repetidos entre los
conservados (``<id>#2``, ``#3``…): un RIS con ``DO https://doi.org/…`` produce
el mismo id que el artículo de OpenAlex con otra clave de dedup, y el diario y
las etiquetas humanas usan el id como clave (hallazgo 3 del spec).
"""

from __future__ import annotations

import re

from revisia.schemas.artifacts import DedupDuplicate, DedupRename, DedupReport
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


def deduplicate_with_report(
    records: list[SearchRecord],
) -> tuple[list[SearchRecord], DedupReport]:
    """Deduplica y devuelve la traza completa (``02_dedup/dedup.json``).

    Conserva el primer registro de cada clave y le fusiona las claves de
    ``extra`` que aporten los duplicados posteriores (sin pisar las suyas), para
    no perder identificadores útiles —como el PMCID— por el orden de las bases.
    Ojo: la fusión muta el registro conservado (por eso la búsqueda se congela
    antes, en ``01_search/records.json``).

    Después, un ``record_id`` repetido entre los conservados se renombra de forma
    determinista: la primera aparición conserva el id y las siguientes pasan a
    ``<id>#2``, ``<id>#3``… (saltando cualquier id ya ocupado). El renombrado
    devuelve una copia; el registro original no cambia.

    Returns:
        ``(únicos, informe)``, preservando el orden de aparición.
    """
    unique: list[SearchRecord] = []
    position: dict[str, int] = {}  # clave → índice en `unique`
    pairs: list[tuple[SearchRecord, int, str]] = []
    for record in records:
        key = dedup_key(record)
        index = position.get(key)
        if index is not None:
            _merge_extra(unique[index], record)
            pairs.append((record, index, key))
            continue
        position[key] = len(unique)
        unique.append(record)

    taken = {r.record_id for r in unique}
    seen_ids: dict[str, int] = {}
    renamed: list[DedupRename] = []
    for i, record in enumerate(unique):
        seen_ids[record.record_id] = seen_ids.get(record.record_id, 0) + 1
        if seen_ids[record.record_id] == 1:
            continue
        n = seen_ids[record.record_id]
        while f"{record.record_id}#{n}" in taken:
            n += 1
        new_id = f"{record.record_id}#{n}"
        taken.add(new_id)
        renamed.append(DedupRename(from_id=record.record_id, to_id=new_id))
        unique[i] = record.model_copy(update={"record_id": new_id})

    duplicates = [
        DedupDuplicate(
            record_id=record.record_id,
            source_db=record.source_db,
            kept_record_id=unique[index].record_id,
            key=key,
        )
        for record, index, key in pairs
    ]
    report = DedupReport(
        n_in=len(records), n_out=len(unique), duplicates=duplicates, renamed=renamed
    )
    return unique, report


def deduplicate(records: list[SearchRecord]) -> tuple[list[SearchRecord], int]:
    """Deduplica una lista de registros (envoltorio de ``deduplicate_with_report``).

    Returns:
        Tupla ``(únicos, n_descartados)``, preservando el orden de aparición.
    """
    unique, report = deduplicate_with_report(records)
    return unique, len(report.duplicates)
