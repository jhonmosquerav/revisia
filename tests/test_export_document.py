"""Tests v0.5.0: exportador de documento único (HTML autocontenido / PDF).

No requieren red ni WeasyPrint: el HTML se ensambla offline y el camino PDF
se prueba simulando la ausencia del extra (mensaje accionable).
"""

from __future__ import annotations

import base64
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
