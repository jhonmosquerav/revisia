"""Agente de búsqueda (⚙️ determinista) · backend OpenAlex.

OpenAlex es una base académica abierta y gratuita (sin API key). Cubre el
caso "cualquier investigador puede correr esto sin credenciales de pago".
Otros backends (Semantic Scholar, Crossref) se añaden en H3 con la misma
firma ``search(query, max_results) -> list[SearchRecord]``.

Detalle técnico: OpenAlex entrega el abstract como ``abstract_inverted_index``
(palabra → posiciones); aquí lo reconstruimos a texto plano.
"""

from __future__ import annotations

from typing import Any

from prisma_loop.schemas.records import SearchRecord

OPENALEX_WORKS_URL = "https://api.openalex.org/works"


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Reconstruye el abstract a partir del índice invertido de OpenAlex.

    Args:
        inverted_index: mapa palabra → lista de posiciones (0-based).

    Returns:
        El abstract como texto, o ``None`` si no hay índice.
    """
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        for idx in idxs:
            positions.append((idx, word))
    positions.sort(key=lambda pair: pair[0])
    return " ".join(word for _, word in positions) or None


def _normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.replace("https://doi.org/", "").lower().strip() or None


def work_to_record(work: dict[str, Any], source_db: str = "OpenAlex") -> SearchRecord:
    """Convierte un objeto ``work`` de OpenAlex en un SearchRecord.

    ``record_id`` prioriza el DOI normalizado (estable entre bases); si falta,
    cae al id de OpenAlex.
    """
    doi = _normalize_doi(work.get("doi"))
    openalex_id = (work.get("id") or "").rsplit("/", 1)[-1] or "unknown"
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in work.get("authorships", [])
        if a.get("author")
    ]
    oa = work.get("open_access") or {}
    best = work.get("best_oa_location") or {}
    oa_url = oa.get("oa_url") or best.get("pdf_url") or best.get("landing_page_url")
    return SearchRecord(
        record_id=doi or openalex_id,
        title=work.get("display_name") or work.get("title") or "(sin título)",
        abstract=reconstruct_abstract(work.get("abstract_inverted_index")),
        authors=[a for a in authors if a],
        year=work.get("publication_year"),
        doi=doi,
        url=work.get("id"),
        source_db=source_db,
        extra={"oa_url": oa_url} if oa_url else {},
    )


def search(query: str, max_results: int = 25, *, mailto: str | None = None) -> list[SearchRecord]:
    """Busca en OpenAlex y devuelve registros normalizados.

    Args:
        query: cadena de búsqueda (texto libre).
        max_results: tope de resultados (per-page de OpenAlex, máx 200).
        mailto: email para el "polite pool" de OpenAlex (recomendado).

    Raises:
        RuntimeError: si ``httpx`` no está instalado (extra ``search``).
    """
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RuntimeError(
            "El agente de búsqueda requiere httpx. Instala el extra: `uv sync --extra search`."
        ) from exc

    params: dict[str, Any] = {"search": query, "per-page": min(max_results, 200)}
    if mailto:
        params["mailto"] = mailto
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(OPENALEX_WORKS_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    works = data.get("results", [])[:max_results]
    return [work_to_record(w) for w in works]
