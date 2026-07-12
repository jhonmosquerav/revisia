"""Tests del agente de deduplicación."""

from __future__ import annotations

from revisia.agents.dedup import deduplicate
from revisia.schemas.records import SearchRecord


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


def test_dedup_fusiona_extra_faltante_del_duplicado() -> None:
    # Conserva el primero (OpenAlex, sin pmcid) pero hereda el pmcid del
    # duplicado (PubMed), para no perder el texto completo por el orden de bases.
    recs = [
        SearchRecord(
            record_id="a", title="T", doi="10.1/x", source_db="OpenAlex", extra={"oa_url": "u"}
        ),
        SearchRecord(
            record_id="b", title="T", doi="10.1/X", source_db="PubMed", extra={"pmcid": "PMC1"}
        ),
    ]
    unique, discarded = deduplicate(recs)
    assert discarded == 1
    assert len(unique) == 1
    assert unique[0].source_db == "OpenAlex"  # conserva el primero visto
    assert unique[0].extra["pmcid"] == "PMC1"  # ...pero hereda el pmcid del duplicado
    assert unique[0].extra["oa_url"] == "u"  # y conserva lo suyo


def test_dedup_no_sobreescribe_extra_existente() -> None:
    recs = [
        SearchRecord(record_id="a", title="T", doi="10.1/x", extra={"pmcid": "PMC_KEEP"}),
        SearchRecord(record_id="b", title="T", doi="10.1/X", extra={"pmcid": "PMC_OTHER"}),
    ]
    unique, _ = deduplicate(recs)
    assert unique[0].extra["pmcid"] == "PMC_KEEP"  # el valor del conservado no se pisa
