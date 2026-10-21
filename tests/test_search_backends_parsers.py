"""Parsers de Crossref y S2 sobre respuestas reales recortadas (auditoría 2026-09-03, M18)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fakes import ClienteJSON

from revisia.agents import search_backends
from revisia.agents.search_backends import crossref_search, semantic_scholar_search

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _carga(nombre: str) -> dict:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def test_las_fixtures_no_llevan_correo_ni_claves() -> None:
    for nombre in ("crossref_works.json", "s2_paper_search.json"):
        texto = (FIXTURES / nombre).read_text(encoding="utf-8")
        assert "mailto=" not in texto and "api_key" not in texto
        assert not _CORREO.search(texto), nombre
    assert (FIXTURES / "README.md").read_text(encoding="utf-8").count("https://api.") >= 2


def test_crossref_parsea_los_tres_items_reales(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _carga("crossref_works.json")
    cliente = ClienteJSON(payload)
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: cliente)
    records = crossref_search("q", 10, mailto="revisora@example.org")
    items = payload["message"]["items"]
    assert len(records) == len(items) == 3
    assert cliente.last_params == {"query": "q", "rows": 10, "mailto": "revisora@example.org"}
    for rec, it in zip(records, items, strict=True):
        doi = (it.get("DOI") or "").lower().strip() or None
        assert rec.doi == doi
        assert (rec.record_id == doi) if doi else rec.record_id.startswith("crossref:")
        assert rec.title == (it["title"][0] if it.get("title") else "(sin título)")
        partes = (it.get("issued") or {}).get("date-parts") or [[None]]
        assert rec.year == (partes[0][0] if partes and partes[0] else None)
        assert rec.url == it.get("URL") and rec.source_db == "Crossref"
        if it.get("abstract"):
            assert rec.abstract and "<" not in rec.abstract  # JATS (<jats:p>) fuera
        autores = [a for a in it.get("author", []) if a.get("given") or a.get("family")]
        assert len(rec.authors) == len(autores)
    assert sum(1 for r in records if r.doi is None) == 1
    assert any(it.get("abstract") for it in items)
    # literales de la fixture (sin recalcular con la lógica del parser)
    assert [r.doi for r in records] == [
        "10.20944/preprints202503.0981.v1",
        "10.1101/2024.06.03.24308405",
        None,
    ]
    assert records[2].record_id == "crossref:2"
    assert records[0].authors[0] == "Carlo Galli"
    assert records[1].authors[0] == "Ronald Luo"
    assert "Large Language Models (LLMs) have recently emerged" in (records[0].abstract or "")


def test_semantic_scholar_parsea_los_tres_papers_reales(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _carga("s2_paper_search.json")
    cliente = ClienteJSON(payload)
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: cliente)
    records = semantic_scholar_search("q", 10)
    papers = payload["data"]
    assert len(records) == len(papers) == 3
    assert cliente.last_params["limit"] == 10 and "externalIds" in cliente.last_params["fields"]
    for rec, p in zip(records, papers, strict=True):
        assert rec.title == (p.get("title") or "(sin título)") and rec.year == p.get("year")
        assert rec.abstract == p.get("abstract") and rec.url == p.get("url")
        assert rec.authors == [a["name"] for a in p.get("authors", []) if a.get("name")]
        oa = (p.get("openAccessPdf") or {}).get("url")
        assert (rec.extra.get("oa_url") == oa) if oa else ("oa_url" not in rec.extra)
        assert rec.source_db == "SemanticScholar"
    # literales de la fixture
    assert [r.doi for r in records] == [
        "10.3390/info16050378",
        "10.1007/978-3-031-56027-9_25",
        None,
    ]
    assert [r.record_id for r in records[:2]] == [records[0].doi, records[1].doi]
    assert records[2].record_id == "s2:11e09ae8c862a8c50fbd489543e86f6ab526542e"
    assert records[0].authors[0] == "C. Galli"
    assert records[0].extra["oa_url"].startswith("https://www.mdpi.com/")
    assert "oa_url" not in records[1].extra
    assert (records[0].year, records[1].year) == (2025, 2024)


def test_max_results_recorta_los_items(monkeypatch: pytest.MonkeyPatch) -> None:
    crossref = ClienteJSON(_carga("crossref_works.json"))
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: crossref)
    assert len(crossref_search("q", 2)) == 2
    s2 = ClienteJSON(_carga("s2_paper_search.json"))
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: s2)
    assert len(semantic_scholar_search("q", 1)) == 1
