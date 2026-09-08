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


_SECRET_PARAM_RE = re.compile(
    r"(?i)((?:api_key|apikey|key|token|access_token|mailto|email)=)[^&\s'\"]+"
)


def redact_secrets(text: str) -> str:
    """Oculta valores de credenciales/PII en parámetros de URL (``api_key=…``, ``email=…``).

    Los errores de ``httpx`` incluyen la URL completa con su query string; antes
    de escribirlos en disco (``01_search/failures.json``) o en consola se pasa
    por aquí para que ninguna key acabe en un artefacto que se comparte.
    """
    return _SECRET_PARAM_RE.sub(r"\1<redacted>", text)


def strip_html(text: str | None) -> str | None:
    """Quita etiquetas HTML; ``None`` si no queda texto."""
    if not text:
        return None
    return _TAG_RE.sub("", text).strip() or None
