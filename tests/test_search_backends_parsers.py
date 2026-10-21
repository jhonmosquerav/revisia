"""Parsers de Crossref y S2 sobre respuestas reales recortadas (auditoría 2026-09-03, M18)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fakes import ClienteJSON

from revisia.agents import search_backends
from revisia.agents.search_backends import crossref_search

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _carga(nombre: str) -> dict:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def test_las_fixtures_no_llevan_correo_ni_claves() -> None:
    for nombre in ("crossref_works.json",):
        texto = (FIXTURES / nombre).read_text(encoding="utf-8")
        assert "mailto=" not in texto and "api_key" not in texto
        assert not _CORREO.search(texto), nombre
    assert (FIXTURES / "README.md").read_text(encoding="utf-8").count("https://api.") >= 1


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


def test_max_results_recorta_los_items(monkeypatch: pytest.MonkeyPatch) -> None:
    crossref = ClienteJSON(_carga("crossref_works.json"))
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: crossref)
    assert len(crossref_search("q", 2)) == 2
