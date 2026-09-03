"""Tests de los backends abiertos nuevos (ERIC, DOAJ, UNESDOC, BVS). Todo offline.

Los payloads son recortes de respuestas reales verificadas en vivo (2026-09-03).
"""

from __future__ import annotations

from revisia.agents import _http, open_backends


def test_user_agent_identifica_a_revisia() -> None:
    assert _http.user_agent(None).startswith("revisia/")
    assert "mailto:x@y.z" in _http.user_agent("x@y.z")


def test_strip_html_limpia_etiquetas() -> None:
    assert _http.strip_html("<p>Hola <b>mundo</b></p>") == "Hola mundo"
    assert _http.strip_html(None) is None
    assert _http.strip_html("<p></p>") is None


class _FakeResp:
    def __init__(self, payload) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Sustituto de httpx.Client: sirve payloads en orden (uno por GET)."""

    def __init__(self, *payloads) -> None:
        self._payloads = list(payloads)
        self.calls: list[tuple[str, dict | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get(self, url: str, params: dict | None = None) -> _FakeResp:
        self.calls.append((url, params))
        payload = self._payloads.pop(0) if len(self._payloads) > 1 else self._payloads[0]
        return _FakeResp(payload)


def _patch(monkeypatch, client: _FakeClient) -> None:
    monkeypatch.setattr(open_backends, "_client", lambda timeout=60.0, mailto=None: client)


# ── ERIC ──────────────────────────────────────────────────────────────

ERIC_PAYLOAD = {
    "response": {
        "numFound": 2,
        "docs": [
            {
                "id": "EJ1465850",
                "title": "Systematic Review of Enrollment",
                "author": ["Brenda K. Smith", "Keith Christensen"],
                "publicationdateyear": 2024,
                "description": "There is a <b>perception</b> that…",
                "url": "https://doi.org/10.1201/9781003102670-20",
                "language": ["English"],
                "peerreviewed": "T",
            },
            {"id": "ED660568", "title": "Informe gris", "publicationdateyear": "bad"},
        ],
    }
}


def test_eric_parse(monkeypatch) -> None:
    client = _FakeClient(ERIC_PAYLOAD)
    _patch(monkeypatch, client)
    records = open_backends.eric_search("systematic review", 10, mailto="x@y.z")
    assert client.calls[0][1]["search"] == "systematic review"
    assert client.calls[0][1]["rows"] == 10
    r0, r1 = records
    assert r0.doi == "10.1201/9781003102670-20" and r0.record_id == r0.doi
    assert r0.authors == ["Brenda K. Smith", "Keith Christensen"]
    assert r0.year == 2024 and "<b>" not in (r0.abstract or "")
    assert r0.source_db == "ERIC" and r0.extra["peer_reviewed"] is True
    assert r1.record_id == "eric:ED660568"
    assert r1.url == "https://eric.ed.gov/?id=ED660568"
    assert r1.year is None and r1.authors == []


# ── DOAJ ──────────────────────────────────────────────────────────────

DOAJ_PAGE = {
    "total": 1,
    "results": [
        {
            "id": "abc123",
            "bibjson": {
                "title": "Effect of smoking",
                "abstract": "Background…",
                "year": "2024",
                "author": [{"name": "Dachen Luo"}, {"name": "Dongmei Yang"}],
                "identifier": [
                    {"id": "2234-943X", "type": "eissn"},
                    {"id": "10.3389/FONC.2024.1422160", "type": "doi"},
                ],
                "journal": {"title": "Frontiers in Oncology", "language": ["EN"]},
                "link": [{"type": "fulltext", "url": "https://www.frontiersin.org/x"}],
            },
        }
    ],
}


def test_doaj_parse_y_tope_100(monkeypatch) -> None:
    client = _FakeClient(DOAJ_PAGE)
    _patch(monkeypatch, client)
    records = open_backends.doaj_search('"systematic review"', 250)
    url, params = client.calls[0]
    assert url.endswith("/articles/%22systematic%20review%22")
    assert params["pageSize"] == 100
    assert len(records) == 1  # total=1 → no pide más páginas
    r = records[0]
    assert r.doi == "10.3389/fonc.2024.1422160" and r.record_id == r.doi
    assert r.authors == ["Dachen Luo", "Dongmei Yang"] and r.year == 2024
    assert r.extra["oa_url"] == "https://www.frontiersin.org/x"
    assert r.extra["journal"] == "Frontiers in Oncology" and r.source_db == "DOAJ"


def test_doaj_sin_doi_usa_id(monkeypatch) -> None:
    page = {"total": 1, "results": [{"id": "zzz", "bibjson": {"title": "Sin doi"}}]}
    _patch(monkeypatch, _FakeClient(page))
    assert open_backends.doaj_search("q", 5)[0].record_id == "doaj:zzz"


def test_doaj_pagina_hasta_max_results(monkeypatch) -> None:
    def page(ids: list[str]) -> dict:
        return {"total": 3, "results": [{"id": i, "bibjson": {"title": i}} for i in ids]}

    client = _FakeClient(page(["a", "b"]), page(["c"]))
    _patch(monkeypatch, client)
    records = open_backends.doaj_search("q", 2)  # pageSize=2 → 2 registros en 1 llamada
    assert len(records) == 2 and len(client.calls) == 1
    client = _FakeClient(page(["a", "b"]), page(["c"]))
    _patch(monkeypatch, client)
    records = open_backends.doaj_search("q", 3)
    assert [r.record_id for r in records] == ["doaj:a", "doaj:b", "doaj:c"]
    assert client.calls[1][1]["page"] == 2


# ── UNESDOC ───────────────────────────────────────────────────────────

UNESDOC_PAGE = {
    "total_count": 1,
    "results": [
        {
            "uuid": "45267330-ebb7",
            "url": "https://unesdoc.unesco.org/ark:/48223/pf0000373844",
            "year": ["2020"],
            "language": ["eng"],
            "title": "COVID-19 is a serious threat",
            "description": "Includes bibliography",
            "creator": "Global Education Monitoring Report Team, Chen, Dandan",
            "isbn": None,
            "document_type": "programme and meeting document",
        }
    ],
}


def test_unesdoc_parse_y_where(monkeypatch) -> None:
    client = _FakeClient(UNESDOC_PAGE)
    _patch(monkeypatch, client)
    records = open_backends.unesdoc_search('educación "a distancia"', 10)
    assert client.calls[0][1]["where"] == 'search("educación \\"a distancia\\"")'
    r = records[0]
    assert r.record_id == "unesdoc:45267330-ebb7" and r.doi is None
    assert r.year == 2020 and r.url.endswith("pf0000373844")
    assert r.authors == ["Global Education Monitoring Report Team, Chen, Dandan"]
    assert r.source_db == "UNESDOC" and r.extra["document_type"].startswith("programme")


def test_unesdoc_cadena_avanzada_pasa_tal_cual() -> None:
    q = 'search("education") AND year:"2020"'
    assert open_backends._unesdoc_where(q) == q


# ── BVS / LILACS ──────────────────────────────────────────────────────

BVS_PAGE_1 = {
    "diaServerResponse": [
        {
            "response": {
                "numFound": 3,
                "start": 0,
                "docs": [
                    {
                        "id": "biblio-1707164",
                        "ti": ["Exploración de las emociones", "Exploration of emotions"],
                        "au": ["Chulibert, María Eugenia", "Pees Labory, Johana"],
                        "ab": ["Introducción: Argentina…"],
                        "da": "202707",
                        "aid": "10.48061/SAN.2026.27.1.95",
                        "ur": ["https://fi-admin.bvsalud.org/document/view/c4vsg"],
                        "la": ["es"],
                        "db": ["LILACS"],
                        "is": ["1667-8052"],
                    },
                    {"id": "biblio-2", "ti": ["Sin doi"], "da": "2019"},
                ],
            }
        }
    ]
}
BVS_PAGE_2 = {
    "diaServerResponse": [
        {"response": {"numFound": 3, "start": 2, "docs": [{"id": "biblio-3", "ti": ["Tercero"]}]}}
    ]
}


def test_bvs_parse_y_paginacion_from_1based(monkeypatch) -> None:
    client = _FakeClient(BVS_PAGE_1, BVS_PAGE_2)
    _patch(monkeypatch, client)
    records = open_backends.bvs_search("diabetes", 3)
    assert client.calls[0][0] == "https://search.bvsalud.org/portal/"
    assert client.calls[0][1]["from"] == 1 and client.calls[0][1]["count"] == 3
    assert client.calls[1][1]["from"] == 3  # 2 docs servidos → la siguiente arranca en 3
    assert [r.record_id for r in records] == [
        "10.48061/san.2026.27.1.95",
        "bvs:biblio-2",
        "bvs:biblio-3",
    ]
    r0 = records[0]
    assert r0.title == "Exploración de las emociones" and r0.year == 2027
    assert r0.authors[0] == "Chulibert, María Eugenia" and r0.extra["db"] == ["LILACS"]
    assert r0.source_db == "BVS" and r0.url.endswith("c4vsg")
    assert records[1].year == 2019


def test_gim_es_instancia_global(monkeypatch) -> None:
    client = _FakeClient(BVS_PAGE_2)
    _patch(monkeypatch, client)
    records = open_backends.gim_search("malaria", 5)
    assert client.calls[0][0] == "https://search.bvsalud.org/gim/"
    assert records[0].source_db == "GIM" and records[0].record_id == "gim:biblio-3"


def test_helpers_year_y_doi() -> None:
    assert open_backends._year("2024-09-01") == 2024
    assert open_backends._year(2019) == 2019
    assert open_backends._year("s/f") is None
    assert open_backends._doi("https://doi.org/10.1/ABC") == "10.1/abc"
    assert open_backends._doi("doi:10.1/x") == "10.1/x"
    assert open_backends._doi("https://example.org/no-doi") is None
