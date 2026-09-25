"""Tests v0.5.0: exportador de documento único (HTML autocontenido / PDF).

No requieren red ni WeasyPrint: el HTML se ensambla offline y el camino PDF
se prueba simulando la ausencia del extra (mensaje accionable).
"""

from __future__ import annotations

import base64
import shutil
import sys
from pathlib import Path

import pytest

from revisia.cli import main
from revisia.exports.document import assemble_html, export_run

# PNG real de 1×1 px: verifica el embebido base64 sin depender de matplotlib.
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

_MANIFEST = """\
slug: demo-export
created_utc: '2026-07-06T08:07:49+00:00'
timestamp: 20260706-080747
engine: revisia 0.5.0
protocol:
  question:
    text: ¿Pregunta de prueba?
counts:
  identified: 120
  identified_by_source:
    OpenAlex: 40
  duplicates_removed: 0
  removed_automation: 0
  removed_other: 0
  screened: 120
  excluded_ta: 92
  excluded_ta_human: 0
  excluded_ta_ai: 92
  fulltext_assessed: 28
  fulltext_abstract_only: 10
  excluded_ft: 3
  ft_exclusion_reasons:
    Razón X: 3
  included: 25
"""

_DOCUMENTO = """\
# Título del artículo de prueba

**Autor:** Autora de Prueba
**Fecha:** 6 de julio de 2026

## Resumen

Texto con **negrita** y [un enlace](https://doi.org/10.1000/demo).

## Flujo de selección

```mermaid
flowchart TB
    A["Identificados (n = 120)"] --> B["Incluidos (n = 25)"]
```

## Resultados

| Modelo | Sensibilidad |
|---|---|
| Llama 3 | 0.938 |
"""

# prisma_flow.md real: mermaid + la tabla estática equivalente ya generada.
_PRISMA_FLOW = """\
```mermaid
flowchart TB
    A --> B
```

| Etapa | n |
|---|---|
| Identificados | 120 |
| Incluidos | 25 |
"""


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    run = tmp_path / "demo-export-20260706-080747"
    deliverable = run / "deliverable"
    assets = deliverable / "assets"
    assets.mkdir(parents=True)
    (run / "manifest.yml").write_text(_MANIFEST, encoding="utf-8")
    (deliverable / "documento.md").write_text(_DOCUMENTO, encoding="utf-8")
    (deliverable / "prisma_flow.md").write_text(_PRISMA_FLOW, encoding="utf-8")
    (deliverable / "meta_analisis.md").write_text(
        "# Meta-análisis cuantitativo\n\n- Estudios (k): **28**\n", encoding="utf-8"
    )
    (deliverable / "checklist_2020.md").write_text(
        "| Ítem | Estado |\n|---|---|\n| 1 | cubierto |\n", encoding="utf-8"
    )
    (deliverable / "referencias.bib").write_text(
        "@article{demo2026,\n  title = {Demo <con> & caracteres},\n}\n", encoding="utf-8"
    )
    (assets / "forest.png").write_bytes(_PNG_1PX)
    (assets / "funnel.png").write_bytes(_PNG_1PX)
    return run


def test_html_autocontenido_sin_recursos_externos(run_dir: Path) -> None:
    html = assemble_html(run_dir)
    # Todas las imágenes viajan dentro del archivo como data-URI…
    imgs = html.split("<img")[1:]
    assert imgs, "el HTML debe incluir las figuras embebidas"
    for chunk in imgs:
        src = chunk.split('src="', 1)[1].split('"', 1)[0]
        assert src.startswith("data:image/png;base64,")
    # …y no hay recursos externos ni locales: ni scripts, ni CSS remoto, ni file://
    assert "<script" not in html
    assert "<link" not in html
    assert 'src="http' not in html
    assert 'src="file' not in html
    assert "url(http" not in html


def test_mermaid_reemplazado_por_tabla_estatica(run_dir: Path) -> None:
    html = assemble_html(run_dir)
    assert "mermaid" not in html
    assert "flowchart TB" not in html
    # documento.md no traía tabla de flujo: se inyecta la del manifest
    # (render_flow_markdown), reconocible por sus cajas oficiales.
    assert "Cribados (T/A)" in html


def test_prisma_flow_conserva_su_tabla_sin_duplicarla(run_dir: Path) -> None:
    html = assemble_html(run_dir)
    # prisma_flow.md ya tenía tabla equivalente: el mermaid se elimina y la
    # tabla oficial inyectada aparece solo una vez (la de documento.md).
    assert html.count("Cribados (T/A)") == 1


def test_titulo_solo_en_la_portada(run_dir: Path) -> None:
    # documento.md abre con su propio H1; la portada ya lo muestra, así que
    # el cuerpo del artículo no debe repetirlo.
    html = assemble_html(run_dir)
    assert html.count("<h1") == 1


def test_portada_con_titulo_autor_y_fecha(run_dir: Path) -> None:
    html = assemble_html(run_dir)
    assert "<title>Título del artículo de prueba</title>" in html
    assert "Autora de Prueba" in html
    assert "6 de julio de 2026" in html
    assert "demo-export" in html  # slug de la corrida en la portada


def test_figuras_meta_analisis_con_caption(run_dir: Path) -> None:
    html = assemble_html(run_dir)
    assert html.count("<figure") >= 2
    assert "<figcaption" in html
    assert "Forest" in html
    assert "Funnel" in html


def test_bibtex_incluido_y_escapado(run_dir: Path) -> None:
    html = assemble_html(run_dir)
    assert "demo2026" in html
    assert "&lt;con&gt;" in html  # el .bib va escapado dentro de <pre>


def test_export_run_escribe_html_por_defecto(run_dir: Path) -> None:
    out = export_run(run_dir)
    assert out.exists()
    assert out.suffix == ".html"
    assert out.parent == run_dir / "deliverable"
    assert "demo-export" in out.name


def test_export_run_formato_desconocido(run_dir: Path) -> None:
    with pytest.raises(ValueError, match="html"):
        export_run(run_dir, fmt="docx")


def test_export_run_sin_deliverable(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        export_run(tmp_path)


def test_pdf_sin_weasyprint_error_accionable(
    run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # None en sys.modules fuerza ImportError aunque el extra esté instalado.
    monkeypatch.setitem(sys.modules, "weasyprint", None)
    with pytest.raises(RuntimeError, match="uv sync --extra pdf"):
        export_run(run_dir, fmt="pdf")


def test_cli_export_html(run_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    destino = tmp_path / "articulo.html"
    assert main(["export", str(run_dir), "--out", str(destino)]) == 0
    assert destino.exists()
    assert "Exportado" in capsys.readouterr().out


def test_cli_export_run_dir_inexistente(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["export", str(tmp_path / "no-existe")]) == 2
    assert "no existe" in capsys.readouterr().err


def test_cli_export_pdf_sin_weasyprint(
    run_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setitem(sys.modules, "weasyprint", None)
    assert main(["export", str(run_dir), "--format", "pdf"]) == 2
    err = capsys.readouterr().err
    assert "uv sync --extra pdf" in err
    assert "--format html" in err


_REAL_RUN = Path("runs/prisma-ia-origen-20260706-080747")


@pytest.mark.skipif(not _REAL_RUN.exists(), reason="corrida real no disponible")
def test_export_corrida_real(tmp_path: Path) -> None:
    out = export_run(_REAL_RUN, out=tmp_path / "real.html")
    html = out.read_text(encoding="utf-8")
    assert "mermaid" not in html
    assert html.count("data:image/png;base64,") >= 2
    assert "Inteligencia artificial en la metodología PRISMA" in html


# ── Ola 0 · A-3/A-4/A-5 (auditoría 2026-09-03, A2 y M1) ─────────────────────


def _append_documento(run_dir: Path, extra: str) -> None:
    doc = run_dir / "deliverable" / "documento.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\n" + extra + "\n", encoding="utf-8")


def test_embed_images_rejects_traversal(run_dir: Path) -> None:
    # Reproducción literal de la auditoría: un secreto fuera de deliverable/.
    (run_dir / ".env").write_text("TOP_SECRET=abc123", encoding="utf-8")
    _append_documento(run_dir, "![fuga](../.env)")
    html = assemble_html(run_dir)
    assert "TOP_SECRET" not in html
    assert base64.b64encode(b"TOP_SECRET=abc123").decode() not in html
    assert "<em>fuga</em>" in html  # se degrada a su texto alternativo


def test_embed_images_rejects_image_outside_deliverable(run_dir: Path) -> None:
    (run_dir / "fuera.png").write_bytes(_PNG_1PX)
    _append_documento(run_dir, "![fuera](../fuera.png)")
    html = assemble_html(run_dir)
    assert 'alt="fuera"' not in html
    assert "<em>fuera</em>" in html


def test_embed_images_solo_extensiones_de_imagen(run_dir: Path) -> None:
    _append_documento(run_dir, "![anexo](referencias.bib)")
    html = assemble_html(run_dir)
    assert "data:application/octet-stream" not in html
    assert "<em>anexo</em>" in html


_MALICIOSO = """
<script>alert('xss')</script>

<img src=x onerror="alert(1)">

<img src="http://evil.example/pixel.png">

<a href="javascript:alert(1)">js</a> <a href="https://doi.org/10.1000/ok">ok</a>

<table><tr><td style="background:url(http://evil.example/x);text-align:center">z</td></tr></table>
"""


def test_export_html_strips_script_and_handlers(run_dir: Path) -> None:
    _append_documento(run_dir, _MALICIOSO)
    html = assemble_html(run_dir)
    assert "<script" not in html
    assert "alert(" not in html
    assert "onerror" not in html
    assert "evil.example" not in html
    assert "javascript:" not in html
    # Lo legítimo sobrevive: enlaces https, alineación de tablas y figuras data:.
    assert 'href="https://doi.org/10.1000/ok"' in html
    assert "text-align:center" in html
    assert 'src="data:image/png;base64,' in html


def test_anexos_tambien_se_sanean(run_dir: Path) -> None:
    (run_dir / "deliverable" / "meta_analisis.md").write_text(
        "# Meta-análisis\n\n<script>alert(2)</script>\n", encoding="utf-8"
    )
    assert "<script" not in assemble_html(run_dir)


def test_pdf_url_fetcher_rejects_non_data(
    run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    seen: dict = {}

    class _Fetcher:
        def __init__(self, **kwargs) -> None:
            seen["fetcher_kwargs"] = kwargs

    class _HTML:
        def __init__(self, **kwargs) -> None:
            seen["html_kwargs"] = kwargs

        def write_pdf(self, target: str) -> None:
            Path(target).write_bytes(b"%PDF-fake")

    fake = types.ModuleType("weasyprint")
    fake.HTML = _HTML  # type: ignore[attr-defined]
    fake.URLFetcher = _Fetcher  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "weasyprint", fake)

    out = export_run(run_dir, fmt="pdf", out=tmp_path / "x.pdf")
    assert out.read_bytes() == b"%PDF-fake"
    # Solo data: (las figuras ya viajan embebidas): ni file:// ni http(s)://.
    assert seen["fetcher_kwargs"] == {"allowed_protocols": {"data"}}
    assert isinstance(seen["html_kwargs"]["url_fetcher"], _Fetcher)


def test_url_fetcher_real_rechaza_file_y_http() -> None:
    # El test anterior mockea `weasyprint.URLFetcher`: verifica que el
    # exportador LO CONSTRUYE con `allowed_protocols={"data"}`, pero no que
    # ese contrato realmente bloquee file/http en el WeasyPrint real. Este
    # test lo hace contra el paquete real; se salta si no está instalado (no
    # forma parte de las deps de este entorno, ni se instala aquí) pero debe
    # ser correcto donde sí lo esté (extra `pdf`, WeasyPrint ≥70; revisión
    # final Ola 0, 2026-09).
    weasyprint = pytest.importorskip("weasyprint")
    fetcher = weasyprint.URLFetcher(allowed_protocols={"data"})
    with pytest.raises(ValueError, match="disallowed protocol"):
        fetcher.fetch("file:///x")
    with pytest.raises(ValueError, match="disallowed protocol"):
        fetcher.fetch("http://example.invalid/x")


# ── Ola 0 · fix de revisión de Tarea 2 (auditoría 2026-09-03) ──────────────


@pytest.mark.parametrize(
    "ref",
    [
        "//host/share/x.png",
        "\\\\host\\share\\x.png",
        "C:/Windows/win.ini",
        "/etc/passwd.png",
    ],
    ids=["barra-doble-unc", "backslash-unc", "unidad-absoluta", "posix-absoluta"],
)
def test_embed_images_rechaza_rutas_absolutas_y_unc_sin_resolver(
    run_dir: Path, monkeypatch: pytest.MonkeyPatch, ref: str
) -> None:
    # Con la ruta sin ancla vetada de antemano, ``Path.resolve`` nunca debe
    # construirse a partir de la referencia peligrosa: en Windows resolver una
    # UNC abre una conexión SMB al host que elija el Markdown (auditoría
    # 2026-09-03). El espía NO aborta por subcadenas genéricas ("host",
    # "windows", "etc") porque colisionan con la ruta temporal real (p. ej.
    # `TEMP` puede vivir bajo `C:\Windows\Temp`, o el usuario del sistema
    # llamarse "etc" y aparecer en el `tmp_path` de pytest); en vez de eso se
    # registran TODAS las rutas resueltas y se comprueba, ya fuera del espía,
    # que ninguna contiene la referencia peligrosa completa normalizada
    # (revisión final Ola 0, 2026-09).
    original_resolve = Path.resolve
    resueltas: list[str] = []

    def _spy(self: Path, *args: object, **kwargs: object) -> Path:
        resueltas.append(str(self))
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", _spy)
    _append_documento(run_dir, f"![x]({ref})")
    html = assemble_html(run_dir)
    assert "<em>x</em>" in html
    peligrosa = ref.replace("\\", "/").lower().lstrip("/")
    tocadas = [r for r in resueltas if peligrosa in r.replace("\\", "/").lower()]
    assert not tocadas, f"Path.resolve() tocó una ruta no confinada: {tocadas!r}"


def test_figuras_meta_no_sigue_symlinks_fuera(run_dir: Path) -> None:
    fuera = run_dir.parent / "secreto-fuera-symlink.png"
    contenido_fuera = b"contenido-secreto-fuera-del-deliverable"
    fuera.write_bytes(contenido_fuera)
    forest = run_dir / "deliverable" / "assets" / "forest.png"
    forest.unlink()
    try:
        forest.symlink_to(fuera)
    except (OSError, NotImplementedError):
        # Sin privilegio para symlinks (Windows sin modo desarrollador ni
        # admin: caso típico de CI/dev). En vez de saltar el test entero, se
        # prueba la misma protección con una *junction* de directorio, que no
        # requiere privilegio especial: `deliverable/assets` pasa a ser una
        # junction hacia una carpeta externa con su propio `forest.png` de
        # bytes distinguibles (revisión final Ola 0, 2026-09).
        try:
            import _winapi

            assets = run_dir / "deliverable" / "assets"
            fuera_dir = run_dir.parent / "assets-fuera-junction"
            fuera_dir.mkdir()
            (fuera_dir / "forest.png").write_bytes(contenido_fuera)
            shutil.rmtree(assets)
            _winapi.CreateJunction(str(fuera_dir), str(assets))
        except (OSError, AttributeError, ImportError, NotImplementedError):
            pytest.skip("sin privilegio para symlinks ni soporte de junctions")
    html = assemble_html(run_dir)
    assert base64.b64encode(contenido_fuera).decode() not in html


def test_style_solo_text_align_con_valor_valido(run_dir: Path) -> None:
    _append_documento(
        run_dir,
        "\n<table><tr>"
        '<td style="text-align:url(http://evil.example/x)">a</td>'
        '<td style="TEXT-ALIGN: Center; color:red">b</td>'
        "</tr></table>\n",
    )
    html = assemble_html(run_dir)
    assert "evil.example" not in html
    assert "text-align:center" in html
    assert "color:red" not in html


def test_href_data_y_javascript_variantes(run_dir: Path) -> None:
    _append_documento(
        run_dir,
        "\n"
        '<a href="DATA:text/html,x">d</a> '
        '<a href="  JaVaScRiPt:alert(1)">j</a> '
        '<a href="java&#x09;script:alert(1)">e</a>\n',
    )
    low = assemble_html(run_dir).lower()
    assert "data:text" not in low
    assert "alert(" not in low
    assert "javascript" not in low


def test_href_protocolo_relativo_y_unc_rechazados(run_dir: Path) -> None:
    # `//host/...` (protocol-relative) y `\\host\...` (UNC): abierto el HTML
    # desde file://, un clic resuelve contra el host que elija el documento
    # (revisión final Ola 0, 2026-09).
    _append_documento(
        run_dir,
        '\n<a href="//evil.example/x">a</a> <a href="\\\\evil.example\\share\\x">b</a>\n',
    )
    html = assemble_html(run_dir)
    assert "evil" not in html
