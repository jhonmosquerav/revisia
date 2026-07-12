# Integración PMC/NCBI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sumar NCBI directo a RevisIA como base de búsqueda (PubMed + PMC opt-in vía E-utilities) y como fuente de texto completo OA estructurado (BioC-PMC).

**Architecture:** Un módulo nuevo `revisia/agents/ncbi.py` concentra toda la lógica NCBI (cortesía/throttle, `esearch`/`efetch`/`esummary`, BioC-PMC, ID Converter). La búsqueda lo consume desde `search_backends.py` (backends nuevos + reasignación de alias); el texto completo desde `fulltext.py` (BioC preferente con fallback al raspado OA actual).

**Tech Stack:** Python 3.13, `httpx` (extra `search`, ya presente), `json` + `xml.etree.ElementTree` (stdlib), `pytest` + `monkeypatch`. Sin dependencias nuevas.

## Global Constraints

- **Sin dependencias nuevas:** solo `httpx` (extra `search` existente), `json`, `xml.etree`, `os`, `time` (stdlib).
- **Tests offline y herméticos:** ninguna prueba toca la red; se mockea el cliente NCBI y se anula el `sleep` del throttle. Mantener las **144 tests verdes** + añadir las nuevas.
- **Cortesía NCBI:** cada petición E-utilities lleva `tool=revisia` + `email=<mailto>` (si hay) + `api_key` (si `NCBI_API_KEY` está en el entorno). Throttle ≤3 req/s sin key, ≤10 con key.
- **`NCBI_API_KEY` opcional:** se lee con `os.environ.get("NCBI_API_KEY")`; sin ella todo funciona (solo más lento). Nunca se commitea.
- **Firma estándar de backend:** `fn(query, max_results, *, mailto) -> list[SearchRecord]`.
- **`record_id` estable:** DOI normalizado en minúsculas si existe; si no, `pubmed:<pmid>` / `pmc:<uid>` (idempotente en dedup).
- **No tocar la red sin `mailto`:** la resolución de PMCID por DOI/PMID vía ID Converter solo ocurre si se pasó `mailto` (igual que Unpaywall en `fulltext.py`).
- **Idioma:** código y docstrings en español, como el resto del repo. Conventional Commits.
- **Comandos:** los tests se corren con `uv run pytest`.

---

### Task 1: Cliente NCBI — búsqueda (esearch / efetch / esummary) + cortesía

**Files:**
- Create: `revisia/agents/ncbi.py`
- Test: `tests/test_pmc_ncbi.py`

**Interfaces:**
- Consumes: `revisia.schemas.records.SearchRecord`.
- Produces:
  - `esearch(db: str, term: str, retmax: int, *, mailto: str | None = None) -> list[str]`
  - `efetch_pubmed(pmids: list[str], *, mailto: str | None = None) -> list[SearchRecord]` (source_db `"PubMed"`, `extra["pmid"]`/`extra["pmcid"]` cuando existan)
  - `esummary_pmc(pmcids: list[str], *, mailto: str | None = None) -> list[SearchRecord]` (source_db `"PMC"`, `extra["pmcid"]`, sin abstract)
  - Helpers internos `_client`, `_throttle`, `_sleep`, `_common_params`, `_parse_pubmed_article`.

- [ ] **Step 1: Escribir el test que falla** (crea `tests/test_pmc_ncbi.py`)

```python
"""Tests de la integración PMC/NCBI (cliente E-utilities + BioC + backends + fulltext).

Todo offline: se enruta un cliente HTTP falso por subcadena de URL y se anula el
sleep del throttle. Sin red ni API key.
"""

from __future__ import annotations

import pytest

from revisia.agents import ncbi
from revisia.schemas.records import SearchRecord


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

    def __enter__(self) -> "_RouterClient":
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
    _route(monkeypatch, {"esearch.fcgi": _FakeResp(json_data={
        "esearchresult": {"idlist": ["40000001", "40000002"]}
    })})
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
    _route(monkeypatch, {"esummary.fcgi": _FakeResp(json_data={
        "result": {
            "uids": ["7654321"],
            "7654321": {
                "title": "Articulo OA en PMC",
                "authors": [{"name": "Doe J"}],
                "pubdate": "2025 Jan",
                "articleids": [{"idtype": "doi", "value": "10.9/OA"}],
            },
        }
    })})
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
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_pmc_ncbi.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'revisia.agents.ncbi'`

- [ ] **Step 3: Crear `revisia/agents/ncbi.py` con la parte de búsqueda**

```python
"""Cliente NCBI · E-utilities (esearch/efetch/esummary) + BioC-PMC + ID Converter.

Fuente única de la lógica NCBI para RevisIA: la consumen el backend de búsqueda
(:mod:`revisia.agents.search_backends`) y la adquisición de texto completo
(:mod:`revisia.agents.fulltext`). Cortesía NCBI: ``tool`` + ``email`` en cada
petición E-utilities, ``api_key`` opcional (``NCBI_API_KEY``) y un throttle que
respeta el rate-limit (≤3 req/s sin key, ≤10 con key). Sin dependencias nuevas:
``httpx`` (extra ``search``), ``json`` y ``xml.etree`` de stdlib.
"""

from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from typing import Any

from revisia.schemas.records import SearchRecord

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS}/esearch.fcgi"
EFETCH_URL = f"{EUTILS}/efetch.fcgi"
ESUMMARY_URL = f"{EUTILS}/esummary.fcgi"
IDCONV_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
BIOC_URL = (
    "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/"
    "pmcoa.cgi/BioC_json/{pmcid}/unicode"
)

TOOL = "revisia"

_sleep = time.sleep  # indirección para tests (monkeypatch ncbi._sleep)
_last_call = [0.0]  # holder mutable del último timestamp (throttle)


def _min_interval() -> float:
    """Espaciado mínimo entre llamadas E-utilities (cortesía NCBI)."""
    return 0.11 if os.environ.get("NCBI_API_KEY") else 0.34


def _throttle() -> None:
    """Respeta el rate-limit NCBI espaciando llamadas consecutivas."""
    wait = _min_interval() - (time.monotonic() - _last_call[0])
    if wait > 0:
        _sleep(wait)
    _last_call[0] = time.monotonic()


def _client(timeout: float = 60.0) -> Any:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RuntimeError(
            "El cliente NCBI requiere httpx. Instala el extra: `uv sync --extra search`."
        ) from exc
    return httpx.Client(timeout=timeout, follow_redirects=True)


def _common_params(mailto: str | None) -> dict[str, str]:
    """Params de cortesía comunes a toda petición E-utilities."""
    params = {"tool": TOOL}
    if mailto:
        params["email"] = mailto
    key = os.environ.get("NCBI_API_KEY")
    if key:
        params["api_key"] = key
    return params


def _text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    return "".join(el.itertext()).strip() or None


def esearch(db: str, term: str, retmax: int, *, mailto: str | None = None) -> list[str]:
    """Devuelve la lista de IDs de una búsqueda E-utilities (JSON).

    Para ``db='pubmed'`` son PMIDs; para ``db='pmc'`` son UIDs de PMC.
    """
    params = _common_params(mailto)
    params.update({"db": db, "term": term, "retmax": str(max(1, retmax)), "retmode": "json"})
    _throttle()
    with _client() as client:
        resp = client.get(ESEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    return list((data.get("esearchresult") or {}).get("idlist") or [])


def _parse_pubmed_article(art: ET.Element) -> SearchRecord:
    pmid = _text(art.find(".//PMID"))
    title = _text(art.find(".//ArticleTitle")) or "(sin título)"
    abstract_parts = [
        "".join(a.itertext()).strip() for a in art.findall(".//Abstract/AbstractText")
    ]
    abstract = " ".join(p for p in abstract_parts if p) or None
    authors: list[str] = []
    for a in art.findall(".//AuthorList/Author"):
        name = " ".join(p for p in [_text(a.find("ForeName")), _text(a.find("LastName"))] if p)
        if name:
            authors.append(name)
    year = None
    y = _text(art.find(".//PubDate/Year"))
    if y and y.isdigit():
        year = int(y)
    else:
        medline = _text(art.find(".//PubDate/MedlineDate"))
        if medline and medline[:4].isdigit():
            year = int(medline[:4])
    doi = None
    pmcid = None
    for aid in art.findall(".//ArticleId"):
        idtype = (aid.get("IdType") or "").lower()
        val = (aid.text or "").strip()
        if idtype == "doi" and not doi:
            doi = val.lower() or None
        elif idtype == "pmc" and not pmcid:
            pmcid = val or None
    if not doi:
        eloc = art.find(".//ELocationID[@EIdType='doi']")
        if eloc is not None and eloc.text:
            doi = eloc.text.strip().lower() or None
    extra: dict[str, str] = {}
    if pmid:
        extra["pmid"] = pmid
    if pmcid:
        extra["pmcid"] = pmcid
    url = None
    if doi:
        url = f"https://doi.org/{doi}"
    elif pmid:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    return SearchRecord(
        record_id=doi or (f"pubmed:{pmid}" if pmid else f"pubmed:{title[:40]}"),
        title=title,
        abstract=abstract,
        authors=authors,
        year=year,
        doi=doi,
        url=url,
        source_db="PubMed",
        extra=extra,
    )


def efetch_pubmed(pmids: list[str], *, mailto: str | None = None) -> list[SearchRecord]:
    """``efetch db=pubmed retmode=xml`` → SearchRecord[] (parse con xml.etree)."""
    if not pmids:
        return []
    params = _common_params(mailto)
    params.update({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml", "rettype": "abstract"})
    _throttle()
    with _client() as client:
        resp = client.get(EFETCH_URL, params=params)
        resp.raise_for_status()
        xml = resp.text
    root = ET.fromstring(xml)
    return [_parse_pubmed_article(art) for art in root.findall(".//PubmedArticle")]


def esummary_pmc(pmcids: list[str], *, mailto: str | None = None) -> list[SearchRecord]:
    """``esummary db=pmc`` → SearchRecord[] (metadata ligera; sin abstract)."""
    if not pmcids:
        return []
    params = _common_params(mailto)
    params.update({"db": "pmc", "id": ",".join(pmcids), "retmode": "json"})
    _throttle()
    with _client() as client:
        resp = client.get(ESUMMARY_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    result = data.get("result") or {}
    records: list[SearchRecord] = []
    for uid in result.get("uids") or []:
        doc = result.get(uid) or {}
        doi = None
        for aid in doc.get("articleids") or []:
            if (aid.get("idtype") or "").lower() == "doi":
                doi = (aid.get("value") or "").lower() or None
        authors = [a.get("name", "") for a in doc.get("authors") or [] if a.get("name")]
        year = None
        pubdate = doc.get("pubdate") or ""
        if pubdate[:4].isdigit():
            year = int(pubdate[:4])
        pmcid = f"PMC{uid}"
        records.append(
            SearchRecord(
                record_id=doi or f"pmc:{uid}",
                title=doc.get("title") or "(sin título)",
                abstract=None,
                authors=authors,
                year=year,
                doi=doi,
                url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
                source_db="PMC",
                extra={"pmcid": pmcid},
            )
        )
    return records
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_pmc_ncbi.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add revisia/agents/ncbi.py tests/test_pmc_ncbi.py
git commit -m "feat(search): cliente NCBI E-utilities (esearch/efetch/esummary)"
```

---

### Task 2: Cliente NCBI — texto completo (BioC-PMC) e ID Converter

**Files:**
- Modify: `revisia/agents/ncbi.py` (añadir funciones al final)
- Test: `tests/test_pmc_ncbi.py` (añadir tests; el fake `_RouterClient`/`_FakeResp` y el fixture `_no_sleep` ya existen del Task 1)

**Interfaces:**
- Consumes: helpers `_client`, `_throttle`, `_common_params` del Task 1.
- Produces:
  - `bioc_fulltext(pmcid: str, *, mailto: str | None = None) -> str | None`
  - `idconv(ids: list[str], *, mailto: str | None = None) -> dict[str, str]` (claves en minúsculas: DOI/PMID/PMCID → PMCID)

- [ ] **Step 1: Escribir los tests que fallan** (añadir a `tests/test_pmc_ncbi.py`)

```python
def test_bioc_fulltext_concatena_passages(monkeypatch) -> None:
    _route(monkeypatch, {"BioC_json": _FakeResp(json_data=[
        {"documents": [{"passages": [
            {"text": "Introduccion del articulo."},
            {"text": "Metodos y resultados."},
        ]}]}
    ])})
    text = ncbi.bioc_fulltext("PMC7654321", mailto="x@y.z")
    assert text == "Introduccion del articulo.\n\nMetodos y resultados."


def test_bioc_fulltext_no_oa_devuelve_none(monkeypatch) -> None:
    # Artículo fuera del subconjunto OA: la API no da JSON → None (sin romper).
    _route(monkeypatch, {"BioC_json": _FakeResp(text_data="[Error] : No result can be found.")})
    assert ncbi.bioc_fulltext("PMC0000000", mailto="x@y.z") is None


def test_bioc_fulltext_acepta_pmcid_sin_prefijo(monkeypatch) -> None:
    client = _route(monkeypatch, {"BioC_json": _FakeResp(json_data=[
        {"documents": [{"passages": [{"text": "ok"}]}]}
    ])})
    ncbi.bioc_fulltext("7654321", mailto="x@y.z")
    assert "PMC7654321" in client.calls[0]  # se normaliza a PMC7654321


def test_idconv_mapea_a_pmcid(monkeypatch) -> None:
    _route(monkeypatch, {"idconv": _FakeResp(json_data={
        "records": [{"pmid": "40000001", "doi": "10.1/ABC", "pmcid": "PMC7654321"}]
    })})
    mapping = ncbi.idconv(["10.1/abc"], mailto="x@y.z")
    assert mapping["10.1/abc"] == "PMC7654321"
    assert mapping["40000001"] == "PMC7654321"


def test_idconv_vacio_no_llama_red() -> None:
    assert ncbi.idconv([]) == {}
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_pmc_ncbi.py -k "bioc or idconv" -v`
Expected: FAIL con `AttributeError: module 'revisia.agents.ncbi' has no attribute 'bioc_fulltext'`

- [ ] **Step 3: Añadir las funciones al final de `revisia/agents/ncbi.py`**

```python
def bioc_fulltext(pmcid: str, *, mailto: str | None = None) -> str | None:
    """Texto completo OA vía BioC-PMC (JSON). ``None`` si no está en el subconjunto OA.

    Concatena el ``text`` de todos los *passages* de todos los documentos. Cualquier
    fallo (red, 404, artículo no-OA que devuelve texto de error en vez de JSON) se
    degrada a ``None`` para no romper la corrida.
    """
    pmc = pmcid if pmcid.upper().startswith("PMC") else f"PMC{pmcid}"
    _throttle()
    try:
        with _client() as client:
            resp = client.get(BIOC_URL.format(pmcid=pmc))
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # red caída, 404, cuerpo no-JSON (no-OA) → sin texto
        return None
    docs: list[dict] = []
    if isinstance(data, list):
        for coll in data:
            docs.extend(coll.get("documents") or [])
    elif isinstance(data, dict):
        docs = data.get("documents") or []
    passages = [
        (p.get("text") or "").strip()
        for doc in docs
        for p in (doc.get("passages") or [])
        if (p.get("text") or "").strip()
    ]
    text = "\n\n".join(passages).strip()
    return text or None


def idconv(ids: list[str], *, mailto: str | None = None) -> dict[str, str]:
    """Mapea DOI/PMID → PMCID vía ID Converter (para registros de otras bases).

    Devuelve un dict con claves en minúsculas (el DOI/PMID/PMCID de entrada) → PMCID.
    Cualquier fallo se degrada a ``{}``.
    """
    if not ids:
        return {}
    params = _common_params(mailto)
    params.update({"ids": ",".join(ids), "format": "json"})
    _throttle()
    try:
        with _client() as client:
            resp = client.get(IDCONV_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return {}
    out: dict[str, str] = {}
    for rec in data.get("records") or []:
        pmcid = rec.get("pmcid")
        if not pmcid:
            continue
        for key in ("doi", "pmid", "pmcid"):
            val = rec.get(key)
            if val:
                out[str(val).lower()] = pmcid
    return out
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_pmc_ncbi.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add revisia/agents/ncbi.py tests/test_pmc_ncbi.py
git commit -m "feat(fulltext): BioC-PMC + ID Converter en cliente NCBI"
```

---

### Task 3: Backends de búsqueda PubMed/PMC + reasignación de alias

**Files:**
- Modify: `revisia/agents/search_backends.py`
- Modify: `tests/test_search_multibase.py:18` (corregir comentario obsoleto)
- Test: `tests/test_pmc_ncbi.py` (añadir tests de despacho)

**Interfaces:**
- Consumes: `ncbi.esearch`, `ncbi.efetch_pubmed`, `ncbi.esummary_pmc` (Task 1).
- Produces:
  - `pubmed_search(query, max_results=25, *, mailto=None) -> list[SearchRecord]`
  - `pmc_search(query, max_results=25, *, mailto=None) -> list[SearchRecord]`
  - Alias en `BACKENDS`: `pubmed`/`medline`/`ncbi`/`entrez` → `pubmed_search`; `pmc` → `pmc_search`; `europepmc`/`europe_pmc`/`epmc` → `europepmc_search` (sin cambio).

- [ ] **Step 1: Escribir los tests que fallan** (añadir a `tests/test_pmc_ncbi.py`)

```python
from revisia.agents import search_backends
from revisia.agents.search_backends import available_backends, search_database


def test_alias_pubmed_despacha_a_ncbi(monkeypatch) -> None:
    llamada = {}

    def fake_esearch(db, term, retmax, *, mailto=None):
        llamada["db"] = db
        return ["40000001"]

    def fake_efetch(pmids, *, mailto=None):
        return [SearchRecord(record_id="10.1/abc", title="T", source_db="PubMed")]

    monkeypatch.setattr(ncbi, "esearch", fake_esearch)
    monkeypatch.setattr(ncbi, "efetch_pubmed", fake_efetch)

    records = search_database("pubmed", "llm", 5, mailto="x@y.z")
    assert llamada["db"] == "pubmed"  # fue a NCBI, no a Europe PMC
    assert records[0].source_db == "PubMed"


def test_alias_pmc_despacha_a_esummary(monkeypatch) -> None:
    monkeypatch.setattr(ncbi, "esearch", lambda db, term, retmax, *, mailto=None: ["7654321"])
    monkeypatch.setattr(
        ncbi, "esummary_pmc",
        lambda uids, *, mailto=None: [SearchRecord(record_id="pmc:7654321", title="T", source_db="PMC")],
    )
    records = search_database("pmc", "llm", 5)
    assert records[0].source_db == "PMC"


def test_backends_ncbi_registrados() -> None:
    backends = available_backends()
    for name in ("pubmed", "medline", "pmc", "ncbi", "entrez"):
        assert name in backends
    # Europe PMC conserva sus alias propios.
    for name in ("europepmc", "europe_pmc", "epmc"):
        assert name in backends


def test_europepmc_sigue_disponible(monkeypatch) -> None:
    # La reasignación de 'pubmed' NO debe afectar el backend Europe PMC.
    from revisia.agents import search_backends as sb

    payload = {"resultList": {"result": [
        {"id": "1", "source": "MED", "doi": "10.2/xyz", "title": "EPMC",
         "abstractText": "x", "authorString": "Doe J", "pubYear": "2024"}
    ]}}

    class _C:
        def __enter__(self): return self
        def __exit__(self, *e): return False
        def get(self, url, params=None):
            class _R:
                def raise_for_status(self_inner): return None
                def json(self_inner): return payload
            return _R()

    monkeypatch.setattr(sb, "_client", lambda timeout=60.0: _C())
    records = search_database("europepmc", "q", 5)
    assert records[0].source_db == "EuropePMC"
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_pmc_ncbi.py -k "alias or ncbi_registrados" -v`
Expected: FAIL — `search_database("pmc", ...)` lanza `ValueError` (base sin backend) y `pubmed` aún despacha a Europe PMC.

- [ ] **Step 3: Añadir backends y reasignar alias en `revisia/agents/search_backends.py`**

Cambiar el import (línea 16) para incluir `ncbi`:

```python
from revisia.agents import busqueda, ncbi
```

Añadir las dos funciones justo antes de la sección `# Despacho por nombre lógico de base`:

```python
def pubmed_search(
    query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
    """Busca en PubMed (NCBI E-utilities): esearch(db=pubmed) + efetch."""
    pmids = ncbi.esearch("pubmed", query, max_results, mailto=mailto)
    return ncbi.efetch_pubmed(pmids, mailto=mailto)


def pmc_search(
    query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
    """Busca en PubMed Central (NCBI E-utilities): esearch(db=pmc) + esummary."""
    uids = ncbi.esearch("pmc", query, max_results, mailto=mailto)
    return ncbi.esummary_pmc(uids, mailto=mailto)
```

Reemplazar el dict `BACKENDS` (líneas 161-172) por:

```python
# Despacho por nombre lógico de base (case-insensitive).
BACKENDS: dict[str, SearchFn] = {
    "openalex": busqueda.search,
    "crossref": crossref_search,
    "semanticscholar": semantic_scholar_search,
    "semantic_scholar": semantic_scholar_search,
    "s2": semantic_scholar_search,
    "europepmc": europepmc_search,
    "europe_pmc": europepmc_search,
    "epmc": europepmc_search,
    # PubMed/PMC = NCBI directo (E-utilities). 'pubmed'/'medline' apuntan a NCBI
    # (canónico para PRISMA-S); Europe PMC conserva sus alias 'europepmc'/'epmc'.
    "pubmed": pubmed_search,
    "medline": pubmed_search,
    "ncbi": pubmed_search,
    "entrez": pubmed_search,
    "pmc": pmc_search,
}
```

- [ ] **Step 4: Corregir el comentario obsoleto en `tests/test_search_multibase.py:18`**

Reemplazar la línea:

```python
    assert "pubmed" in backends  # Europe PMC espeja MEDLINE/PubMed
```

por:

```python
    assert "pubmed" in backends  # 'pubmed' → NCBI E-utilities (reasignado); Europe PMC vive en 'europepmc'
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_pmc_ncbi.py tests/test_search_multibase.py -v`
Expected: PASS (todos)

- [ ] **Step 6: Commit**

```bash
git add revisia/agents/search_backends.py tests/test_pmc_ncbi.py tests/test_search_multibase.py
git commit -m "feat(search): backends PubMed/PMC (NCBI) + reasignación de alias pubmed→NCBI"
```

---

### Task 4: Texto completo BioC preferente en `fulltext.py`

**Files:**
- Modify: `revisia/agents/fulltext.py`
- Test: `tests/test_pmc_ncbi.py` (añadir tests de fulltext)

**Interfaces:**
- Consumes: `ncbi.bioc_fulltext`, `ncbi.idconv` (Task 2); `FullText`, `resolve_oa_url` (existentes).
- Produces: `fetch_fulltext` prioriza BioC-PMC; helper nuevo `_resolve_pmcid(record, *, mailto=None) -> str | None`.

- [ ] **Step 1: Escribir los tests que fallan** (añadir a `tests/test_pmc_ncbi.py`)

```python
from revisia.agents import fulltext


def test_fetch_fulltext_prefiere_bioc(monkeypatch) -> None:
    monkeypatch.setattr(fulltext.ncbi, "bioc_fulltext", lambda pmcid, *, mailto=None: "TEXTO COMPLETO OA")
    rec = SearchRecord(record_id="x", title="T", extra={"pmcid": "PMC7654321"})
    ft = fulltext.fetch_fulltext(rec, mailto="x@y.z")
    assert ft.available is True
    assert ft.text == "TEXTO COMPLETO OA"
    assert "PMC7654321" in (ft.source_url or "")


def test_fetch_fulltext_resuelve_pmcid_por_doi(monkeypatch) -> None:
    monkeypatch.setattr(fulltext.ncbi, "idconv", lambda ids, *, mailto=None: {"10.1/abc": "PMC999"})
    llamado = {}

    def fake_bioc(pmcid, *, mailto=None):
        llamado["pmcid"] = pmcid
        return "OA por idconv"

    monkeypatch.setattr(fulltext.ncbi, "bioc_fulltext", fake_bioc)
    rec = SearchRecord(record_id="10.1/abc", title="T", doi="10.1/abc")
    ft = fulltext.fetch_fulltext(rec, mailto="x@y.z")
    assert llamado["pmcid"] == "PMC999"
    assert ft.available is True and ft.text == "OA por idconv"


def test_fetch_fulltext_sin_pmcid_ni_mailto_no_toca_red(monkeypatch) -> None:
    # Sin PMCID y sin mailto: no se llama a idconv (invariante de red) → fallback abstract.
    def boom(*a, **k):
        raise AssertionError("no debe llamarse a idconv sin mailto")

    monkeypatch.setattr(fulltext.ncbi, "idconv", boom)
    rec = SearchRecord(record_id="x", title="T", doi="10.1/abc", abstract="solo abstract")
    ft = fulltext.fetch_fulltext(rec, mailto=None)
    assert ft.available is False
    assert ft.text == "solo abstract"


def test_fetch_fulltext_bioc_no_oa_cae_a_abstract(monkeypatch) -> None:
    monkeypatch.setattr(fulltext.ncbi, "idconv", lambda ids, *, mailto=None: {"10.1/abc": "PMC999"})
    monkeypatch.setattr(fulltext.ncbi, "bioc_fulltext", lambda pmcid, *, mailto=None: None)  # no OA
    rec = SearchRecord(record_id="10.1/abc", title="T", doi="10.1/abc", abstract="abs")
    ft = fulltext.fetch_fulltext(rec, mailto="x@y.z")
    assert ft.available is False and ft.text == "abs"
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_pmc_ncbi.py -k "fetch_fulltext" -v`
Expected: FAIL — `AttributeError: module 'revisia.agents.fulltext' has no attribute 'ncbi'` (aún no se importa).

- [ ] **Step 3: Integrar BioC en `revisia/agents/fulltext.py`**

Añadir el import de `ncbi` junto al import de `SearchRecord` (tras la línea 18):

```python
from revisia.agents import ncbi
```

Añadir el helper `_resolve_pmcid` justo antes de `def fetch_fulltext(`:

```python
def _resolve_pmcid(record: SearchRecord, *, mailto: str | None = None) -> str | None:
    """PMCID del registro: directo de ``extra``, o resuelto por DOI/PMID vía ID Converter.

    La resolución por DOI/PMID solo se intenta si hay ``mailto`` (no golpear NCBI sin
    email, igual que Unpaywall). ``extra['pmcid']`` no necesita red.
    """
    pmcid = record.extra.get("pmcid")
    if pmcid:
        return str(pmcid)
    ident = record.extra.get("pmid") or record.doi
    if not ident or not mailto:
        return None
    return ncbi.idconv([str(ident)], mailto=mailto).get(str(ident).lower())
```

Reemplazar el cuerpo de `fetch_fulltext` (líneas 86-114) por la versión que antepone BioC:

```python
def fetch_fulltext(
    record: SearchRecord, *, mailto: str | None = None, max_chars: int = 20000
) -> FullText:
    """Descarga el texto completo OA de un estudio, con fallback al abstract.

    Prioridad: BioC-PMC (texto estructurado, sin parsear PDF) si hay PMCID
    resoluble > raspado OA (``extra.fulltext_url``/``oa_url``) > Unpaywall.
    """
    fallback = FullText(text=record.abstract or "", available=False)

    # 1) BioC-PMC: texto completo estructurado si el registro está en el subconjunto OA.
    pmcid = _resolve_pmcid(record, mailto=mailto)
    if pmcid:
        bioc = ncbi.bioc_fulltext(pmcid, mailto=mailto)
        if bioc:
            return FullText(
                text=bioc[:max_chars],
                available=True,
                source_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
            )

    # 2) Fallback: raspado OA / Unpaywall (comportamiento previo, intacto).
    url = resolve_oa_url(record, mailto=mailto)
    if not url:
        return fallback
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return fallback
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            raw = resp.content
    except Exception:
        return fallback

    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        text = _extract_pdf(raw)
    else:
        text = strip_html(raw.decode("utf-8", errors="ignore"))

    if not text:
        return fallback
    return FullText(text=text[:max_chars], available=True, source_url=url)
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_pmc_ncbi.py -v`
Expected: PASS (todos los del archivo)

- [ ] **Step 5: Correr la suite completa (invariante offline intacta)**

Run: `uv run pytest -q`
Expected: PASS — 144 previas + nuevas, sin red.

- [ ] **Step 6: Commit**

```bash
git add revisia/agents/fulltext.py tests/test_pmc_ncbi.py
git commit -m "feat(fulltext): BioC-PMC como fuente de texto completo preferente"
```

---

### Task 5: Documentación, plantilla, `.env.example` y CHANGELOG

**Files:**
- Modify: `docs/integraciones.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `protocols/_TEMPLATE/protocol.yml`
- Create: `protocols/_TEMPLATE/search_strings/pubmed.txt`
- Modify: `.env.example`

**Interfaces:**
- Consumes: nombres de base y comportamiento definidos en Tasks 1-4.
- Produces: documentación coherente con la reasignación de alias y las dos capacidades nuevas.

- [ ] **Step 1: `docs/integraciones.md` — añadir dos filas a "Integradas"**

Tras la fila de Europe PMC (línea 15), insertar:

```markdown
| [PubMed / PMC (NCBI E-utilities)](https://www.ncbi.nlm.nih.gov/books/NBK25501/) | Búsqueda | API abierta (`NCBI_API_KEY` opcional: 3→10 req/s) | Backend nativo (`agents/ncbi.py` + `search_backends.py`); alias `pubmed`/`medline` → NCBI, `pmc` opt-in |
| [BioC-PMC](https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/) | Texto completo OA | API abierta | Texto completo estructurado (JSON) del subconjunto OA por PMCID en `agents/fulltext.py`, preferente al raspado de PDF |
```

- [ ] **Step 2: `README.md` — actualizar la línea de "búsqueda multi-base"**

En la sección **Estado** (línea 145-148), reemplazar el fragmento:

```
**búsqueda multi-base**
(OpenAlex / Crossref / Semantic Scholar / **Europe PMC (MEDLINE/PubMed)** + import
RIS/BibTeX para Scopus/WoS);
```

por:

```
**búsqueda multi-base**
(OpenAlex / Crossref / Semantic Scholar / **PubMed + PMC (NCBI E-utilities)** /
Europe PMC + import RIS/BibTeX para Scopus/WoS; **texto completo OA estructurado
vía BioC-PMC**);
```

- [ ] **Step 3: `CHANGELOG.md` — añadir entrada (con nota breaking del alias)**

Añadir bajo la sección de la próxima versión (crear el encabezado si no existe, en la parte superior del archivo):

```markdown
### Añadido
- **Backend NCBI E-utilities** (`revisia/agents/ncbi.py`): búsqueda PubMed
  (`esearch`+`efetch`) y PMC opt-in (`esummary`), con cortesía NCBI y
  `NCBI_API_KEY` opcional. PubMed queda como línea de búsqueda canónica y
  citable para PRISMA-S.
- **Texto completo OA estructurado vía BioC-PMC**: `agents/fulltext.py` prioriza
  el texto BioC (JSON, sin parsear PDF) cuando hay PMCID (directo o resuelto por
  ID Converter), mejorando cribado full-text y extracción.

### Cambiado (breaking menor)
- Los alias `pubmed` y `medline` ahora apuntan a **NCBI** (antes a Europe PMC).
  Europe PMC conserva sus alias propios: `europepmc` / `europe_pmc` / `epmc`.
  Protocolos que usaban `pubmed` esperando Europe PMC deben cambiarlo a `europepmc`.
```

- [ ] **Step 4: `protocols/_TEMPLATE/protocol.yml` — añadir PubMed al default**

Reemplazar el bloque `databases` (líneas 21-29) por:

```yaml
# Bases de datos / fuentes a consultar (la búsqueda usa search_strings/<base>.txt).
# Bases abiertas por defecto (sin API key). PubMed = NCBI directo (E-utilities),
# línea citable para PRISMA-S; Europe PMC espeja PubMed/PMC (procedencia distinta,
# el dedup une el solape). 'pmc' (texto completo NCBI) está disponible como opt-in.
# Scopus/Web of Science no tienen API abierta: expórtalos a RIS/BibTeX y déjalos
# en imported/ (se fusionan en la deduplicación).
databases:
  - OpenAlex
  - Crossref
  - Semantic Scholar
  - PubMed
  - Europe PMC
```

- [ ] **Step 5: Crear `protocols/_TEMPLATE/search_strings/pubmed.txt`**

```text
("artificial intelligence"[tiab] OR "machine learning"[tiab] OR "large language models"[tiab]) AND ("systematic review"[tiab] OR "evidence synthesis"[tiab]) AND (screening[tiab] OR "data extraction"[tiab] OR "risk of bias"[tiab])
```

- [ ] **Step 6: `.env.example` — añadir bloque `NCBI_API_KEY` opcional**

Tras el bloque de OpenRouter (línea 44), insertar:

```bash

# ── NCBI E-utilities (búsqueda PubMed/PMC + texto completo BioC-PMC) ─────
# OPCIONAL. Sin key funciona igual, solo con menos cuota (3 req/s → 10 req/s).
# Acúñala en https://www.ncbi.nlm.nih.gov/account/ (Settings → API Key Management).
NCBI_API_KEY=
```

- [ ] **Step 7: Verificar que la suite sigue verde tras los cambios de plantilla**

Run: `uv run pytest -q`
Expected: PASS (el `_TEMPLATE` con 5 bases carga y valida; `test_config.py` solo exige OpenAlex presente).

- [ ] **Step 8: Commit**

```bash
git add docs/integraciones.md README.md CHANGELOG.md protocols/_TEMPLATE/protocol.yml protocols/_TEMPLATE/search_strings/pubmed.txt .env.example
git commit -m "docs: documenta integración PMC/NCBI (PubMed/PMC + BioC-PMC) y reasignación de alias"
```

---

## Self-Review (completado)

**1. Cobertura del spec:**
- §4.1 cliente NCBI (esearch/efetch/esummary/bioc/idconv/throttle/key) → Tasks 1-2. ✅
- §4.2 pubmed_search/pmc_search + reasignación de alias → Task 3. ✅
- §4.3 BioC preferente + fallback + gate por mailto → Task 4. ✅
- §5 flujo de datos (source_db PubMed/PMC en PRISMA vía dedup; PMCID→BioC) → cubierto por Tasks 3-4 (no requiere cambios en pipeline: usa el despacho y `fetch_fulltext` existentes). ✅
- §6 degradación: BioC/idconv capturan errores → None/{} (Task 2); búsqueda propaga como los demás backends (comportamiento existente, no se sobre-promete). ✅
- §8 tests offline (esearch, efetch, esummary, bioc, idconv, aliases, fulltext, invariante de red) → Tasks 1-4. ✅
- §9 docs → Task 5. ✅

**2. Placeholder scan:** sin TBD/TODO; todo el código y los payloads de test están completos. ✅

**3. Consistencia de tipos:** `esearch`→`list[str]`; `efetch_pubmed`/`esummary_pmc`→`list[SearchRecord]`; `bioc_fulltext`→`str | None`; `idconv`→`dict[str,str]`; `_resolve_pmcid`→`str | None`; `pubmed_search`/`pmc_search` cumplen `SearchFn`. Nombres idénticos entre tasks (`ncbi.esearch`, `ncbi.efetch_pubmed`, `ncbi.esummary_pmc`, `ncbi.bioc_fulltext`, `ncbi.idconv`, `fulltext.ncbi`). ✅

**Nota de reconciliación con el spec:** el spec (§6) sugería que la búsqueda "degrada" ante errores de red; en la práctica los backends existentes propagan el error de red (solo se captura `ValueError` de base desconocida en el pipeline). Este plan mantiene esa consistencia y concentra la degradación en el camino de texto completo (BioC/idconv), que sí captura y cae al abstract.
