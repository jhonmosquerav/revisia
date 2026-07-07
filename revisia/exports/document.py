"""Exportador del entregable a un documento único y portable (HTML / PDF).

``revisia export <run_dir>`` ensambla todo el ``deliverable/`` de una corrida
en UN solo archivo:

- **HTML autocontenido** (formato por defecto · cero dependencias del sistema):
  portada con los metadatos del ``manifest.yml``, el artículo (``documento.md``)
  y los anexos (flujo PRISMA, metaanálisis con figuras, metodología, checklists,
  tabla de extracción, riesgo de sesgo y bibliografía). Las figuras van
  **embebidas como data-URI** y los bloques Mermaid se sustituyen por la tabla
  estática oficial (:func:`revisia.exports.prisma_flow.render_flow_markdown`):
  el archivo se abre igual en cualquier carpeta o máquina, sin red y sin
  JavaScript.
- **PDF** (extra opcional ``pdf``): el mismo HTML renderizado con WeasyPrint —
  multiplataforma y 100% Python; sin Word/COM, sin LaTeX, sin pandoc, sin
  Chromium. Si el extra no está instalado, el error explica cómo instalarlo o
  cómo obtener el PDF desde el navegador.

La conversión Markdown→HTML usa la librería ``markdown`` (pura-Python, sin
dependencias transitivas), declarada en el núcleo para que el formato por
defecto funcione siempre.
"""

from __future__ import annotations

import base64
import html
import re
from datetime import datetime
from pathlib import Path

import markdown as md_lib
import yaml
from pydantic import ValidationError

from revisia.exports.prisma_flow import PrismaCounts, render_flow_markdown

_MERMAID_RE = re.compile(r"```mermaid\r?\n.*?```[ \t]*\r?\n?", re.DOTALL)
_IMG_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6}) ", re.MULTILINE)
# Marca de la tabla estática del flujo: si el documento ya la trae, el bloque
# Mermaid se elimina en vez de duplicarla.
_FLOW_TABLE_MARKER = "| Etapa | n |"

_MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}

# Anexos del deliverable, en orden de ensamblado; los ausentes se omiten.
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("prisma_flow.md", "Anexo A · Flujo de selección PRISMA 2020"),
    ("prisma_flow_updated.md", "Anexo A.1 · Flujo de actualización (living review)"),
    ("meta_analisis.md", "Anexo B · Metaanálisis"),
    ("metodologia.md", "Anexo C · Metodología detallada"),
    ("checklist_2020.md", "Anexo D · Checklist PRISMA 2020"),
    ("checklist_s.md", "Anexo E · Checklist PRISMA-S"),
    ("checklist_abstracts.md", "Anexo F · Checklist PRISMA para resúmenes"),
    ("checklist_traice.md", "Anexo G · Checklist PRISMA-trAIce"),
    ("tabla_extraccion.md", "Anexo H · Tabla de extracción"),
    ("risk_of_bias.md", "Anexo I · Riesgo de sesgo"),
)

_FIGURAS_META: tuple[tuple[str, str], ...] = (
    ("forest.png", "Forest plot del metaanálisis (efecto por estudio y combinado)."),
    ("funnel.png", "Funnel plot (asimetría / sesgo de publicación)."),
)

_PDF_HINT = (
    "El formato pdf requiere WeasyPrint (extra opcional): instálalo con "
    "`uv sync --extra pdf` (o `pip install 'revisia[pdf]'`). WeasyPrint usa "
    "Pango: presente en Linux; en macOS `brew install pango`; en Windows el "
    "runtime GTK3 o MSYS2. Alternativa sin instalar nada: exporta con "
    "`--format html` y desde el navegador imprime a PDF."
)

# CSS académico inline: serif, ancho de lectura, tablas con borde, figuras
# centradas con caption, portada y saltos de página para imprimir/WeasyPrint.
_CSS = """
body { font-family: Georgia, 'Times New Roman', 'Liberation Serif', serif;
  color: #1c1c1c; background: #ffffff; line-height: 1.65;
  max-width: 52rem; margin: 0 auto; padding: 2.5rem 1.5rem; }
h1, h2, h3, h4 { line-height: 1.25; margin: 1.6em 0 0.6em; }
h1 { font-size: 1.9rem; }
h2 { font-size: 1.45rem; border-bottom: 1px solid #ddd; padding-bottom: 0.25rem; }
h3 { font-size: 1.15rem; }
h4 { font-size: 1rem; }
p { margin: 0.8em 0; text-align: justify; hyphens: auto; }
a { color: #17457a; text-decoration: none; }
a:hover { text-decoration: underline; }
table { border-collapse: collapse; width: 100%; margin: 1.2em 0; font-size: 0.92rem; }
th, td { border: 1px solid #b9b9b9; padding: 0.35em 0.6em; text-align: left;
  vertical-align: top; }
th { background: #f2f1ec; }
tr:nth-child(even) td { background: #fafaf7; }
figure { margin: 2em auto; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; height: auto; }
figcaption { font-size: 0.88rem; color: #555; font-style: italic; margin-top: 0.6em; }
blockquote { margin: 1.2em 0; padding: 0.4em 1.1em; border-left: 4px solid #9a9a9a;
  background: #f7f6f2; color: #333; }
code { font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 0.88em;
  background: #f2f1ec; padding: 0.08em 0.3em; border-radius: 2px; }
pre { background: #f7f6f2; border: 1px solid #ddd; padding: 1em; overflow-x: auto;
  font-size: 0.82rem; line-height: 1.45; }
pre code { background: none; padding: 0; }
hr { border: none; border-top: 1px solid #ccc; margin: 2.2em 0; }
.portada { text-align: center; padding: 5rem 0 3rem; page-break-after: always; }
.portada .tipo { text-transform: uppercase; letter-spacing: 0.18em; font-size: 0.8rem;
  color: #666; }
.portada h1 { font-size: 2rem; margin: 1.2em 0 0.8em; }
.portada .autor { font-size: 1.1rem; margin-top: 1.5em; }
.portada .fecha { color: #555; }
.portada .pregunta { font-style: italic; color: #444; margin: 2.2em auto 0;
  max-width: 40rem; }
.portada .sello { margin-top: 3.5rem; font-size: 0.85rem; color: #777; }
section.anexo { page-break-before: always; margin-top: 3rem; }
@page { size: A4; margin: 22mm 18mm; }
@media print { body { max-width: none; padding: 0; } a { color: inherit; } }
"""


def _load_manifest(run_dir: Path) -> dict:
    path = run_dir / "manifest.yml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _flow_table(manifest: dict) -> str | None:
    """Tabla estática del flujo PRISMA a partir de los conteos del manifest."""
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        return None
    try:
        return render_flow_markdown(PrismaCounts(**counts))
    except (TypeError, ValidationError):
        return None


def replace_mermaid_blocks(text: str, flow_table: str | None) -> str:
    """Sustituye los bloques ```mermaid``` por una representación estática.

    Reglas (deterministas): si el documento ya contiene la tabla estática del
    flujo (la emite el motor junto al Mermaid en ``prisma_flow.md``), los
    bloques simplemente se eliminan; si no, el primero se reemplaza por la
    tabla derivada del manifest y el resto se elimina.
    """
    if _FLOW_TABLE_MARKER in text:
        replacement = ""
    elif flow_table:
        replacement = flow_table + "\n"
    else:
        replacement = "*(Diagrama de flujo disponible en `prisma_flow.md` de la corrida.)*\n"
    first = True

    def _sub(_match: re.Match[str]) -> str:
        nonlocal first
        if first:
            first = False
            return replacement
        return ""

    return _MERMAID_RE.sub(_sub, text)


def _data_uri(path: Path) -> str:
    mime = _MIME.get(path.suffix.lower(), "application/octet-stream")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _figure_html(path: Path, caption: str) -> str:
    fig = f'<figure><img src="{_data_uri(path)}" alt="{html.escape(caption)}" />'
    if caption:
        fig += f"<figcaption>{html.escape(caption)}</figcaption>"
    return fig + "</figure>"


def _embed_md_images(text: str, base_dir: Path) -> str:
    """Reescribe ``![alt](ruta)`` a ``<figure>`` con la imagen embebida.

    Las referencias externas (http/https) o rotas se degradan a su texto
    alternativo en cursiva: el HTML resultante nunca carga recursos de fuera.
    """

    def _sub(match: re.Match[str]) -> str:
        alt, ref = match.group(1), match.group(2)
        if not ref.startswith(("http://", "https://", "data:", "file:")):
            target = base_dir / ref
            if target.is_file():
                return _figure_html(target, alt)
        return f"*{alt}*" if alt else ""

    return _IMG_MD_RE.sub(_sub, text)


def _demote_headings(text: str, levels: int = 2) -> str:
    """Baja los encabezados ATX ``levels`` niveles (los anexos cuelgan de un h2)."""

    def _sub(match: re.Match[str]) -> str:
        return "#" * min(6, len(match.group(1)) + levels) + " "

    return _HEADING_RE.sub(_sub, text)


def _md_to_html(text: str) -> str:
    return md_lib.markdown(text, extensions=["tables", "fenced_code"])


def _titulo(doc_md: str | None, manifest: dict, run_dir: Path) -> str:
    if doc_md:
        match = re.search(r"^# (.+)$", doc_md, re.MULTILINE)
        if match:
            return re.sub(r"[*`]", "", match.group(1)).strip()
    question = manifest.get("protocol", {}).get("question", {})
    if isinstance(question, dict) and question.get("text"):
        return str(question["text"]).strip()
    return str(manifest.get("slug") or run_dir.name)


def _autor(doc_md: str | None) -> str:
    if not doc_md:
        return ""
    match = re.search(r"^\*\*Autor:\*\*\s*(.+)$", doc_md, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _fecha_legible(manifest: dict) -> str:
    created = manifest.get("created_utc")
    if not created:
        return ""
    try:
        fecha = datetime.fromisoformat(str(created))
    except ValueError:
        return str(created)
    return f"{fecha.day} de {_MESES[fecha.month - 1]} de {fecha.year}"


def _portada(titulo: str, autor: str, fecha: str, manifest: dict) -> str:
    question = manifest.get("protocol", {}).get("question", {})
    pregunta = question.get("text", "") if isinstance(question, dict) else ""
    corrida = "-".join(str(p) for p in (manifest.get("slug"), manifest.get("timestamp")) if p)
    lineas = [
        '<header class="portada">',
        '<p class="tipo">Revisión sistemática · PRISMA 2020</p>',
        f"<h1>{html.escape(titulo)}</h1>",
    ]
    if autor:
        lineas.append(f'<p class="autor">{html.escape(autor)}</p>')
    if fecha:
        lineas.append(f'<p class="fecha">{html.escape(fecha)}</p>')
    if pregunta:
        lineas.append(f'<p class="pregunta">{html.escape(str(pregunta))}</p>')
    sello = html.escape(str(manifest.get("engine") or "revisia"))
    if corrida:
        sello += f" · corrida {html.escape(corrida)}"
    lineas.append(f'<p class="sello">Generado con {sello} · documento autocontenido</p>')
    lineas.append("</header>")
    return "\n".join(lineas)


def _figuras_meta(assets_dir: Path) -> str:
    parts = []
    numero = 1
    for nombre, descripcion in _FIGURAS_META:
        path = assets_dir / nombre
        if path.is_file():
            parts.append(_figure_html(path, f"Figura {numero}. {descripcion}"))
            numero += 1
    return "\n".join(parts)


def _wrap_html(titulo: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n<head>\n<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"<title>{html.escape(titulo)}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def assemble_html(run_dir: Path | str) -> str:
    """Ensambla el deliverable de ``run_dir`` en un HTML autocontenido."""
    run_dir = Path(run_dir)
    deliverable = run_dir / "deliverable"
    if not deliverable.is_dir():
        raise FileNotFoundError(f"{deliverable} no existe: ¿es {run_dir} una corrida de revisia?")
    manifest = _load_manifest(run_dir)
    flow_table = _flow_table(manifest)
    doc_path = deliverable / "documento.md"
    doc_md = doc_path.read_text(encoding="utf-8") if doc_path.exists() else None

    titulo = _titulo(doc_md, manifest, run_dir)
    body: list[str] = [_portada(titulo, _autor(doc_md), _fecha_legible(manifest), manifest)]

    if doc_md:
        # La portada ya muestra el título: el H1 inicial del artículo se retira.
        preparado = re.sub(r"\A# .+\r?\n", "", doc_md, count=1)
        preparado = _embed_md_images(replace_mermaid_blocks(preparado, flow_table), deliverable)
        body.append(f'<main class="articulo">\n{_md_to_html(preparado)}\n</main>')

    figuras = _figuras_meta(deliverable / "assets")
    figuras_colocadas = False
    for nombre, heading in _SECTIONS:
        path = deliverable / nombre
        if not path.exists():
            continue
        texto = replace_mermaid_blocks(path.read_text(encoding="utf-8"), flow_table)
        texto = _demote_headings(_embed_md_images(texto, deliverable))
        seccion = _md_to_html(texto)
        if nombre == "meta_analisis.md" and figuras:
            seccion += "\n" + figuras
            figuras_colocadas = True
        body.append(
            f'<section class="anexo">\n<h2>{html.escape(heading)}</h2>\n{seccion}\n</section>'
        )
    if figuras and not figuras_colocadas:
        body.append(f'<section class="anexo">\n<h2>Figuras</h2>\n{figuras}\n</section>')

    bib = deliverable / "referencias.bib"
    if bib.exists():
        contenido = html.escape(bib.read_text(encoding="utf-8"))
        body.append(
            '<section class="anexo">\n<h2>Anexo J · Referencias (BibTeX)</h2>\n'
            f'<pre class="bibtex">{contenido}</pre>\n</section>'
        )
    return _wrap_html(titulo, "\n".join(body))


def _render_pdf(html_text: str, out: Path) -> None:
    try:
        from weasyprint import HTML  # extra opcional `pdf` (import perezoso)
    except (ImportError, OSError) as exc:
        raise RuntimeError(f"{_PDF_HINT} Detalle: {exc}") from exc
    HTML(string=html_text).write_pdf(str(out))


def export_run(run_dir: Path | str, fmt: str = "html", out: Path | str | None = None) -> Path:
    """Exporta la corrida a un documento único; devuelve la ruta escrita.

    Args:
        run_dir: carpeta de la corrida (``runs/<slug>-<fecha>``).
        fmt: ``"html"`` (autocontenido, default) o ``"pdf"`` (extra ``pdf``).
        out: ruta de salida; por defecto ``<run_dir>/deliverable/<slug>.<fmt>``.

    Raises:
        FileNotFoundError: si la corrida no tiene ``deliverable/``.
        ValueError: si ``fmt`` no es ``html`` ni ``pdf``.
        RuntimeError: si ``fmt="pdf"`` y WeasyPrint no está disponible.
    """
    if fmt not in {"html", "pdf"}:
        raise ValueError(f"Formato desconocido: {fmt!r}. Usa html o pdf.")
    run_dir = Path(run_dir)
    html_text = assemble_html(run_dir)
    slug = str(_load_manifest(run_dir).get("slug") or run_dir.name)
    destino = Path(out) if out else run_dir / "deliverable" / f"{slug}.{fmt}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "html":
        destino.write_text(html_text, encoding="utf-8")
    else:
        _render_pdf(html_text, destino)
    return destino
