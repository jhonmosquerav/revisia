"""Tests del fetcher de texto completo (offline · sin red)."""

from __future__ import annotations

import sys
import types

import pytest

from revisia.agents.fulltext import fetch_fulltext, resolve_oa_url, strip_html
from revisia.schemas.records import SearchRecord


def test_strip_html_quita_etiquetas_y_scripts() -> None:
    html = (
        "<html><head><style>x{}</style></head>"
        "<body>Hola <b>mundo</b><script>1</script></body></html>"
    )
    assert strip_html(html) == "Hola mundo"


def test_resolve_oa_url_prioriza_extra() -> None:
    rec = SearchRecord(record_id="a", title="t", extra={"oa_url": "http://x/p.pdf"})
    assert resolve_oa_url(rec) == "http://x/p.pdf"
    rec2 = SearchRecord(
        record_id="b", title="t", extra={"fulltext_url": "http://y", "oa_url": "http://x"}
    )
    assert resolve_oa_url(rec2) == "http://y"


def test_resolve_oa_url_sin_fuente_es_none() -> None:
    rec = SearchRecord(record_id="c", title="t", doi="10.1/x")  # sin mailto → no Unpaywall
    assert resolve_oa_url(rec) is None


def test_fetch_fulltext_fallback_a_abstract_sin_red() -> None:
    rec = SearchRecord(record_id="d", title="t", abstract="resumen del estudio")
    ft = fetch_fulltext(rec)  # sin oa_url → no toca la red
    assert ft.available is False
    assert ft.text == "resumen del estudio"
    assert ft.reason == "sin_url_oa"


# ── Motivo del fallo (auditoría 2026-09-03, M11; spec 2026-10-04 §6) ────────


def _httpx_falso(*, error: Exception | None = None, body: bytes = b"", ctype: str = "text/html"):
    """Módulo ``httpx`` sustituto: un ``Client`` que responde o lanza, sin red."""

    class _Resp:
        headers = {"content-type": ctype}
        content = body

        def raise_for_status(self) -> None:
            if error is not None:
                raise error

    class _Client:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> bool:
            return False

        def get(self, _url: str) -> _Resp:
            return _Resp()

    modulo = types.ModuleType("httpx")
    modulo.Client = _Client  # type: ignore[attr-defined]
    return modulo


@pytest.mark.parametrize(
    ("caso", "esperado"),
    [
        ("sin_url", "sin_url_oa"),
        ("sin_httpx", "sin_httpx"),
        ("error_http", "error_http"),
        ("texto_vacio", "texto_vacio"),
    ],
)
def test_fetch_fulltext_registra_motivo(
    monkeypatch: pytest.MonkeyPatch, caso: str, esperado: str
) -> None:
    extra = {} if caso == "sin_url" else {"oa_url": "https://oa.example/p?api_key=SECRETO"}
    rec = SearchRecord(record_id="r", title="t", abstract="resumen", extra=extra)
    if caso == "sin_httpx":
        monkeypatch.setitem(sys.modules, "httpx", None)  # `import httpx` → ImportError
    elif caso == "error_http":
        error = RuntimeError("503 Service Unavailable para https://oa.example/p?api_key=SECRETO")
        monkeypatch.setitem(sys.modules, "httpx", _httpx_falso(error=error))
    elif caso == "texto_vacio":
        monkeypatch.setitem(sys.modules, "httpx", _httpx_falso(body=b"<html><body> </body></html>"))

    ft = fetch_fulltext(rec)

    assert ft.available is False
    assert ft.reason == esperado
    assert ft.detail
    assert "SECRETO" not in ft.detail  # el detalle va redactado
    assert ft.text == "resumen"  # compatibilidad: el abstract sigue en text


def test_fetch_fulltext_recuperado_sin_motivo(monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<html><body><p>Texto completo del estudio.</p></body></html>"
    monkeypatch.setitem(sys.modules, "httpx", _httpx_falso(body=html))
    rec = SearchRecord(record_id="r", title="t", extra={"oa_url": "https://oa.example/p"})
    ft = fetch_fulltext(rec)
    assert (ft.available, ft.reason, ft.detail) == (True, None, None)
    assert ft.text == "Texto completo del estudio."
