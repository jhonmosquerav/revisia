"""Tests del adaptador DSpace 7+ (AGROSAVIA/CLACSO/OKR) y DOAB (DSpace 6). Offline."""

from __future__ import annotations

from revisia.agents import dspace


class _FakeResp:
    def __init__(self, payload) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeClient:
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
    monkeypatch.setattr(dspace, "_client", lambda timeout=60.0, mailto=None: client)


def _hal(objects: list[dict], *, total_pages: int, number: int = 0) -> dict:
    return {
        "_embedded": {
            "searchResult": {
                "_embedded": {"objects": [{"_embedded": {"indexableObject": o}} for o in objects]},
                "page": {
                    "number": number,
                    "size": 2,
                    "totalPages": total_pages,
                    "totalElements": 3,
                },
            }
        }
    }


def _md(**fields: list[str]) -> dict:
    return {k.replace("_", "."): [{"value": v} for v in vals] for k, vals in fields.items()}


OKR_ITEM = {
    "handle": "10986/21037",
    "uuid": "u-1",
    "metadata": _md(
        dc_title=["Towards Sustainable Peace", "Hacia la paz sostenible"],
        dc_contributor_author=["World Bank"],
        dc_date_issued=["2014-09-29"],
        dc_identifier_doi=["10.1596/21037"],
        dc_identifier_uri=["https://hdl.handle.net/10986/21037"],
        dc_language_iso=["en_US"],
        dc_description_abstract=["The inauguration…"],
        okr_pdfurl=["http://documents.worldbank.org/x.pdf"],
    ),
}
CLACSO_ITEM = {
    "handle": "CLACSO/12048",
    "uuid": "u-2",
    "metadata": _md(
        dc_title=["Las ciudades y la cuestión social"],
        dc_contributor_editor=["Ziccardi, Alicia"],
        dc_date_issued=["2001"],
        dc_language=["spa"],
        dc_identifier_isbn=["950-9231-60-2"],
    ),
}


def test_dspace7_parse_y_paginacion(monkeypatch) -> None:
    client = _FakeClient(
        _hal([OKR_ITEM, CLACSO_ITEM], total_pages=2),
        _hal([CLACSO_ITEM], total_pages=2, number=1),
    )
    _patch(monkeypatch, client)
    records = dspace.worldbank_okr_search("pobreza", 3, mailto="x@y.z")
    url, params = client.calls[0]
    assert url == "https://openknowledge.worldbank.org/server/api/discover/search/objects"
    assert params == {"query": "pobreza", "dsoType": "item", "page": 0, "size": 3}
    assert client.calls[1][1]["page"] == 1 and len(records) == 3
    r0, r1 = records[0], records[1]
    assert r0.record_id == "10.1596/21037" and r0.title == "Towards Sustainable Peace"
    assert r0.extra["titles"] == ["Hacia la paz sostenible"]
    assert r0.extra["oa_url"].endswith(".pdf")
    assert r0.year == 2014 and r0.authors == ["World Bank"] and r0.source_db == "WorldBankOKR"
    assert r1.record_id == "worldbankokr:CLACSO/12048"  # sin DOI → fuente:handle
    assert r1.authors == ["Ziccardi, Alicia"] and r1.extra["isbn"] == ["950-9231-60-2"]
    assert r1.url == "https://openknowledge.worldbank.org/handle/CLACSO/12048"


def test_dspace7_se_detiene_en_total_pages(monkeypatch) -> None:
    client = _FakeClient(_hal([OKR_ITEM], total_pages=1))
    _patch(monkeypatch, client)
    records = dspace.agrosavia_search("cacao", 50)
    assert len(records) == 1 and len(client.calls) == 1
    assert client.calls[0][0].startswith("https://repository.agrosavia.co/")
    assert records[0].source_db == "AGROSAVIA"


def test_clacso_instancia() -> None:
    assert dspace.clacso_search.keywords["source_db"] == "CLACSO"
    assert dspace.clacso_search.keywords["base_url"] == dspace.CLACSO_URL


DOAB_ITEMS = [
    {
        "uuid": "f4b5",
        "handle": "20.500.12854/97644",
        "metadata": [
            {"key": "dc.title", "value": "China-Africa and an Economic Transformation"},
            {"key": "dc.contributor.editor", "value": "Oqubay, Arkebe"},
            {"key": "dc.date.issued", "value": "2019"},
            {"key": "oapen.identifier.doi", "value": "10.1093/OSO/9780198830504.001.0001"},
            {"key": "dc.description.abstract", "value": "<p>Resumen</p>"},
            {"key": "dc.language", "value": "English"},
            {
                "key": "dc.identifier.uri",
                "value": "https://directory.doabooks.org/handle/20.500.12854/97644",
            },
        ],
    },
    {"uuid": "b2", "handle": "20.500.12854/2", "metadata": [{"key": "dc.title", "value": "L2"}]},
]


def test_doab_parse_y_paginacion_sin_total(monkeypatch) -> None:
    client = _FakeClient(DOAB_ITEMS, [])
    _patch(monkeypatch, client)
    records = dspace.doab_search("economics", 5)
    assert client.calls[0][1] == {
        "query": "economics",
        "expand": "metadata",
        "limit": 5,
        "offset": 0,
    }
    assert len(records) == 2
    r0, r1 = records
    assert r0.record_id == "10.1093/oso/9780198830504.001.0001" and r0.year == 2019
    assert r0.authors == ["Oqubay, Arkebe"] and r0.abstract == "Resumen"
    assert r0.source_db == "DOAB" and r0.extra["type"] == "book"
    assert r1.record_id == "doab:20.500.12854/2"
    assert r1.url == "https://directory.doabooks.org/handle/20.500.12854/2"


def test_doab_pagina_llena_pide_mas_y_corta_no(monkeypatch) -> None:
    client = _FakeClient(DOAB_ITEMS, DOAB_ITEMS[:1])
    _patch(monkeypatch, client)
    records = dspace.doab_search("q", 2)  # limit=2 → 1.ª página llena → cumple max_results
    assert len(records) == 2 and len(client.calls) == 1
    client = _FakeClient(DOAB_ITEMS, DOAB_ITEMS[:1])
    _patch(monkeypatch, client)
    records = dspace.doab_search("q", 4)  # limit=4 → 2 ítems (<4) → página corta → fin
    assert len(records) == 2 and len(client.calls) == 1
