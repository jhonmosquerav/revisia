"""Tests del fetcher de texto completo (offline · sin red)."""

from __future__ import annotations

from prisma_loop.agents.fulltext import fetch_fulltext, resolve_oa_url, strip_html
from prisma_loop.schemas.records import SearchRecord


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
