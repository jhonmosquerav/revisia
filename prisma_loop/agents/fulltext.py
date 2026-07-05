"""Adquisición de texto completo (⚙️ determinista · solo Open Access).

Resuelve y descarga el texto completo de un estudio cuando está en abierto
(OpenAlex OA / Unpaywall / URL declarada en ``record.extra``). Si no hay OA
accesible, cae al abstract y marca ``available=False`` — honesto: en v1 el
texto completo tras paywall queda fuera (decisión de diseño; la ingesta
manual de PDFs llegará después).

Dependencias opcionales: ``httpx`` (extra ``search``) para descargar y
``pypdf`` para extraer PDFs. Sin ellas, cae al abstract sin romper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from prisma_loop.schemas.records import SearchRecord

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


@dataclass(slots=True)
class FullText:
    """Resultado de la adquisición de texto completo."""

    text: str
    available: bool
    source_url: str | None = None


def strip_html(html: str) -> str:
    """Convierte HTML a texto plano (quita scripts/estilos/etiquetas)."""
    no_scripts = _SCRIPT_RE.sub(" ", html)
    no_tags = _TAG_RE.sub(" ", no_scripts)
    return _WS_RE.sub(" ", no_tags).strip()


def resolve_oa_url(record: SearchRecord, *, mailto: str | None = None) -> str | None:
    """Devuelve la mejor URL de texto completo OA, o ``None``.

    Prioridad: ``extra.fulltext_url`` > ``extra.oa_url`` > consulta a Unpaywall
    por DOI (requiere ``httpx`` y un email).
    """
    for key in ("fulltext_url", "oa_url"):
        url = record.extra.get(key)
        if url:
            return str(url)
    if record.doi and mailto:
        return _unpaywall_url(record.doi, mailto)
    return None


def _unpaywall_url(doi: str, mailto: str) -> str | None:
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return None
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(f"https://api.unpaywall.org/v2/{doi}", params={"email": mailto})
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # red caída, 404, etc. → sin OA
        return None
    loc = data.get("best_oa_location") or {}
    return loc.get("url_for_pdf") or loc.get("url")


def _extract_pdf(content: bytes) -> str | None:
    try:
        import io

        import pypdf
    except ImportError:  # pragma: no cover - pypdf es opcional
        return None
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return None


def fetch_fulltext(
    record: SearchRecord, *, mailto: str | None = None, max_chars: int = 20000
) -> FullText:
    """Descarga el texto completo OA de un estudio, con fallback al abstract."""
    fallback = FullText(text=record.abstract or "", available=False)
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
