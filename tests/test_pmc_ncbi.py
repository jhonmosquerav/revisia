"""Tests de la integración PMC/NCBI (cliente E-utilities + BioC + backends + fulltext).

Todo offline: se enruta un cliente HTTP falso por subcadena de URL y se anula el
sleep del throttle. Sin red ni API key.
"""

from __future__ import annotations

import pytest

from revisia.agents import ncbi


class _FakeResp:
    """Respuesta falsa: expone .json() (endpoints JSON) y .text (efetch XML)."""

    def __init__(self, *, json_data=None, text_data=None) -> None:
        self._json = json_data
        self._text = text_data

    def raise_for_status(self) -> None:
        return None

    def json(self):
        if self._json is None:
            raise ValueError("respuesta sin cuerpo JSON")
        return self._json

    @property
    def text(self) -> str:
        return self._text or ""


class _RouterClient:
    """Sustituto de httpx.Client que enruta por subcadena de URL a un _FakeResp."""

    def __init__(self, routes: dict[str, _FakeResp]) -> None:
        self._routes = routes
        self.calls: list[str] = []

    def __enter__(self) -> _RouterClient:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get(self, url: str, params: dict | None = None) -> _FakeResp:
        self.calls.append(url)
        for frag, resp in self._routes.items():
            if frag in url:
                return resp
        raise AssertionError(f"URL no ruteada en el test: {url}")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch) -> None:
    """Anula el throttle real para que los tests no duerman."""
    monkeypatch.setattr(ncbi, "_sleep", lambda _s: None)


def _route(monkeypatch, routes: dict[str, _FakeResp]) -> _RouterClient:
    client = _RouterClient(routes)
    monkeypatch.setattr(ncbi, "_client", lambda timeout=60.0: client)
    return client


PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>40000001</PMID>
      <Article>
        <ArticleTitle>LLM screening en revisiones sistematicas</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Primera parte.</AbstractText>
          <AbstractText Label="METHODS">Segunda parte.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author>
          <Author><LastName>Roe</LastName><ForeName>Ada</ForeName></Author>
        </AuthorList>
        <PubDate><Year>2026</Year></PubDate>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">40000001</ArticleId>
        <ArticleId IdType="doi">10.1/ABC</ArticleId>
        <ArticleId IdType="pmc">PMC7654321</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_esearch_parsea_idlist(monkeypatch) -> None:
    _route(
        monkeypatch,
        {
            "esearch.fcgi": _FakeResp(
                json_data={"esearchresult": {"idlist": ["40000001", "40000002"]}}
            )
        },
    )
    ids = ncbi.esearch("pubmed", "llm systematic review", 10, mailto="x@y.z")
    assert ids == ["40000001", "40000002"]


def test_efetch_pubmed_parsea_registro(monkeypatch) -> None:
    _route(monkeypatch, {"efetch.fcgi": _FakeResp(text_data=PUBMED_XML)})
    records = ncbi.efetch_pubmed(["40000001"], mailto="x@y.z")
    assert len(records) == 1
    r = records[0]
    assert r.record_id == "10.1/abc"
    assert r.doi == "10.1/abc"
    assert r.title == "LLM screening en revisiones sistematicas"
    assert r.abstract == "Primera parte. Segunda parte."
    assert r.authors == ["Jane Doe", "Ada Roe"]
    assert r.year == 2026
    assert r.source_db == "PubMed"
    assert r.extra["pmid"] == "40000001"
    assert r.extra["pmcid"] == "PMC7654321"


def test_efetch_pubmed_sin_doi_usa_pmid(monkeypatch) -> None:
    xml = """<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle><MedlineCitation>
<PMID>39999999</PMID>
<Article><ArticleTitle>Sin DOI</ArticleTitle></Article>
</MedlineCitation></PubmedArticle></PubmedArticleSet>
"""
    _route(monkeypatch, {"efetch.fcgi": _FakeResp(text_data=xml)})
    r = ncbi.efetch_pubmed(["39999999"])[0]
    assert r.record_id == "pubmed:39999999"
    assert r.doi is None
    assert r.year is None


def test_esummary_pmc_parsea_metadata(monkeypatch) -> None:
    _route(
        monkeypatch,
        {
            "esummary.fcgi": _FakeResp(
                json_data={
                    "result": {
                        "uids": ["7654321"],
                        "7654321": {
                            "title": "Articulo OA en PMC",
                            "authors": [{"name": "Doe J"}],
                            "pubdate": "2025 Jan",
                            "articleids": [{"idtype": "doi", "value": "10.9/OA"}],
                        },
                    }
                }
            )
        },
    )
    records = ncbi.esummary_pmc(["7654321"], mailto="x@y.z")
    assert len(records) == 1
    r = records[0]
    assert r.record_id == "10.9/oa"
    assert r.title == "Articulo OA en PMC"
    assert r.year == 2025
    assert r.source_db == "PMC"
    assert r.extra["pmcid"] == "PMC7654321"
    assert r.abstract is None


def test_esearch_vacio_no_llama_efetch() -> None:
    assert ncbi.efetch_pubmed([]) == []
    assert ncbi.esummary_pmc([]) == []
