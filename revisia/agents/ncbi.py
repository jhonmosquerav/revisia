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

from revisia.agents import _http
from revisia.schemas.records import SearchRecord

EUTILS ="https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS}/esearch.fcgi"
EFETCH_URL = f"{EUTILS}/efetch.fcgi"
ESUMMARY_URL = f"{EUTILS}/esummary.fcgi"
IDCONV_URL = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
BIOC_URL = (
    "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/" "pmcoa.cgi/BioC_json/{pmcid}/unicode"
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
    """Indirección local (los tests la parchean) sobre el cliente compartido."""
    return _http.make_client(timeout)


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
