"""Ruta Unpaywall → PDF/HTML de `fetch_fulltext` con la red simulada (auditoría 2026-09-03, M19)."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator

import httpx
import pytest
from fakes import pdf_minimo

from revisia.agents import ncbi
from revisia.agents.fulltext import fetch_fulltext
from revisia.schemas.records import SearchRecord

UNPAYWALL = "https://api.unpaywall.org/v2/"
PDF_URL = "https://repo.example/articulo.pdf"
HTML_URL = "https://repo.example/articulo.html"
SIN_PMCID = {
    "status": "ok",
    "records": [{"doi": "10.1000/xyz", "status": "error", "errmsg": "invalid article id"}],
}
_PASAJES = [{"text": "Introducción."}, {"text": "Métodos."}]
Manejador = Callable[[httpx.Request], httpx.Response]


def _urls(vistas: list[httpx.Request]) -> list[str]:
    return [str(r.url).split("?")[0] for r in vistas]


def _registro() -> SearchRecord:
    return SearchRecord(record_id="10.1000/xyz", title="t", abstract="resumen", doi="10.1000/xyz")


@pytest.fixture
def cliente_simulado(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[Manejador], list[httpx.Request]]]:
    """Instala un manejador para toda conexión httpx y devuelve la lista de peticiones vistas."""

    inesperadas: list[str] = []

    def instalar(manejador: Manejador) -> list[httpx.Request]:
        vistas: list[httpx.Request] = []
        real = httpx.Client

        def enrutado(request: httpx.Request) -> httpx.Response:
            vistas.append(request)
            try:
                return manejador(request)
            except AssertionError:
                # `fetch_fulltext` absorbe cualquier excepción como `error_http`: se anota la URL
                # y el assert final de la fixture hace fallar el test (no puede quedar en falso).
                inesperadas.append(str(request.url))
                raise

        monkeypatch.setattr(
            httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(enrutado), **kw)
        )
        # El ID Converter pasa por `ncbi._throttle` (0,34 s entre llamadas): sin esto cada test
        # duerme. `ncbi._sleep` es la indirección prevista para tests.
        monkeypatch.setattr(ncbi, "_sleep", lambda _s: None)
        return vistas

    yield instalar
    assert not inesperadas, f"peticiones no previstas: {inesperadas}"


def _manejador(unpaywall: httpx.Response, descarga: httpx.Response | None = None) -> Manejador:
    def manejador(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(ncbi.IDCONV_URL):
            return httpx.Response(200, json=SIN_PMCID)
        if url.startswith(UNPAYWALL):
            assert request.url.params.get("email") == "revisora@example.org"
            return unpaywall
        if descarga is not None and url in (PDF_URL, HTML_URL):
            return descarga
        raise AssertionError(f"URL no prevista por el test: {url}")

    return manejador


def test_pdf_minimo_es_legible_por_pypdf() -> None:
    pypdf = pytest.importorskip("pypdf")

    datos = pdf_minimo("Texto completo de prueba")
    assert datos.startswith(b"%PDF-1.4") and datos.rstrip().endswith(b"%%EOF")
    assert pypdf.PdfReader(io.BytesIO(datos)).pages[0].extract_text() == "Texto completo de prueba"
    with pytest.raises(ValueError):
        pdf_minimo("con (paréntesis)")


def test_pdf_minimo_xref_apunta_a_cada_objeto() -> None:
    """Estructura verificada a mano: pypdf reconstruiría un xref roto y no lo detectaría."""
    datos = pdf_minimo("Texto completo de prueba")
    inicio = int(datos[datos.rindex(b"startxref") :].split()[1])
    assert datos[inicio:].startswith(b"xref")
    lineas = datos[inicio:].split(b"\n")
    total = int(lineas[1].split()[1])
    entradas = lineas[3 : 2 + total]  # salta «xref», «0 N» y la entrada libre
    assert len(entradas) == total - 1
    for n, entrada in enumerate(entradas, 1):
        offset = int(entrada.split()[0])
        assert datos[offset:].startswith(f"{n} 0 obj".encode())


def test_unpaywall_url_for_pdf_descarga_y_extrae_el_pdf(cliente_simulado) -> None:
    pytest.importorskip("pypdf")
    vistas = cliente_simulado(
        _manejador(
            httpx.Response(
                200, json={"best_oa_location": {"url_for_pdf": PDF_URL, "url": HTML_URL}}
            ),
            httpx.Response(
                200,
                content=pdf_minimo("Texto completo de prueba"),
                headers={"content-type": "application/pdf"},
            ),
        )
    )
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert ft.available is True and ft.reason is None
    assert "Texto completo de prueba" in ft.text and ft.source_url == PDF_URL
    assert _urls(vistas) == [
        ncbi.IDCONV_URL,
        f"{UNPAYWALL}10.1000/xyz",
        PDF_URL,
    ]


def test_unpaywall_url_html_se_limpia(cliente_simulado) -> None:
    cliente_simulado(
        _manejador(
            httpx.Response(200, json={"best_oa_location": {"url": HTML_URL}}),
            httpx.Response(
                200,
                content=(
                    b"<html><script>x()</script><body><p>Texto <b>completo</b> en HTML.</p>"
                    b"</body></html>"
                ),
                headers={"content-type": "text/html; charset=utf-8"},
            ),
        )
    )
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert ft.available is True and ft.text == "Texto completo en HTML."
    assert ft.source_url == HTML_URL


def test_unpaywall_404_es_sin_url_oa(cliente_simulado) -> None:
    vistas = cliente_simulado(_manejador(httpx.Response(404)))
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert _urls(vistas) == [ncbi.IDCONV_URL, f"{UNPAYWALL}10.1000/xyz"]
    assert vistas[-1].url.params["email"] == "revisora@example.org"
    assert (ft.available, ft.reason) == (False, "sin_url_oa") and ft.text == "resumen"


def test_unpaywall_503_es_error_http_transitorio(cliente_simulado) -> None:
    vistas = cliente_simulado(_manejador(httpx.Response(503)))
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert _urls(vistas) == [ncbi.IDCONV_URL, f"{UNPAYWALL}10.1000/xyz"]
    assert vistas[-1].url.params["email"] == "revisora@example.org"
    assert (ft.available, ft.reason) == (False, "error_http") and "503" in (ft.detail or "")


def test_descarga_404_tras_unpaywall_es_error_http(cliente_simulado) -> None:
    vistas = cliente_simulado(
        _manejador(
            httpx.Response(200, json={"best_oa_location": {"url": HTML_URL}}),
            httpx.Response(404),
        )
    )
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert (ft.available, ft.reason) == (False, "error_http")
    assert _urls(vistas) == [ncbi.IDCONV_URL, f"{UNPAYWALL}10.1000/xyz", HTML_URL]
    assert vistas[1].url.params["email"] == "revisora@example.org"


@pytest.mark.parametrize(
    "pdf",
    [pdf_minimo(""), b"%PDF-1.4\n%%EOF\n"],
    ids=["valido_sin_texto", "corrupto"],
)
def test_pdf_sin_texto_extraible_es_texto_vacio(cliente_simulado, pdf: bytes) -> None:
    pytest.importorskip("pypdf")
    cliente_simulado(
        _manejador(
            httpx.Response(200, json={"best_oa_location": {"url_for_pdf": PDF_URL}}),
            httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"}),
        )
    )
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert (ft.available, ft.reason) == (False, "texto_vacio")


def test_pmcid_resuelto_por_idconv_usa_bioc_sin_unpaywall(cliente_simulado) -> None:
    def manejador(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(ncbi.IDCONV_URL):
            return httpx.Response(
                200, json={"status": "ok", "records": [{"doi": "10.1000/xyz", "pmcid": "PMC123"}]}
            )
        if url.startswith(ncbi.BIOC_URL.format(pmcid="PMC123")):
            return httpx.Response(
                200,
                json=[{"documents": [{"passages": _PASAJES}]}],
            )
        raise AssertionError(f"URL no prevista por el test: {url}")

    vistas = cliente_simulado(manejador)
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert ft.available is True and ft.text == "Introducción.\n\nMétodos."
    assert ft.source_url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/"
    assert len(vistas) == 2 and not any("unpaywall" in str(r.url) for r in vistas)


def test_el_recorte_a_max_chars_se_aplica_al_texto_descargado(cliente_simulado) -> None:
    cliente_simulado(
        _manejador(
            httpx.Response(200, json={"best_oa_location": {"url": HTML_URL}}),
            httpx.Response(
                200,
                content=b"<p>" + b"palabra " * 5_000 + b"</p>",
                headers={"content-type": "text/html"},
            ),
        )
    )
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org", max_chars=100)
    assert ft.available is True and len(ft.text) == 100


def test_sin_mailto_no_se_consulta_unpaywall(cliente_simulado) -> None:
    def ninguna(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"sin --mailto no debe salir ninguna petición: {request.url}")

    vistas = cliente_simulado(ninguna)
    ft = fetch_fulltext(_registro())
    assert (ft.available, ft.reason) == (False, "sin_url_oa") and vistas == []
