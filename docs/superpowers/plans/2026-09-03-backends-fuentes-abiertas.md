# Backends de fuentes abiertas · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir ocho backends de búsqueda abiertos (ERIC, DOAJ, UNESDOC, BVS/LILACS, AGROSAVIA, CLACSO, Banco Mundial OKR, DOAB) con un adaptador DSpace 7+ genérico y degradación por base en el pipeline.

**Architecture:** Tres módulos nuevos bajo `revisia/agents/`: `_http.py` (cliente httpx compartido con User-Agent identificado), `open_backends.py` (ERIC, DOAJ, UNESDOC, BVS: REST JSON sin estado) y `dspace.py` (adaptador DSpace 7+ parametrizado + DOAB DSpace 6). `search_backends.py` solo registra alias. El pipeline captura fallos de red por base y los escribe en `01_search/failures.json`.

**Tech Stack:** Python 3.13, `httpx` (extra `search`, ya existente), pydantic `SearchRecord`, pytest con clientes falsos (offline). Cero dependencias nuevas.

## Global Constraints

- Firma de backend: `fn(query: str, max_results: int = 25, *, mailto: str | None = None) -> list[SearchRecord]`.
- `record_id` = DOI normalizado (minúsculas, sin `https://doi.org/`) o `"<fuente>:<id nativo>"`.
- Sin API keys; sin dependencias nuevas; tests sin red.
- `ruff` limpio (line-length 100, reglas E/F/I/UP/B/SIM).
- Los 168 tests existentes siguen en verde en cada commit.
- Commits en español, con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

### Task 1: `_http.py` compartido + URL nueva de idconv

**Files:**
- Create: `revisia/agents/_http.py`
- Modify: `revisia/agents/search_backends.py:26-41` (`_client`, `_strip_html`)
- Modify: `revisia/agents/ncbi.py:24` (`IDCONV_URL`), `:48-55` (`_client`)
- Test: `tests/test_open_backends.py` (nuevo, primer test)

**Interfaces:**
- Produces: `_http.make_client(timeout: float = 60.0, *, mailto: str | None = None) -> httpx.Client`; `_http.strip_html(text: str | None) -> str | None`; `_http.user_agent(mailto) -> str`.

- [ ] **Step 1: Test que falla**

```python
# tests/test_open_backends.py
"""Tests de los backends abiertos nuevos (ERIC, DOAJ, UNESDOC, BVS). Todo offline."""

from __future__ import annotations

from revisia.agents import _http


def test_user_agent_identifica_a_revisia() -> None:
    assert _http.user_agent(None).startswith("revisia/")
    assert "mailto:x@y.z" in _http.user_agent("x@y.z")


def test_strip_html_limpia_etiquetas() -> None:
    assert _http.strip_html("<p>Hola <b>mundo</b></p>") == "Hola mundo"
    assert _http.strip_html(None) is None
    assert _http.strip_html("<p></p>") is None
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest tests/test_open_backends.py -q`
Expected: `ImportError: cannot import name '_http'`

- [ ] **Step 3: Implementar**

```python
# revisia/agents/_http.py
"""Cliente HTTP compartido por los backends de búsqueda.

Un solo lugar para el cliente ``httpx`` (timeout, redirecciones, User-Agent
identificado) y para limpiar HTML de abstracts. Los backends lo usan vía una
indirección local (``_client``) para que los tests puedan sustituirlo.
"""

from __future__ import annotations

import re
from typing import Any

from revisia import __version__

_TAG_RE = re.compile(r"<[^>]+>")


def user_agent(mailto: str | None = None) -> str:
    """User-Agent identificado (cortesía estándar; BVS lo requiere)."""
    base = f"revisia/{__version__}"
    return f"{base} (mailto:{mailto})" if mailto else base


def make_client(timeout: float = 60.0, *, mailto: str | None = None) -> Any:
    """Cliente httpx con timeout, follow_redirects y User-Agent."""
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RuntimeError(
            "Los backends de búsqueda requieren httpx. Instala el extra: `uv sync --extra search`."
        ) from exc
    return httpx.Client(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent(mailto)}
    )


def strip_html(text: str | None) -> str | None:
    """Quita etiquetas HTML; ``None`` si no queda texto."""
    if not text:
        return None
    return _TAG_RE.sub("", text).strip() or None
```

En `search_backends.py`, sustituir `_client` y `_strip_html` por delegaciones (se conservan los nombres porque los tests existentes los parchean):

```python
from revisia.agents import _http, busqueda, ncbi


def _client(timeout: float = 60.0) -> Any:
    return _http.make_client(timeout)


_strip_html = _http.strip_html
```

(borrar el `import re` local dentro de `_strip_html`). En `ncbi.py`:

```python
IDCONV_URL = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
```

y

```python
from revisia.agents import _http


def _client(timeout: float = 60.0) -> Any:
    return _http.make_client(timeout)
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -q`
Expected: 170 passed (168 + 2 nuevos)

- [ ] **Step 5: Commit**

```bash
git add revisia/agents/_http.py revisia/agents/search_backends.py revisia/agents/ncbi.py tests/test_open_backends.py
git commit -m "refactor(search): cliente httpx compartido (_http) + URL nueva del ID Converter de PMC"
```

---

### Task 2: ERIC y DOAJ

**Files:**
- Create: `revisia/agents/open_backends.py`
- Test: `tests/test_open_backends.py`

**Interfaces:**
- Consumes: `_http.make_client`, `_http.strip_html`.
- Produces: `open_backends.eric_search`, `open_backends.doaj_search` (firma estándar); helpers `_year(value) -> int | None`, `_doi(value) -> str | None`, `_client(timeout=60.0, *, mailto=None)`.

- [ ] **Step 1: Tests que fallan** (añadir a `tests/test_open_backends.py`)

```python
from revisia.agents import open_backends


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
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest tests/test_open_backends.py -q`
Expected: `ImportError: cannot import name 'open_backends'`

- [ ] **Step 3: Implementar**

```python
# revisia/agents/open_backends.py
"""Backends abiertos adicionales: ERIC, DOAJ, UNESDOC (DataHub) y BVS/LILACS.

Cuatro APIs REST JSON sin API key, verificadas en vivo (2026-09-03; ver
``docs/fuentes-triage.md``). Todas comparten la firma estándar
``fn(query, max_results, *, mailto) -> list[SearchRecord]`` y se registran por
alias en :mod:`revisia.agents.search_backends`. La sintaxis de la cadena es la de
cada motor (Lucene en ERIC, Elasticsearch en DOAJ, ODSQL en UNESDOC, iAHx/Solr en
BVS) y la escribe el investigador en ``search_strings/<alias>.txt``.
"""

from __future__ import annotations

from functools import partial
from typing import Any
from urllib.parse import quote

from revisia.agents import _http
from revisia.schemas.records import SearchRecord

ERIC_URL = "https://api.ies.ed.gov/eric/"
ERIC_FIELDS = (
    "id,title,author,publicationdateyear,description,url,language,peerreviewed,publicationtype"
)
DOAJ_URL = "https://doaj.org/api/search/articles/"
UNESDOC_URL = "https://data.unesco.org/api/explore/v2.1/catalog/datasets/doc001/records"
BVS_URL = "https://search.bvsalud.org/{instance}/"


def _client(timeout: float = 60.0, *, mailto: str | None = None) -> Any:
    return _http.make_client(timeout, mailto=mailto)


def _year(value: Any) -> int | None:
    """Año desde int, ``"2024"``, ``"2024-09-01"`` o ``"202707"`` (YYYYMM)."""
    if value is None:
        return None
    try:
        return int(str(value).strip()[:4])
    except (TypeError, ValueError):
        return None


def _doi(value: Any) -> str | None:
    """DOI normalizado: minúsculas, sin prefijos ``https://doi.org/`` / ``doi:``."""
    if not value:
        return None
    text = str(value).strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
    text = text.lower().strip()
    return text if text.startswith("10.") else None


def _first(value: Any) -> Any:
    """Primer elemento si es lista; el valor tal cual si no."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


# ── ERIC ──────────────────────────────────────────────────────────────


def eric_search(query: str, max_results: int = 25, *, mailto: str | None = None) -> list[SearchRecord]:
    """Busca en ERIC (IES/US Dept. of Education): artículos EJ + documentos ED."""
    params: dict[str, Any] = {
        "search": query,
        "format": "json",
        "rows": min(max_results, 2000),
        "start": 0,
        "fields": ERIC_FIELDS,
    }
    with _client(mailto=mailto) as client:
        resp = client.get(ERIC_URL, params=params)
        resp.raise_for_status()
        docs = (resp.json().get("response") or {}).get("docs", [])[:max_results]
    records: list[SearchRecord] = []
    for d in docs:
        eric_id = str(d.get("id") or len(records))
        url = d.get("url")
        doi = _doi(url) if url and "doi.org/" in url else None
        authors = d.get("author") or []
        if isinstance(authors, str):
            authors = [authors]
        records.append(
            SearchRecord(
                record_id=doi or f"eric:{eric_id}",
                title=d.get("title") or "(sin título)",
                abstract=_http.strip_html(d.get("description")),
                authors=[a for a in authors if a],
                year=_year(d.get("publicationdateyear")),
                doi=doi,
                url=url or f"https://eric.ed.gov/?id={eric_id}",
                source_db="ERIC",
                extra={
                    "eric_id": eric_id,
                    "peer_reviewed": d.get("peerreviewed") == "T",
                    "language": d.get("language") or [],
                    "publication_type": d.get("publicationtype") or [],
                },
            )
        )
    return records


# ── DOAJ ──────────────────────────────────────────────────────────────


def _doaj_record(item: dict[str, Any]) -> SearchRecord:
    bib = item.get("bibjson") or {}
    doi = next(
        (_doi(i.get("id")) for i in bib.get("identifier") or [] if i.get("type") == "doi"),
        None,
    )
    oa_url = next(
        (link.get("url") for link in bib.get("link") or [] if link.get("type") == "fulltext"),
        None,
    )
    journal = bib.get("journal") or {}
    extra: dict[str, Any] = {"journal": journal.get("title"), "language": journal.get("language")}
    if oa_url:
        extra["oa_url"] = oa_url
    return SearchRecord(
        record_id=doi or f"doaj:{item.get('id')}",
        title=bib.get("title") or "(sin título)",
        abstract=_http.strip_html(bib.get("abstract")),
        authors=[a.get("name", "") for a in bib.get("author") or [] if a.get("name")],
        year=_year(bib.get("year")),
        doi=doi,
        url=(f"https://doi.org/{doi}" if doi else oa_url),
        source_db="DOAJ",
        extra={k: v for k, v in extra.items() if v},
    )


def doaj_search(query: str, max_results: int = 25, *, mailto: str | None = None) -> list[SearchRecord]:
    """Busca artículos en DOAJ (API abierta, CC0; 100 por página, 2 req/s)."""
    page_size = min(max_results, 100)
    url = DOAJ_URL + quote(query, safe="")
    records: list[SearchRecord] = []
    page = 1
    with _client(mailto=mailto) as client:
        while len(records) < max_results:
            resp = client.get(url, params={"page": page, "pageSize": page_size})
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            if not results:
                break
            records.extend(_doaj_record(it) for it in results)
            if len(results) < page_size or len(records) >= int(data.get("total") or 0):
                break
            page += 1
    return records[:max_results]
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest tests/test_open_backends.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add revisia/agents/open_backends.py tests/test_open_backends.py
git commit -m "feat(search): backends ERIC y DOAJ (API abierta, sin key)"
```

---

### Task 3: UNESDOC y BVS/LILACS

**Files:**
- Modify: `revisia/agents/open_backends.py` (añadir al final)
- Test: `tests/test_open_backends.py`

**Interfaces:**
- Produces: `open_backends.unesdoc_search`, `open_backends.bvs_search(query, max_results=25, *, mailto=None, instance="portal", source_db="BVS")`, `open_backends.gim_search` (partial de `bvs_search`), `open_backends._unesdoc_where(query) -> str`.

- [ ] **Step 1: Tests que fallan**

```python
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
    assert client.calls[1][1]["from"] == 3  # 2 docs servidos → siguiente arranca en 3
    assert [r.record_id for r in records] == ["10.48061/san.2026.27.1.95", "bvs:biblio-2", "bvs:biblio-3"]
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
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest tests/test_open_backends.py -q`
Expected: `AttributeError: module ... has no attribute 'unesdoc_search'`

- [ ] **Step 3: Implementar** (añadir a `open_backends.py`)

```python
# ── UNESDOC (UNESCO DataHub · Opendatasoft) ───────────────────────────


def _unesdoc_where(query: str) -> str:
    """Cadena simple → ``search("…")``; cadena ODSQL (contiene ``search(``) → tal cual."""
    if "search(" in query:
        return query
    escaped = query.replace("\\", "\\\\").replace('"', '\\"')
    return f'search("{escaped}")'


def unesdoc_search(query: str, max_results: int = 25, *, mailto: str | None = None) -> list[SearchRecord]:
    """Busca en UNESDOC vía UNESCO DataHub (dataset ``doc001``; snapshot del catálogo)."""
    limit = min(max_results, 100)
    records: list[SearchRecord] = []
    offset = 0
    with _client(mailto=mailto) as client:
        while len(records) < max_results:
            params = {"where": _unesdoc_where(query), "limit": limit, "offset": offset}
            resp = client.get(UNESDOC_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            if not results:
                break
            for it in results:
                uuid = it.get("uuid") or it.get("id") or str(len(records))
                creator = it.get("creator")
                extra = {
                    "language": it.get("language") or [],
                    "document_type": it.get("document_type"),
                    "isbn": it.get("isbn"),
                }
                records.append(
                    SearchRecord(
                        record_id=f"unesdoc:{uuid}",
                        title=it.get("title") or "(sin título)",
                        abstract=_http.strip_html(it.get("description")),
                        authors=[creator] if creator else [],
                        year=_year(_first(it.get("year"))),
                        doi=None,
                        url=it.get("url"),
                        source_db="UNESDOC",
                        extra={k: v for k, v in extra.items() if v},
                    )
                )
            offset += len(results)
            if len(results) < limit or offset >= int(data.get("total_count") or 0):
                break
    return records[:max_results]


# ── BVS / LILACS (iAHx) ───────────────────────────────────────────────


def _bvs_record(doc: dict[str, Any], source_db: str) -> SearchRecord:
    doi = _doi(_first(doc.get("aid")))
    native = str(doc.get("id") or "")
    url = _first(doc.get("ur"))
    extra = {
        "lilacs_id": native,
        "language": doc.get("la") or [],
        "db": doc.get("db") or [],
        "issn": doc.get("is") or [],
    }
    return SearchRecord(
        record_id=doi or f"{source_db.lower()}:{native}",
        title=_first(doc.get("ti")) or "(sin título)",
        abstract=_http.strip_html(_first(doc.get("ab"))),
        authors=[a for a in doc.get("au") or [] if a],
        year=_year(doc.get("da")),
        doi=doi,
        url=url or (f"https://doi.org/{doi}" if doi else None),
        source_db=source_db,
        extra={k: v for k, v in extra.items() if v},
    )


def bvs_search(
    query: str,
    max_results: int = 25,
    *,
    mailto: str | None = None,
    instance: str = "portal",
    source_db: str = "BVS",
) -> list[SearchRecord]:
    """Busca en la BVS (iAHx). ``portal`` = BVS regional (LILACS+); ``gim`` = Global Index Medicus.

    ``from`` es 1-based; hasta 500 registros por petición. El filtro de año va en
    la cadena (``year_cluster:[2020 TO 2024]``), no como ``filter=``.
    """
    count = min(max_results, 500)
    records: list[SearchRecord] = []
    offset = 0
    url = BVS_URL.format(instance=instance)
    with _client(mailto=mailto) as client:
        while len(records) < max_results:
            params = {"output": "json", "lang": "es", "q": query, "count": count, "from": offset + 1}
            resp = client.get(url, params=params)
            resp.raise_for_status()
            dia = (resp.json().get("diaServerResponse") or [{}])[0]
            response = dia.get("response") or {}
            docs = response.get("docs") or []
            if not docs:
                break
            records.extend(_bvs_record(d, source_db) for d in docs)
            offset += len(docs)
            if len(docs) < count or offset >= int(response.get("numFound") or 0):
                break
    return records[:max_results]


gim_search = partial(bvs_search, instance="gim", source_db="GIM")
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest tests/test_open_backends.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add revisia/agents/open_backends.py tests/test_open_backends.py
git commit -m "feat(search): backends UNESDOC (DataHub) y BVS/LILACS (iAHx)"
```

---

### Task 4: Adaptador DSpace 7+ (AGROSAVIA, CLACSO, Banco Mundial OKR) y DOAB

**Files:**
- Create: `revisia/agents/dspace.py`
- Test: `tests/test_dspace.py`

**Interfaces:**
- Consumes: `_http.make_client`, `_http.strip_html`; `open_backends._year`, `open_backends._doi` (reutilizados por import).
- Produces: `dspace.dspace7_search(query, max_results=25, *, mailto=None, base_url: str, source_db: str)`; partials `agrosavia_search`, `clacso_search`, `worldbank_okr_search`; `dspace.doab_search`; constantes `AGROSAVIA_URL`, `CLACSO_URL`, `WORLDBANK_OKR_URL`, `DOAB_URL`.

- [ ] **Step 1: Tests que fallan**

```python
# tests/test_dspace.py
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
                "page": {"number": number, "size": 2, "totalPages": total_pages, "totalElements": 3},
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
    client = _FakeClient(_hal([OKR_ITEM, CLACSO_ITEM], total_pages=2), _hal([CLACSO_ITEM], total_pages=2, number=1))
    _patch(monkeypatch, client)
    records = dspace.worldbank_okr_search("pobreza", 3, mailto="x@y.z")
    url, params = client.calls[0]
    assert url == "https://openknowledge.worldbank.org/server/api/discover/search/objects"
    assert params == {"query": "pobreza", "dsoType": "item", "page": 0, "size": 3}
    assert client.calls[1][1]["page"] == 1 and len(records) == 3
    r0, r1 = records[0], records[1]
    assert r0.record_id == "10.1596/21037" and r0.title == "Towards Sustainable Peace"
    assert r0.extra["titles"] == ["Hacia la paz sostenible"] and r0.extra["oa_url"].endswith(".pdf")
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
            {"key": "dc.identifier.uri", "value": "https://directory.doabooks.org/handle/20.500.12854/97644"},
        ],
    },
    {"uuid": "b2", "handle": "20.500.12854/2", "metadata": [{"key": "dc.title", "value": "Libro 2"}]},
]


def test_doab_parse_y_paginacion_sin_total(monkeypatch) -> None:
    client = _FakeClient(DOAB_ITEMS, [])
    _patch(monkeypatch, client)
    records = dspace.doab_search("economics", 5)
    assert client.calls[0][1] == {"query": "economics", "expand": "metadata", "limit": 5, "offset": 0}
    assert client.calls[1][1]["offset"] == 2 and len(records) == 2
    r0, r1 = records
    assert r0.record_id == "10.1093/oso/9780198830504.001.0001" and r0.year == 2019
    assert r0.authors == ["Oqubay, Arkebe"] and r0.abstract == "Resumen"
    assert r0.source_db == "DOAB" and r0.extra["type"] == "book"
    assert r1.record_id == "doab:20.500.12854/2"
    assert r1.url == "https://directory.doabooks.org/handle/20.500.12854/2"


def test_doab_pagina_corta_no_pide_mas(monkeypatch) -> None:
    client = _FakeClient(DOAB_ITEMS[:1])
    _patch(monkeypatch, client)
    dspace.doab_search("q", 50)
    assert len(client.calls) == 1
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest tests/test_dspace.py -q`
Expected: `ImportError: cannot import name 'dspace'`

- [ ] **Step 3: Implementar**

```python
# revisia/agents/dspace.py
"""Adaptador DSpace (REST) · repositorios institucionales y DOAB.

DSpace 7+ es el estándar de facto de los repositorios LATAM e institucionales
(verificado en AGROSAVIA 9.1, CLACSO 10, Banco Mundial OKR 7). Todos exponen la
misma API HAL ``/server/api/discover/search/objects``; aquí hay **un** adaptador
parametrizado por URL base y nombre de fuente, y tres instancias registradas.
Añadir otro repositorio es una línea::

    mi_repo_search = partial(dspace7_search, base_url="https://…", source_db="MiRepo")

DOAB (Directory of Open Access Books) corre DSpace 6, cuya API ``/rest/search``
devuelve los metadatos como lista plana ``{key, value}``; comparte el mapeo
Dublin Core → ``SearchRecord``.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from revisia.agents import _http
from revisia.agents.open_backends import _doi, _year
from revisia.schemas.records import SearchRecord

AGROSAVIA_URL = "https://repository.agrosavia.co"
CLACSO_URL = "https://biblioteca-repositorio.clacso.edu.ar"
WORLDBANK_OKR_URL = "https://openknowledge.worldbank.org"
DOAB_URL = "https://directory.doabooks.org/rest/search"

_AUTHOR_KEYS = ("dc.contributor.author", "dc.contributor.editor", "dc.contributor.corporatename")
_DOI_KEYS = ("dc.identifier.doi", "oapen.identifier.doi")
_LANG_KEYS = ("dc.language.iso", "dc.language")


def _client(timeout: float = 60.0, *, mailto: str | None = None) -> Any:
    return _http.make_client(timeout, mailto=mailto)


def _values(meta: dict[str, list[str]], *keys: str) -> list[str]:
    """Concatena los valores de los primeros campos presentes en ``keys``."""
    out: list[str] = []
    for key in keys:
        out.extend(v for v in meta.get(key, []) if v)
    return out


def _dc_record(
    meta: dict[str, list[str]],
    *,
    source_db: str,
    native_id: str,
    url_fallback: str,
    extra: dict[str, Any] | None = None,
) -> SearchRecord:
    """Mapea metadatos Dublin Core (campo → lista de valores) a un SearchRecord."""
    titles = _values(meta, "dc.title")
    doi = next((d for d in (_doi(v) for v in _values(meta, *_DOI_KEYS)) if d), None)
    authors = _values(meta, _AUTHOR_KEYS[0]) or _values(meta, *_AUTHOR_KEYS[1:])
    uri = next(iter(_values(meta, "dc.identifier.uri")), None)
    extras: dict[str, Any] = dict(extra or {})
    if len(titles) > 1:
        extras["titles"] = titles[1:]
    language = _values(meta, *_LANG_KEYS)
    if language:
        extras["language"] = language
    isbn = _values(meta, "dc.identifier.isbn")
    if isbn:
        extras["isbn"] = isbn
    pdf = next(iter(_values(meta, "okr.pdfurl")), None)
    if pdf:
        extras["oa_url"] = pdf
    return SearchRecord(
        record_id=doi or f"{source_db.lower()}:{native_id}",
        title=titles[0] if titles else "(sin título)",
        abstract=_http.strip_html(next(iter(_values(meta, "dc.description.abstract")), None)),
        authors=authors,
        year=_year(next(iter(_values(meta, "dc.date.issued")), None)),
        doi=doi,
        url=uri or url_fallback,
        source_db=source_db,
        extra=extras,
    )


# ── DSpace 7+ (HAL) ───────────────────────────────────────────────────


def _group_hal(metadata: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    return {k: [str(x.get("value")) for x in v if x.get("value")] for k, v in metadata.items()}


def dspace7_search(
    query: str,
    max_results: int = 25,
    *,
    mailto: str | None = None,
    base_url: str,
    source_db: str,
) -> list[SearchRecord]:
    """Busca ítems en un DSpace 7+ vía ``discover/search/objects`` (texto libre Solr).

    El filtro de año va en la cadena (``… AND dc.date.issued:[2020 TO 2024]``):
    la sintaxis de facetas varía entre instancias.
    """
    base = base_url.rstrip("/")
    url = f"{base}/server/api/discover/search/objects"
    size = min(max_results, 100)
    records: list[SearchRecord] = []
    page = 0
    with _client(mailto=mailto) as client:
        while len(records) < max_results:
            resp = client.get(url, params={"query": query, "dsoType": "item", "page": page, "size": size})
            resp.raise_for_status()
            result = (resp.json().get("_embedded") or {}).get("searchResult") or {}
            objects = (result.get("_embedded") or {}).get("objects") or []
            if not objects:
                break
            for obj in objects:
                item = (obj.get("_embedded") or {}).get("indexableObject") or {}
                handle = str(item.get("handle") or item.get("uuid") or len(records))
                records.append(
                    _dc_record(
                        _group_hal(item.get("metadata") or {}),
                        source_db=source_db,
                        native_id=handle,
                        url_fallback=f"{base}/handle/{handle}",
                    )
                )
            page += 1
            if page >= int((result.get("page") or {}).get("totalPages") or 1):
                break
    return records[:max_results]


agrosavia_search = partial(dspace7_search, base_url=AGROSAVIA_URL, source_db="AGROSAVIA")
clacso_search = partial(dspace7_search, base_url=CLACSO_URL, source_db="CLACSO")
worldbank_okr_search = partial(dspace7_search, base_url=WORLDBANK_OKR_URL, source_db="WorldBankOKR")


# ── DOAB (DSpace 6 · /rest/search) ────────────────────────────────────


def _group_flat(metadata: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for entry in metadata:
        key, value = entry.get("key"), entry.get("value")
        if key and value:
            grouped.setdefault(key, []).append(str(value))
    return grouped


def doab_search(query: str, max_results: int = 25, *, mailto: str | None = None) -> list[SearchRecord]:
    """Busca libros OA en DOAB (DSpace 6 REST; sin ``total``: pagina hasta página corta)."""
    limit = min(max_results, 100)
    records: list[SearchRecord] = []
    offset = 0
    with _client(mailto=mailto) as client:
        while len(records) < max_results:
            params = {"query": query, "expand": "metadata", "limit": limit, "offset": offset}
            resp = client.get(DOAB_URL, params=params)
            resp.raise_for_status()
            items = resp.json() or []
            if not items:
                break
            for item in items:
                handle = str(item.get("handle") or item.get("uuid") or len(records))
                records.append(
                    _dc_record(
                        _group_flat(item.get("metadata") or []),
                        source_db="DOAB",
                        native_id=handle,
                        url_fallback=f"https://directory.doabooks.org/handle/{handle}",
                        extra={"type": "book"},
                    )
                )
            offset += len(items)
            if len(items) < limit:
                break
    return records[:max_results]
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest tests/test_dspace.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add revisia/agents/dspace.py tests/test_dspace.py
git commit -m "feat(search): adaptador DSpace 7+ (AGROSAVIA, CLACSO, Banco Mundial OKR) y backend DOAB"
```

---

### Task 5: Registro de alias y `MANUAL_ONLY`

**Files:**
- Modify: `revisia/agents/search_backends.py:1-9` (docstring), `:176-196` (`BACKENDS`, `MANUAL_ONLY`)
- Test: `tests/test_search_multibase.py`

**Interfaces:**
- Produces: alias en `BACKENDS` según §5 del spec; `MANUAL_ONLY` ampliado.

- [ ] **Step 1: Tests que fallan** (añadir a `tests/test_search_multibase.py`)

```python
def test_backends_nuevos_registrados() -> None:
    backends = available_backends()
    for alias in ("eric", "doaj", "unesdoc", "bvs", "lilacs", "gim", "agrosavia", "clacso", "worldbank", "okr", "doab"):
        assert alias in backends, alias


def test_bvs_despacha_por_alias(monkeypatch) -> None:
    from revisia.agents import open_backends

    visto: dict = {}

    def fake(query, max_results=25, *, mailto=None, instance="portal", source_db="BVS"):
        visto.update(query=query, instance=instance)
        return []

    monkeypatch.setattr(open_backends, "bvs_search", fake)
    monkeypatch.setattr(search_backends, "BACKENDS", {**search_backends.BACKENDS, "lilacs": fake})
    search_database("LILACS", "diabetes", 5)
    assert visto == {"query": "diabetes", "instance": "portal"}


def test_redalyc_y_dialnet_sugieren_importacion_manual() -> None:
    for db in ("Redalyc", "Dialnet", "SciELO", "Google Scholar"):
        with pytest.raises(ValueError, match="importación manual"):
            search_database(db, "q", 5)
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest tests/test_search_multibase.py -q`
Expected: 3 failed (alias no registrados; `Redalyc` sin sugerencia)

- [ ] **Step 3: Implementar** (en `search_backends.py`)

Docstring nuevo:

```python
"""Backends de búsqueda multi-base · despacho por nombre de base de datos.

PRISMA exige exhaustividad en **varias** bases (§3). Este módulo registra, con
la misma firma ``search(query, max_results, *, mailto) -> list[SearchRecord]``:
OpenAlex, Crossref, Semantic Scholar, Europe PMC, PubMed/PMC (NCBI), y las
fuentes abiertas añadidas tras el triage de 2026-09 (``docs/fuentes-triage.md``):
ERIC, DOAJ, UNESDOC, BVS/LILACS, AGROSAVIA, CLACSO, Banco Mundial OKR y DOAB.
Las bases sin API abierta (Scopus, WoS, Redalyc, Dialnet, SciELO…) se incorporan
por **importación manual** (RIS/BibTeX), ver :mod:`revisia.ingest.manual_import`.
"""
```

Import y registro:

```python
from revisia.agents import _http, busqueda, dspace, ncbi, open_backends
```

```python
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
    # Fuentes abiertas por área (triage 2026-09 · docs/fuentes-triage.md).
    "eric": open_backends.eric_search,
    "doaj": open_backends.doaj_search,
    "unesdoc": open_backends.unesdoc_search,
    "unesco": open_backends.unesdoc_search,
    "bvs": open_backends.bvs_search,
    "lilacs": open_backends.bvs_search,
    "bvsalud": open_backends.bvs_search,
    "gim": open_backends.gim_search,
    "globalindexmedicus": open_backends.gim_search,
    "agrosavia": dspace.agrosavia_search,
    "clacso": dspace.clacso_search,
    "worldbank": dspace.worldbank_okr_search,
    "worldbankokr": dspace.worldbank_okr_search,
    "okr": dspace.worldbank_okr_search,
    "bancomundial": dspace.worldbank_okr_search,
    "doab": dspace.doab_search,
}

# Bases sin API abierta de búsqueda: se ingestan por importación manual (RIS/BibTeX).
# Redalyc/Dialnet/SciELO solo ofrecen cosecha OAI-PMH (sin texto libre); Google
# Scholar no tiene API; Mendeley/DynaMed/Lens exigen credenciales por usuario.
MANUAL_ONLY = {
    "scopus", "webofscience", "wos", "embase", "psycinfo",
    "redalyc", "dialnet", "scielo", "googlescholar", "scholar",
    "mendeley", "dynamed", "lens", "pedro",
}
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -q`
Expected: todo en verde (168 + 2 + 7 + 5 + 3 = 185)

- [ ] **Step 5: Commit**

```bash
git add revisia/agents/search_backends.py tests/test_search_multibase.py
git commit -m "feat(search): registro de alias de las fuentes abiertas nuevas + MANUAL_ONLY ampliado"
```

---

### Task 6: Degradación por base en el pipeline

**Files:**
- Modify: `revisia/orchestration/pipeline.py:98-125` (`_multi_database_search`), `:171-179` (llamada)
- Test: `tests/test_search_multibase.py`

**Interfaces:**
- Produces: `_multi_database_search(...) -> tuple[list[SearchRecord], list[dict[str, str]]]`; fichero `01_search/failures.json` en la corrida cuando hay fallos.

- [ ] **Step 1: Test que falla**

```python
def test_multi_database_degrada_si_una_base_falla(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from revisia.orchestration.pipeline import _multi_database_search
    from revisia.schemas.records import SearchRecord

    def fake_search_database(db, query, max_results, *, mailto=None):
        if db == "BVS":
            raise RuntimeError("503 Service Unavailable")
        return [SearchRecord(record_id=f"{db}:1", title="ok", source_db=db)]

    monkeypatch.setattr(search_backends, "search_database", fake_search_database)
    protocol = SimpleNamespace(databases=["OpenAlex", "BVS", "ERIC"])
    records, failures = _multi_database_search(protocol, tmp_path, "q", 5, None)
    assert [r.source_db for r in records] == ["OpenAlex", "ERIC"]
    assert failures == [{"db": "BVS", "error": "RuntimeError: 503 Service Unavailable"}]
```

Y actualizar el test existente `test_multi_database_usa_cadena_de_base_con_espacios` para desempaquetar: `_multi_database_search(...)` → sigue válido (ignora el retorno); no cambia.

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest tests/test_search_multibase.py -q -k degrada`
Expected: FAIL (`RuntimeError` propagado / `cannot unpack`)

- [ ] **Step 3: Implementar**

```python
def _multi_database_search(
    protocol: ReviewProtocol,
    protocol_dir: Path,
    question_text: str,
    max_results: int,
    mailto: str | None,
) -> tuple[list[SearchRecord], list[dict[str, str]]]:
    """Busca en cada base declarada (con su cadena) + importación manual.

    Por cada base de ``protocol.databases`` lee su cadena en
    ``search_strings/<base>.txt`` (cae a la pregunta) y despacha al backend; las
    bases sin backend programático (Scopus/WoS) se cubren con los archivos
    RIS/BibTeX de ``imported/``. Un backend que falle (red, 5xx, JSON inválido)
    **no aborta la corrida**: se anota en ``failures`` para que quede en disco
    (``01_search/failures.json``) y en PRISMA-S conste qué base no respondió.
    La deduplicación posterior une los solapes.
    """
    databases = protocol.databases or ["openalex"]
    records: list[SearchRecord] = []
    failures: list[dict[str, str]] = []
    for db in databases:
        string_file = protocol_dir / "search_strings" / f"{search_backends.db_key(db)}.txt"
        query = question_text
        if string_file.exists():
            query = string_file.read_text(encoding="utf-8").strip() or question_text
        try:
            records += search_backends.search_database(db, query, max_results, mailto=mailto)
        except ValueError:
            # Base sin backend (p. ej. Scopus): se incorpora vía imported/.
            continue
        except Exception as exc:  # noqa: BLE001 - degradar por base, nunca abortar la corrida
            failures.append({"db": db, "error": f"{type(exc).__name__}: {exc}"})
            continue
    records += import_directory(protocol_dir / "imported")
    return records, failures
```

En `run_pipeline`:

```python
    search_failures: list[dict[str, str]] = []
    if search_fn is not None:
        raw_records = search_fn(question_text, max_results)
    else:
        raw_records, search_failures = _multi_database_search(
            protocol, protocol_dir, question_text, max_results, mailto
        )
    if search_failures:
        run_ctx.write_json("01_search/failures.json", search_failures)
        for f in search_failures:
            print(f"⚠️  búsqueda · {f['db']} no respondió ({f['error']}); se continúa sin esa base")
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -q && uv run ruff check revisia tests`
Expected: 186 passed; ruff sin errores (si `BLE001` no está activo, quitar el `# noqa`).

- [ ] **Step 5: Commit**

```bash
git add revisia/orchestration/pipeline.py tests/test_search_multibase.py
git commit -m "feat(pipeline): degradación por base en la búsqueda multi-base (failures.json)"
```

---

### Task 7: Documentación, template y CHANGELOG

**Files:**
- Modify: `docs/fuentes-candidatas.md` (sección "Ya integradas", tabla LATAM, prioridad), `docs/integraciones.md` (tabla "Integradas"), `README.md` (línea de búsqueda multi-base), `AGENTS.md` (fila `busqueda`), `protocols/_TEMPLATE/protocol.yml` (comentario de `databases`), `CHANGELOG.md` (`[Unreleased]`)
- Create: `protocols/_TEMPLATE/search_strings/eric.txt`, `doaj.txt`, `bvs.txt`, `clacso.txt`

- [ ] **Step 1: `docs/integraciones.md`** — añadir a la tabla "Integradas", tras la fila BioC-PMC:

```markdown
| [ERIC](https://eric.ed.gov) | Búsqueda (educación) | API abierta (sin key) | Backend nativo (`agents/open_backends.py`); alias `eric`; cadena Lucene |
| [DOAJ](https://doaj.org) | Búsqueda (revistas OA) | API abierta (CC0; 2 req/s) | Backend nativo; alias `doaj` |
| [UNESDOC](https://unesdoc.unesco.org) vía [UNESCO DataHub](https://data.unesco.org) | Búsqueda (literatura gris institucional) | API abierta (Opendatasoft) | Backend nativo; alias `unesdoc`; snapshot del catálogo |
| [BVS / LILACS](https://bvsalud.org) | Búsqueda (salud LATAM, es/pt) | API abierta (iAHx, sin key) | Backend nativo; alias `bvs`/`lilacs` (portal regional), `gim` (Global Index Medicus) |
| [AGROSAVIA](https://repository.agrosavia.co) · [CLACSO](https://biblioteca-repositorio.clacso.edu.ar) · [Banco Mundial OKR](https://openknowledge.worldbank.org) | Búsqueda (repositorios DSpace 7+) | API abierta (REST HAL) | Adaptador genérico `agents/dspace.py`; alias `agrosavia`, `clacso`, `worldbank` |
| [DOAB](https://directory.doabooks.org) | Búsqueda (libros OA) | API abierta (DSpace 6 REST) | Backend nativo; alias `doab` |
```

Y bajo la nota de hoja de ruta, añadir: `> **Triage verificado (2026-09):** qué tiene API y qué no, fuente por fuente: [`fuentes-triage.md`](fuentes-triage.md).`

- [ ] **Step 2: `docs/fuentes-candidatas.md`** — "Ya integradas" pasa a:

```markdown
OpenAlex · Crossref · Semantic Scholar · **PubMed/PMC (NCBI)** · Europe PMC ·
**ERIC** · **DOAJ** · **UNESDOC** · **BVS/LILACS** · **AGROSAVIA / CLACSO / Banco
Mundial OKR (DSpace 7+)** · **DOAB** · Unpaywall (texto completo) · **BioC-PMC**
(texto completo estructurado) · import RIS/BibTeX. Ver
[`integraciones.md`](integraciones.md) y el triage fuente por fuente en
[`fuentes-triage.md`](fuentes-triage.md).
```

En la tabla "Generales": DOAJ → `🟢 *(ya integrada)*`. En la tabla LATAM: RedALyC → `🟡 (OAI-PMH solo cosecha; sin búsqueda por texto → import RIS)`; SciELO → `🟡 (ArticleMeta sin texto libre; buscador tras WAF)`; CLACSO → `🟢 *(ya integrada · DSpace 10)*`; Dialnet → `🟡 (OAI-PMH solo cosecha → import RIS)`; añadir fila `| [BVS / LILACS](https://bvsalud.org) | 🟢 *(ya integrada)* | Salud en español/portugués que no está en MEDLINE |`. En "Prioridad recomendada", reemplazar el ítem 5 por `5. **RedALyC + SciELO** — sus DOIs ya entran por OpenAlex/Crossref; la cosecha OAI (sin búsqueda por texto) queda como integración de índice local futura.`

- [ ] **Step 3: `README.md`** — en el diagrama/línea "búsqueda multi-base" y en la tabla de principios, donde diga `OpenAlex, Crossref, Semantic Scholar, PubMed/PMC vía NCBI, Europe PMC` añadir `+ ERIC, DOAJ, UNESDOC, BVS/LILACS, repositorios DSpace (AGROSAVIA, CLACSO, Banco Mundial) y DOAB, todos sin API key` y un enlace a `docs/fuentes-triage.md`. Actualizar el badge de tests a `186`.

- [ ] **Step 4: `AGENTS.md`** — fila `busqueda`: `Búsqueda multi-base (OpenAlex, Crossref, Semantic Scholar, PubMed/PMC vía NCBI, Europe PMC, ERIC, DOAJ, UNESDOC, BVS/LILACS, DSpace 7+ (AGROSAVIA/CLACSO/OKR), DOAB + import RIS/BibTeX)`.

- [ ] **Step 5: `protocols/_TEMPLATE/protocol.yml`** — ampliar el comentario de `databases` (los valores por defecto no cambian):

```yaml
# Bases opt-in por área (todas sin API key; ver docs/fuentes-triage.md):
#   ERIC (educación) · DOAJ (revistas OA) · UNESDOC (literatura gris UNESCO) ·
#   BVS o LILACS (salud LATAM, es/pt) · GIM (Global Index Medicus) ·
#   AGROSAVIA (agro CO) · CLACSO (sociales LATAM) · WorldBank (OKR, desarrollo) ·
#   DOAB (libros OA). Añádelas a la lista y crea search_strings/<alias>.txt.
# Redalyc / SciELO / Dialnet no ofrecen búsqueda por texto (solo cosecha OAI):
# exporta RIS desde su web a imported/. Google Scholar: sin API (ToS).
```

- [ ] **Step 6: cadenas de ejemplo** (`protocols/_TEMPLATE/search_strings/`)

`eric.txt`:
```
("systematic review" OR "meta-analysis") AND ("large language model" OR "artificial intelligence") AND publicationdateyear:[2020 TO 2026]
```
`doaj.txt`:
```
bibjson.title:("systematic review" OR "meta-analysis") AND bibjson.abstract:("artificial intelligence") AND bibjson.year:[2020 TO 2026]
```
`bvs.txt`:
```
(tw:("revisión sistemática" OR "systematic review")) AND (tw:("inteligencia artificial" OR "artificial intelligence")) AND year_cluster:[2020 TO 2026]
```
`clacso.txt`:
```
("revisión sistemática" OR "inteligencia artificial") AND dc.date.issued:[2020 TO 2026]
```

- [ ] **Step 7: `CHANGELOG.md`** — bajo `## [Unreleased]` → `### Added`, antes de la entrada de OpenAlex:

```markdown
- **Ocho backends de fuentes abiertas, sin API key** (triage verificado en vivo,
  `docs/fuentes-triage.md`): **ERIC** (educación), **DOAJ** (revistas OA),
  **UNESDOC** (UNESCO DataHub), **BVS/LILACS** (salud LATAM, es/pt; alias `gim`
  para Global Index Medicus), **AGROSAVIA**, **CLACSO** y **Banco Mundial OKR**
  vía un **adaptador DSpace 7+ genérico** (`agents/dspace.py`; otro repositorio =
  una línea) y **DOAB** (libros OA). Todos opt-in por área en `protocol.databases`.
- **Degradación por base en la búsqueda**: un backend que falle por red/5xx no
  aborta la corrida; el fallo queda en `01_search/failures.json` (PRISMA-S).
- Cliente HTTP compartido (`agents/_http.py`) con User-Agent identificado.

### Changed
- `MANUAL_ONLY` incluye Redalyc, Dialnet, SciELO, Google Scholar, Mendeley,
  DynaMed, Lens y PEDro: el despacho sugiere importación RIS/BibTeX.
- URL del ID Converter de PMC actualizada a `pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/`
  (la antigua responde 301). El PMC OA Web Service fue descontinuado en 2026;
  RevisIA no lo usaba.
```

- [ ] **Step 8: Verificar y commit**

Run: `uv run pytest -q && uv run ruff check revisia tests && uv run ruff format --check revisia tests`
Expected: 186 passed; sin errores.

```bash
git add docs/ README.md AGENTS.md CHANGELOG.md protocols/_TEMPLATE/
git commit -m "docs: fuentes abiertas nuevas en integraciones, hoja de ruta, README, template y CHANGELOG"
```

---

### Task 8: Verificación en vivo (smoke) y cierre

**Files:** ninguno (solo ejecución).

- [ ] **Step 1: smoke con red real** (una petición por backend, `max_results=2`):

```bash
uv run python -c "
from revisia.agents.search_backends import search_database
for db in ['eric','doaj','unesdoc','bvs','gim','agrosavia','clacso','worldbank','doab']:
    try:
        rs = search_database(db, 'systematic review', 2, mailto='mosquera.abg@gmail.com')
        print(f'{db:10s} ok  n={len(rs)}  ->', rs[0].record_id if rs else '-', '|', (rs[0].title[:50] if rs else ''))
    except Exception as e:
        print(f'{db:10s} FAIL', type(e).__name__, e)
"
```

Expected: nueve líneas `ok` con `n=2` (BVS/GIM pueden dar `n<2` si la cadena no casa; no es fallo). Anotar cualquier `FAIL` en el informe final.

- [ ] **Step 2: suite completa + lint** (`uv run pytest -q && uv run ruff check revisia tests`).

- [ ] **Step 3:** push de la rama y PR con el resumen del triage y los backends (skill `superpowers:finishing-a-development-branch`).
