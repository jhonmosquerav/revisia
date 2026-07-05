"""Tests del agente de deduplicación."""

from __future__ import annotations

from prisma_loop.agents.dedup import deduplicate
from prisma_loop.schemas.records import SearchRecord


def test_dedup_por_doi_normalizado() -> None:
    recs = [
        SearchRecord(record_id="a", title="A", doi="10.1/x"),
        SearchRecord(record_id="b", title="B distinto", doi="10.1/X"),
    ]
    unique, discarded = deduplicate(recs)
    assert len(unique) == 1
    assert discarded == 1


def test_dedup_por_titulo_normalizado() -> None:
    recs = [
        SearchRecord(record_id="a", title="Hello, World!"),
        SearchRecord(record_id="b", title="hello   world"),
    ]
    unique, discarded = deduplicate(recs)
    assert len(unique) == 1
    assert discarded == 1


def test_dedup_conserva_distintos_y_orden() -> None:
    recs = [
        SearchRecord(record_id="a", title="Primero"),
        SearchRecord(record_id="b", title="Segundo"),
    ]
    unique, discarded = deduplicate(recs)
    assert [r.record_id for r in unique] == ["a", "b"]
    assert discarded == 0
