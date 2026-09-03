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
    """Indirección local (los tests la parchean) sobre el cliente compartido."""
    return _http.make_client(timeout, mailto=mailto)


def _values(meta: dict[str, list[str]], *keys: str) -> list[str]:
    """Concatena los valores de los campos ``keys`` presentes en ``meta``."""
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
            params = {"query": query, "dsoType": "item", "page": page, "size": size}
            resp = client.get(url, params=params)
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


def doab_search(
    query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
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
