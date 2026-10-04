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


# Cabeceras `x-api-key` / `authorization`, en forma `clave: valor` o `'clave': 'valor'`
# (el repr de un dict de cabeceras). El valor suelto puede llevar esquema
# (`Bearer sk-…`): se tapa entero, no solo la palabra `Bearer`.
_SECRET_HEADER_RE = re.compile(
    r"(?i)((?:x-api-key|authorization)['\"]?\s*[:=]\s*)"
    # valor entre comillas, o suelto (con esquema opcional) hasta un separador
    r"(?:(?P<q>['\"])[^'\"\r\n]*(?P=q)"
    r"|['\"]?(?:(?:bearer|basic|digest|token)\s+)?[^\s'\",;}&]+)"
)
# El valor tras `Bearer ` (RFC 6750: b64token) donde aparezca, sin cabecera delante.
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+")
# Claves con forma de proveedor: `sk-ant-…`, `sk-proj-…`, `sk-or-v1-…`. Con ≥ 16
# caracteres tras `sk-` y sin alfanumérico delante, para no tocar prosa (`task-force-…`).
_PROVIDER_KEY_RE = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}")


def _redact_header(match: re.Match[str]) -> str:
    quote = match.group("q") or ""
    return f"{match.group(1)}{quote}<redacted>{quote}"


def redact_secrets(text: str) -> str:
    """Oculta credenciales/PII: parámetros de URL, cabeceras de auth y claves de proveedor.

    Los errores de ``httpx`` incluyen la URL completa con su query string
    (``api_key=…``, ``email=…``) y los de los SDK de LLM, la cabecera o la clave
    (``Authorization: Bearer …``, ``{'x-api-key': …}``, ``Incorrect API key
    provided: sk-…``). Antes de escribirlos en disco (``01_search/failures.json``,
    ``run.json``) o en consola se pasa por aquí para que ninguna key acabe en un
    artefacto que se comparte.
    """
    text = _SECRET_HEADER_RE.sub(_redact_header, text)
    text = _BEARER_RE.sub(r"\1<redacted>", text)
    text = _PROVIDER_KEY_RE.sub("<redacted>", text)
    return _SECRET_PARAM_RE.sub(r"\1<redacted>", text)


def strip_html(text: str | None) -> str | None:
    """Quita etiquetas HTML; ``None`` si no queda texto."""
    if not text:
        return None
    return _TAG_RE.sub("", text).strip() or None
