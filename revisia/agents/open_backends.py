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
    """Indirección local (los tests la parchean) sobre el cliente compartido."""
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


def eric_search(
    query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
    """Busca en ERIC (IES/US Dept. of Education): artículos EJ + documentos ED.

    Sintaxis Lucene en la cadena (``AND``, ``campo:valor``,
    ``publicationdateyear:[2020 TO 2024]``). Hasta 2 000 registros por petición.
    """
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


def doaj_search(
    query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
    """Busca artículos en DOAJ (API abierta, metadatos CC0; 100 por página, 2 req/s).

    Sintaxis Elasticsearch ``query_string`` en la cadena (``bibjson.year:2024``,
    ``bibjson.title:"…"``). La cadena va en la ruta, URL-codificada.
    """
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
            if len(records) >= int(data.get("total") or 0):
                break
            page += 1
    return records[:max_results]


# ── UNESDOC (UNESCO DataHub · Opendatasoft) ───────────────────────────


def _unesdoc_where(query: str) -> str:
    """Cadena simple → ``search("…")``; cadena ODSQL (contiene ``search(``) → tal cual."""
    if "search(" in query:
        return query
    escaped = query.replace("\\", "\\\\").replace('"', '\\"')
    return f'search("{escaped}")'


def unesdoc_search(
    query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
    """Busca en UNESDOC vía UNESCO DataHub (dataset ``doc001``; snapshot del catálogo).

    Literatura gris institucional (informes, documentos de programa) que no está
    en OpenAlex/Crossref. Sin DOI: ``record_id = unesdoc:<uuid>``.
    """
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
            if offset >= int(data.get("total_count") or 0):
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
    la cadena (``year_cluster:[2020 TO 2024]``), no como ``filter=`` (el servidor
    lo corrompe). Requiere User-Agent identificado (lo pone ``_http``).
    """
    count = min(max_results, 500)
    records: list[SearchRecord] = []
    offset = 0
    url = BVS_URL.format(instance=instance)
    with _client(mailto=mailto) as client:
        while len(records) < max_results:
            params = {
                "output": "json",
                "lang": "es",
                "q": query,
                "count": count,
                "from": offset + 1,
            }
            resp = client.get(url, params=params)
            resp.raise_for_status()
            dia = (resp.json().get("diaServerResponse") or [{}])[0]
            response = dia.get("response") or {}
            docs = response.get("docs") or []
            if not docs:
                break
            records.extend(_bvs_record(d, source_db) for d in docs)
            offset += len(docs)
            if offset >= int(response.get("numFound") or 0):
                break
    return records[:max_results]


gim_search = partial(bvs_search, instance="gim", source_db="GIM")
