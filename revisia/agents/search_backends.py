"""Backends de búsqueda multi-base · despacho por nombre de base de datos.

PRISMA exige exhaustividad en **varias** bases (§3). Este módulo añade backends
abiertos y sin API key —Crossref y Semantic Scholar— junto al de OpenAlex, todos
con la misma firma ``search(query, max_results, *, mailto) -> list[SearchRecord]``.
Las bases de pago (Scopus, Web of Science) no tienen API abierta: sus resultados
se incorporan por **importación manual** (RIS/BibTeX), ver
:mod:`revisia.ingest.manual_import`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from revisia.agents import busqueda, ncbi
from revisia.schemas.records import SearchRecord

SearchFn = Callable[..., list[SearchRecord]]

CROSSREF_URL = "https://api.crossref.org/works"
S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
EUROPEPMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _client(timeout: float = 60.0) -> Any:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RuntimeError(
            "Los backends de búsqueda requieren httpx. Instala el extra: `uv sync --extra search`."
        ) from exc
    return httpx.Client(timeout=timeout, follow_redirects=True)


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    import re

    return re.sub(r"<[^>]+>", "", text).strip() or None


def crossref_search(
    query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
    """Busca en Crossref (abierto, sin API key)."""
    params: dict[str, Any] = {"query": query, "rows": min(max_results, 100)}
    if mailto:
        params["mailto"] = mailto
    with _client() as client:
        resp = client.get(CROSSREF_URL, params=params)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])[:max_results]
    records: list[SearchRecord] = []
    for it in items:
        doi = (it.get("DOI") or "").lower().strip() or None
        title_list = it.get("title") or []
        authors = [
            " ".join(p for p in [a.get("given"), a.get("family")] if p)
            for a in it.get("author", [])
        ]
        year = None
        parts = (it.get("issued") or {}).get("date-parts") or [[None]]
        if parts and parts[0]:
            year = parts[0][0]
        records.append(
            SearchRecord(
                record_id=doi or f"crossref:{it.get('DOI') or len(records)}",
                title=title_list[0] if title_list else "(sin título)",
                abstract=_strip_html(it.get("abstract")),
                authors=[a for a in authors if a],
                year=year,
                doi=doi,
                url=it.get("URL"),
                source_db="Crossref",
            )
        )
    return records


def semantic_scholar_search(
    query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
    """Busca en Semantic Scholar (abierto; key opcional para más cuota)."""
    fields = "title,abstract,year,externalIds,authors,url,openAccessPdf"
    params = {"query": query, "limit": min(max_results, 100), "fields": fields}
    with _client() as client:
        resp = client.get(S2_URL, params=params)
        resp.raise_for_status()
        data = resp.json().get("data", [])[:max_results]
    records: list[SearchRecord] = []
    for p in data:
        ext = p.get("externalIds") or {}
        doi = (ext.get("DOI") or "").lower().strip() or None
        oa = p.get("openAccessPdf") or {}
        records.append(
            SearchRecord(
                record_id=doi or f"s2:{p.get('paperId', len(records))}",
                title=p.get("title") or "(sin título)",
                abstract=p.get("abstract"),
                authors=[a.get("name", "") for a in p.get("authors", []) if a.get("name")],
                year=p.get("year"),
                doi=doi,
                url=p.get("url"),
                source_db="SemanticScholar",
                extra={"oa_url": oa.get("url")} if oa.get("url") else {},
            )
        )
    return records


def europepmc_search(
    query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
    """Busca en Europe PMC (abierto, sin API key).

    Europe PMC espeja MEDLINE/PubMed + PubMed Central + preprints, así que cubre
    el grueso de la literatura biomédica/metodológica sin la suscripción de una
    universidad. ``resultType=core`` incluye el abstract.
    """
    params: dict[str, Any] = {
        "query": query,
        "format": "json",
        "resultType": "core",
        "pageSize": min(max_results, 100),
    }
    if mailto:
        params["email"] = mailto
    with _client() as client:
        resp = client.get(EUROPEPMC_URL, params=params)
        resp.raise_for_status()
        results = (resp.json().get("resultList") or {}).get("result", [])[:max_results]
    records: list[SearchRecord] = []
    for it in results:
        doi = (it.get("doi") or "").lower().strip() or None
        epmc_id = f"{it.get('source', 'EPMC')}:{it.get('id') or len(records)}"
        year = None
        if it.get("pubYear"):
            try:
                year = int(it["pubYear"])
            except (TypeError, ValueError):
                year = None
        authors = [a.strip() for a in (it.get("authorString") or "").split(",") if a.strip()]
        records.append(
            SearchRecord(
                record_id=doi or f"europepmc:{epmc_id}",
                title=it.get("title") or "(sin título)",
                abstract=_strip_html(it.get("abstractText")),
                authors=authors,
                year=year,
                doi=doi,
                url=(f"https://doi.org/{doi}" if doi else None),
                source_db="EuropePMC",
            )
        )
    return records


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

# Bases sin API abierta: se ingestan por importación manual (RIS/BibTeX).
MANUAL_ONLY = {"scopus", "webofscience", "wos", "embase", "psycinfo"}


def available_backends() -> list[str]:
    """Nombres de base con backend programático."""
    return sorted(BACKENDS)


def search_database(
    db: str, query: str, max_results: int = 25, *, mailto: str | None = None
) -> list[SearchRecord]:
    """Busca en la base ``db`` (despacho case-insensitive).

    Raises:
        ValueError: si la base no tiene backend programático (puede requerir
            importación manual si está en :data:`MANUAL_ONLY`).
    """
    key = db.lower().replace(" ", "")
    fn = BACKENDS.get(key)
    if fn is None:
        hint = " (requiere importación manual RIS/BibTeX)" if key in MANUAL_ONLY else ""
        raise ValueError(
            f"Base sin backend programático: {db!r}{hint}. "
            f"Disponibles: {', '.join(available_backends())}."
        )
    return fn(query, max_results, mailto=mailto)
