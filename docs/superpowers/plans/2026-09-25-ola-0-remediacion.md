# Ola 0 del plan de remediación · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar los hallazgos de la Ola 0 de la auditoría 2026-09-03 (C4, A1, A2, M1-parcial, media C1, parte de C3, dos bajos de estadística) en tres PRs temáticas apiladas.

**Architecture:** Correcciones locales sin rediseño. PR-A endurece la frontera con el exterior (nombre de modelo, shim de Windows, exportador HTML/PDF). PR-B hace que el pipeline no mienta sobre la decisión humana y la procedencia. PR-C repara el default roto, el empaquetado y dos métricas que inventaban ceros.

**Tech Stack:** Python 3.13 (suite también en 3.11/3.12), Pydantic v2, PyYAML, `markdown`, `nh3` 0.3.x (nuevo), WeasyPrint ≥ 70 (extra `pdf`), pytest, ruff, black, uv, hatchling.

**Spec:** `docs/superpowers/specs/2026-09-25-ola-0-remediacion-design.md` (leer §3 Decisiones antes de empezar).

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes y commits **en español**, con el tono del repo (docstrings que explican el porqué y citan la auditoría: "auditoría 2026-09-03, A2").
- Estilo: `ruff` (reglas `E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100). Ambos deben quedar limpios.
- `from __future__ import annotations` al inicio de todo módulo nuevo, como el resto del paquete.
- Tests offline, sin red, deterministas. Ningún test invoca `claude`, WeasyPrint real ni APIs.
- Línea base: **190 tests en verde** en 3.13. Ningún test existente se borra; los que cambian de expectativa se listan explícitamente en su tarea.
- Commits pequeños, uno por tarea como mínimo, mensaje en español con prefijo convencional (`fix:`, `feat:`, `test:`, `chore:`), terminando con la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **No tocar** `CHANGELOG.md`, `README.md` ni el spec: el integrador los actualiza (Tarea 8) para evitar conflictos entre pistas paralelas.
- **No tocar** `runs/` ni `protocols/<slug>/` distintos de `_TEMPLATE` (no versionados).
- Comando de tests en 3.13: `uv run pytest -p no:cacheprovider`. Lint: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`

---

## Topología de ejecución (subagentes)

Las tres PRs tocan conjuntos de ficheros casi disjuntos. Solapes verificados y cómo se resuelven:

| Fichero | Pistas | Resolución |
|---|---|---|
| `pyproject.toml` | A (`dependencies`, extra `pdf`) · C (`[tool.hatch.build.targets.sdist]`) | Secciones distintas → merge automático |
| `uv.lock` | solo A | — |
| `revisia/audit.py` | B (check `provenance` tras `manifest`, ~l.133) · C (check `gold`, ~l.250) | Hunks separados → merge automático |
| `revisia/cli.py` | B (`main()`, ~l.423) · C (`_cmd_validate` ~l.48, `p_check` ~l.366, resumen ~l.167) | Hunks separados → merge automático |
| `tests/test_audit.py` | B (fixture + tests al final) · C (test al final) | Conflicto trivial al final del fichero → lo resuelve el integrador |

Por eso las pistas **corren en paralelo**, cada una en su worktree y rama, y el integrador las apila al final (Tarea 8):

| Pista | Worktree | Rama | Tareas (secuenciales dentro de la pista) |
|---|---|---|---|
| A | `C:\revisia` | `fix/ola0-seguridad-exportador` | 1 → 2 |
| B | `C:\revisia-wt\b` | `fix/ola0-honestidad-pipeline` | 3 → 4 |
| C | `C:\revisia-wt\c` | `fix/ola0-higiene` | 5 → 6 → 7 |

Cada tarea: implementador (subagente fresco, TDD) → revisor (subagente fresco: primero cumplimiento del spec, después calidad) → correcciones si las hay → siguiente tarea. Las Tareas 8 (integración) y 9 (auditoría final) las ejecuta el controlador.

En cada worktree, el primer `uv run` crea su propio `.venv` (necesita red una vez).

---

## Pista A · PR-A `fix/ola0-seguridad-exportador`

### Task 1: Endurecer los proveedores (A-1 nombre de modelo, A-2 shim de Windows)

**Files:**
- Modify: `revisia/llm/registry.py` (import de pydantic; clase `ProviderConfig`, l.35-51)
- Modify: `revisia/llm/providers/claude_code.py` (imports l.20-31; constantes tras l.49; `_command` l.104-118)
- Test: `tests/test_llm_registry.py`, `tests/test_claude_code_provider.py`

**Interfaces:**
- Produces: `revisia.llm.registry.MODEL_NAME_PATTERN: str`; `ClaudeCodeProvider._guard_cmd_shim(cmd: list[str]) -> None` (staticmethod, lanza `RuntimeError`).

- [ ] **Step 1: Tests que fallan para A-1** — añadir al final de `tests/test_llm_registry.py` (añadir `import pytest` y `from pydantic import ValidationError` a los imports si faltan; `ProviderConfig` ya se importa desde `revisia.llm`):

```python
@pytest.mark.parametrize(
    "bad",
    [
        'opus" & calc & "',  # reproducción de la auditoría (A1, BatBadBut)
        "sonnet|whoami",
        "a%PATH%",
        "x\ny",
        "gpt 4",
        "",
        "m" * 129,
    ],
)
def test_provider_model_rejects_injection(bad: str) -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(provider="claude_code", model=bad)


@pytest.mark.parametrize(
    "ok",
    [
        "sonnet",
        "gemini-3.5-flash-lite",
        "openai/gpt-5",
        "fake:fake-1",
        "llama3.1:8b",
        "claude-x@20260101",
        "glm-5.2",
    ],
)
def test_provider_model_accepts_real_ids(ok: str) -> None:
    assert ProviderConfig(provider="gemini", model=ok).model == ok
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest tests/test_llm_registry.py -p no:cacheprovider -q`
Expected: FAIL en los 7 casos de `test_provider_model_rejects_injection` (DID NOT RAISE); los de `accepts` pasan.

- [ ] **Step 3: Implementar A-1** en `revisia/llm/registry.py`:

Cambiar `from pydantic import BaseModel` por `from pydantic import BaseModel, Field`. Justo antes de `class ProviderConfig`, añadir:

```python
# Identificador de modelo admisible (auditoría 2026-09-03, A1). El nombre viaja
# como argumento de línea de comandos en `claude_code` y, en Windows, un shim
# .CMD lo re-parsea con cmd.exe (BatBadBut). Solo caracteres que no son
# metacaracteres de ningún shell; `@` y `+` admiten ids estilo Vertex/OpenRouter.
MODEL_NAME_PATTERN = r"^[A-Za-z0-9._:/@+-]{1,128}$"
```

y en la clase sustituir `model: str` por:

```python
    model: str = Field(pattern=MODEL_NAME_PATTERN)
```

Añadir a la docstring de la clase, en `model:`, "(acotado por ``MODEL_NAME_PATTERN``)".

- [ ] **Step 4: Verificar A-1**

Run: `uv run pytest tests/test_llm_registry.py -p no:cacheprovider -q`
Expected: PASS todos.

- [ ] **Step 5: Tests que fallan para A-2** — añadir al final de `tests/test_claude_code_provider.py`:

```python
# ── A-2 · guardia fail-closed del shim .CMD (auditoría 2026-09-03, A1) ──────


def test_windows_cmd_shim_rejects_metachars(monkeypatch) -> None:
    recorder: list[dict] = []
    monkeypatch.setattr(cc.shutil, "which", lambda _name: r"C:\npm\claude.CMD")
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("x")], recorder))
    # Construcción directa: salta ProviderConfig; la guardia debe sostenerse sola.
    provider = cc.ClaudeCodeProvider(model='opus" & calc & "')
    with pytest.raises(RuntimeError, match="BatBadBut"):
        provider.complete(LLMRequest(prompt="hola"))
    assert recorder == []  # no se llegó a crear ningún proceso


def test_windows_cmd_shim_rejects_metachars_in_system_prompt(monkeypatch) -> None:
    recorder: list[dict] = []
    monkeypatch.setattr(cc.shutil, "which", lambda _name: r"C:\npm\claude.cmd")
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("x")], recorder))
    provider = cc.ClaudeCodeProvider(model="sonnet")
    with pytest.raises(RuntimeError, match="BatBadBut"):
        provider.complete(LLMRequest(prompt="hola", system="usa el 100% & sal"))
    assert recorder == []


def test_windows_cmd_shim_permite_argumentos_seguros(monkeypatch) -> None:
    recorder: list[dict] = []
    monkeypatch.setattr(cc.shutil, "which", lambda _name: r"C:\npm\claude.CMD")
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")], recorder))
    provider = cc.ClaudeCodeProvider(model="sonnet")
    # El prompt viaja por stdin, no por cmd.exe: puede traer cualquier carácter.
    resp = provider.complete(LLMRequest(prompt="abstract con & y %PATH%", system="eres conciso"))
    assert resp.text == "ok"
    assert recorder[0]["cmd"][0].endswith("claude.CMD")
    assert recorder[0]["input"] == "abstract con & y %PATH%"


def test_binario_nativo_no_activa_la_guardia(monkeypatch) -> None:
    recorder: list[dict] = []
    monkeypatch.setattr(cc.shutil, "which", lambda _name: r"C:\bin\claude.exe")
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")], recorder))
    provider = cc.ClaudeCodeProvider(model="sonnet")
    # CreateProcess sobre un .exe no re-parsea: la guardia no aplica.
    resp = provider.complete(LLMRequest(prompt="x", system="usa el 100%"))
    assert resp.text == "ok"
    assert len(recorder) == 1
```

- [ ] **Step 6: Verificar que fallan**

Run: `uv run pytest tests/test_claude_code_provider.py -p no:cacheprovider -q`
Expected: FAIL `test_windows_cmd_shim_rejects_metachars` y `..._in_system_prompt` (DID NOT RAISE); los otros dos pasan.

- [ ] **Step 7: Implementar A-2** en `revisia/llm/providers/claude_code.py`:

Añadir `from pathlib import Path` a los imports (orden alfabético de stdlib, tras `import os`... respetar el orden que imponga `ruff` I). Tras `_CLEAN_ENV_FLAG = ...` añadir:

```python
# Shims que CreateProcess delega en cmd.exe, que RE-PARSEA la línea de comandos
# (BatBadBut, auditoría 2026-09-03 A1): los argumentos ya citados por subprocess
# recuperan el significado de estos metacaracteres. No se escapan (``%VAR%`` no
# es neutralizable dentro de comillas y ``!`` depende de la expansión
# retardada): si alguno aparece, la llamada se rechaza antes de crear el proceso.
_CMD_SHIM_SUFFIXES = (".cmd", ".bat")
_CMD_METACHARS = frozenset('"&|<>^%!\r\n')
```

En `_command`, sustituir el `return cmd` final por:

```python
        self._guard_cmd_shim(cmd)
        return cmd
```

y añadir, justo después de `_command`, el método:

```python
    @staticmethod
    def _guard_cmd_shim(cmd: list[str]) -> None:
        """Rechaza argumentos con metacaracteres de cmd.exe si el CLI es un shim.

        Con el binario nativo (``claude.exe`` o POSIX) no hace nada: solo un
        ``.cmd``/``.bat`` pasa por cmd.exe. El prompt viaja por stdin y no se
        comprueba: no atraviesa cmd.exe.

        Raises:
            RuntimeError: si algún argumento contiene un metacarácter de cmd.exe.
        """
        exe = Path(cmd[0])
        if exe.suffix.lower() not in _CMD_SHIM_SUFFIXES:
            return
        for arg in cmd[1:]:
            bad = sorted(set(arg) & _CMD_METACHARS)
            if bad:
                raise RuntimeError(
                    f"Argumento no seguro para el shim {exe.name}: contiene {''.join(bad)!r}. "
                    "En Windows, cmd.exe re-interpreta esos caracteres al lanzar un .cmd/.bat "
                    "(BatBadBut) y podría ejecutar comandos. Instala el binario nativo de "
                    "Claude Code (claude.exe) o usa un modelo y un system prompt sin esos "
                    "caracteres."
                )
```

- [ ] **Step 8: Verificar A-2 y la suite**

Run: `uv run pytest -p no:cacheprovider -q`
Expected: PASS todo (190 + 14 nuevos parametrizados/tests = 204 o más).

- [ ] **Step 9: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores (si `ruff format`/`black` reformatean, aplicar `uv run ruff format <ficheros>` y re-verificar).

- [ ] **Step 10: Commit**

```bash
git add revisia/llm/registry.py revisia/llm/providers/claude_code.py tests/test_llm_registry.py tests/test_claude_code_provider.py
git commit -m "fix(llm): acotar el nombre de modelo y bloquear metacaracteres en shims .cmd (A1)" -m "ProviderConfig.model con patrón ^[A-Za-z0-9._:/@+-]{1,128}\$ y guardia fail-closed en ClaudeCodeProvider cuando el CLI resuelto es .cmd/.bat (BatBadBut). Auditoría 2026-09-03, A1." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Endurecer el exportador (A-3 confinamiento, A-4 saneado nh3, A-5 fetcher PDF, A-6 dependencias)

**Files:**
- Modify: `pyproject.toml` (bloque `dependencies`; extra `pdf`)
- Modify: `uv.lock` (regenerado por `uv lock`)
- Modify: `revisia/exports/document.py` (docstring del módulo l.18-21; imports l.24-35; `_embed_md_images` l.198-213; `_md_to_html` l.225-226; `_render_pdf` l.350-355)
- Test: `tests/test_export_document.py`

**Interfaces:**
- Consumes: nada de la Tarea 1.
- Produces: `_md_to_html(text: str) -> str` ahora devuelve HTML saneado; constantes privadas `_ALLOWED_TAGS`, `_ALLOWED_ATTRIBUTES`, función `_attribute_filter(tag: str, attr: str, value: str) -> str | None`.

- [ ] **Step 1: Dependencias.** En `pyproject.toml`, dentro de `dependencies`, tras la línea `"markdown>=3.6",` añadir:

```toml
    # Saneado del HTML del exportador (auditoría 2026-09-03, A2/M1): allowlist
    # sobre el Markdown convertido. Wheel precompilado (Rust/ammonia) sin deps
    # transitivas; con él el núcleo deja de ser pura-Python, a sabiendas.
    "nh3>=0.3",
```

y en `[project.optional-dependencies]` cambiar `pdf = ["weasyprint>=63"]` por `pdf = ["weasyprint>=70"]`, añadiendo al comentario del extra: "≥70: `url_fetcher` es una instancia de `URLFetcher`, no un callable."

Run: `uv lock && uv sync`
Expected: `uv.lock` actualizado con `nh3`; `uv run python -c "import nh3"` sin error.

- [ ] **Step 2: Tests que fallan** — añadir al final de `tests/test_export_document.py`:

```python
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
```

- [ ] **Step 3: Verificar que fallan**

Run: `uv run pytest tests/test_export_document.py -p no:cacheprovider -q`
Expected: FAIL `test_embed_images_rejects_traversal`, `..._rejects_image_outside_deliverable`, `..._solo_extensiones_de_imagen`, `test_export_html_strips_script_and_handlers`, `test_anexos_tambien_se_sanean`, `test_pdf_url_fetcher_rejects_non_data` (este último con `ImportError: cannot import name 'URLFetcher'` convertido en `RuntimeError`, o `KeyError`).

- [ ] **Step 4: Implementar A-3** — sustituir `_embed_md_images` completo en `revisia/exports/document.py`:

```python
def _embed_md_images(text: str, base_dir: Path) -> str:
    """Reescribe ``![alt](ruta)`` a ``<figure>`` con la imagen embebida.

    Solo se embeben imágenes (extensión en ``_MIME``) que queden DENTRO de
    ``base_dir`` tras resolver ``..`` y enlaces simbólicos: una referencia como
    ``![x](../../.env)`` no puede sacar ficheros del entregable (auditoría
    2026-09-03, A2). Las referencias externas (http/https), rotas o fuera del
    entregable se degradan a su texto alternativo en cursiva: el HTML resultante
    nunca carga recursos de fuera.
    """
    root = base_dir.resolve()

    def _sub(match: re.Match[str]) -> str:
        alt, ref = match.group(1), match.group(2)
        if not ref.startswith(("http://", "https://", "data:", "file:")):
            target = (base_dir / ref).resolve()
            if (
                target.is_relative_to(root)
                and target.suffix.lower() in _MIME
                and target.is_file()
            ):
                return _figure_html(target, alt)
        return f"*{alt}*" if alt else ""

    return _IMG_MD_RE.sub(_sub, text)
```

- [ ] **Step 5: Implementar A-4.** Añadir `import nh3` tras `import markdown as md_lib` (bloque de terceros). Tras la definición de `_MIME` añadir:

```python
# Saneado del Markdown convertido (auditoría 2026-09-03, A2/M1). Todo el texto no
# confiable del entregable (lo redacta un LLM) entra al HTML por `_md_to_html`;
# lo que genera el propio exportador (portada, figuras de meta-análisis, BibTeX,
# plantilla con <style>) no pasa por ahí y ya va escapado.
_ALLOWED_TAGS = frozenset(
    {
        "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "div", "span",
        "strong", "em", "b", "i", "del", "sup", "sub", "code", "pre", "blockquote",
        "ul", "ol", "li", "a", "table", "thead", "tbody", "tfoot", "tr", "th", "td",
        "caption", "figure", "figcaption", "img",
    }
)
_ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title"},
    "img": {"src", "alt"},
    "code": {"class"},  # language-x de los bloques de código
    "th": {"style"},  # la extensión `tables` alinea con style="text-align: …"
    "td": {"style"},
}


def _attribute_filter(tag: str, attr: str, value: str) -> str | None:
    """Restringe ``data:`` a imágenes y veta ``javascript:``/``data:`` en enlaces."""
    if tag == "img" and attr == "src":
        return value if value.startswith("data:image/") else None
    if tag == "a" and attr == "href":
        low = value.strip().lower()
        return None if low.startswith(("data:", "javascript:")) else value
    return value
```

(`black` reformateará el `frozenset` a una línea por elemento; es aceptable.) Sustituir `_md_to_html` por:

```python
def _md_to_html(text: str) -> str:
    """Convierte Markdown a HTML y lo sanea con una allowlist (``nh3``).

    Tumba ``<script>``/``<style>`` con su contenido, los manejadores ``on*``,
    las imágenes remotas y cualquier ``style`` que no sea ``text-align``.
    """
    raw = md_lib.markdown(text, extensions=["tables", "fenced_code"])
    return nh3.clean(
        raw,
        tags=set(_ALLOWED_TAGS),
        clean_content_tags={"script", "style"},
        attributes=_ALLOWED_ATTRIBUTES,
        attribute_filter=_attribute_filter,
        url_schemes={"http", "https", "mailto", "data"},
        filter_style_properties={"text-align"},
    )
```

En la docstring del módulo, tras el párrafo de `markdown`, añadir: "El HTML resultante se sanea con ``nh3`` (allowlist de etiquetas y atributos, solo ``data:`` en imágenes): el entregable lo redacta un LLM y no se confía en él."

- [ ] **Step 6: Implementar A-5** — sustituir `_render_pdf`:

```python
def _render_pdf(html_text: str, out: Path) -> None:
    try:
        from weasyprint import HTML, URLFetcher  # extra opcional `pdf` (import perezoso)
    except (ImportError, OSError) as exc:
        raise RuntimeError(f"{_PDF_HINT} Detalle: {exc}") from exc
    # Solo data: (las figuras ya viajan embebidas): WeasyPrint no abre file:// ni
    # http(s):// aunque el HTML los traiga (auditoría 2026-09-03, M1).
    fetcher = URLFetcher(allowed_protocols={"data"})
    HTML(string=html_text, url_fetcher=fetcher).write_pdf(str(out))
```

- [ ] **Step 7: Verificar**

Run: `uv run pytest tests/test_export_document.py -p no:cacheprovider -q`
Expected: PASS todo, incluidos los tests previos (`test_html_autocontenido_sin_recursos_externos`, `test_bibtex_incluido_y_escapado`, `test_pdf_sin_weasyprint_error_accionable`, etc.).

Run: `uv run pytest -p no:cacheprovider -q` → PASS todo.

- [ ] **Step 8: Lint** — mismo comando que la Tarea 1. Expected: limpio.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock revisia/exports/document.py tests/test_export_document.py
git commit -m "fix(export): confinar imágenes al entregable, sanear el HTML con nh3 y restringir el fetcher del PDF (A2, M1)" -m "_embed_md_images exige is_relative_to(deliverable) y extensión de imagen; _md_to_html sanea con allowlist (solo data:image en img, style solo text-align); WeasyPrint recibe URLFetcher(allowed_protocols={'data'}). nh3>=0.3 al núcleo; extra pdf a weasyprint>=70. Auditoría 2026-09-03, A2 y M1." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Pista B · PR-B `fix/ola0-honestidad-pipeline`

### Task 3: Validar autonomía y `decision.yml` (B-1, B-2) con errores accionables en el CLI

**Files:**
- Modify: `revisia/config.py` (import de pydantic l.16; constantes tras `DEFAULT_AUTONOMY` l.46; validador en `ReviewProtocol`)
- Modify: `revisia/orchestration/hitl.py` (imports; `HumanDecision`; `DecisionFileError`; `review_gate`; `_read_decision`)
- Modify: `revisia/cli.py` (solo `main()`, bloque final l.423-430, e import de `ValidationError`)
- Test: `tests/test_config.py`, `tests/test_hitl.py` (nuevo), `tests/test_cli_errores.py` (nuevo)

**Interfaces:**
- Produces: `revisia.config.AUTONOMY_LEVELS: tuple[str, ...]`, `revisia.config.JUDGMENT_STAGES: tuple[str, ...]`; `revisia.orchestration.hitl.HumanDecision` (Pydantic: `approved: StrictBool`, `actor: str = "human:desconocido"`, `reason: str | None = None`, `extra="allow"`); `revisia.orchestration.hitl.DecisionFileError(ValueError)`; `_read_decision(path: Path) -> HumanDecision | None`.

- [ ] **Step 1: Tests que fallan para B-1** — en `tests/test_config.py` añadir imports `import shutil`, `import pytest`, `import yaml`, `from pydantic import ValidationError`, cambiar `from revisia.config import load_protocol` por `from revisia.config import ReviewProtocol, load_protocol`, y añadir al final:

```python
def _template_raw() -> dict:
    raw = yaml.safe_load((TEMPLATE_DIR / "protocol.yml").read_text(encoding="utf-8"))
    raw["slug"] = "demo"
    return raw


@pytest.mark.parametrize("stage", ["screening_ta", "screening_ft", "extraccion", "rob"])
@pytest.mark.parametrize("level", ["A2", "A3"])
def test_autonomy_a3_in_judgement_stage_rejected(stage: str, level: str) -> None:
    raw = _template_raw()
    raw["autonomy"][stage] = level
    with pytest.raises(ValidationError, match="nunca superan A1"):
        ReviewProtocol.model_validate(raw)


def test_autonomy_nivel_invalido_rechazado() -> None:
    raw = _template_raw()
    raw["autonomy"]["busqueda"] = "A5"
    with pytest.raises(ValidationError, match="inválido"):
        ReviewProtocol.model_validate(raw)


def test_autonomy_etapa_desconocida_rechazada() -> None:
    raw = _template_raw()
    raw["autonomy"]["cribado"] = "A1"
    with pytest.raises(ValidationError, match="etapa desconocida"):
        ReviewProtocol.model_validate(raw)


def test_autonomy_a3_permitido_en_etapa_determinista() -> None:
    raw = _template_raw()
    raw["autonomy"]["dedup"] = "A3"
    assert ReviewProtocol.model_validate(raw).autonomy_for("dedup") == "A3"


def test_load_protocol_con_a3_en_juicio_falla(tmp_path: Path) -> None:
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["autonomy"]["rob"] = "A3"
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_protocol(proto)
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest tests/test_config.py -p no:cacheprovider -q`
Expected: FAIL los 8 casos de `test_autonomy_a3_in_judgement_stage_rejected`, `nivel_invalido`, `etapa_desconocida`, `load_protocol_con_a3`; `a3_permitido_en_etapa_determinista` pasa.

- [ ] **Step 3: Implementar B-1** en `revisia/config.py`: cambiar el import a `from pydantic import BaseModel, Field, field_validator`. Tras `DEFAULT_AUTONOMY` añadir:

```python
AUTONOMY_LEVELS: tuple[str, ...] = ("A0", "A1", "A2", "A3")
# Etapas de juicio (AGENTS.md): nunca superan A1; la decisión final es humana.
JUDGMENT_STAGES: tuple[str, ...] = ("screening_ta", "screening_ft", "extraccion", "rob")
```

Dentro de `ReviewProtocol`, justo después del campo `grounding` y antes de `autonomy_for`, añadir:

```python
    @field_validator("autonomy")
    @classmethod
    def _autonomia_valida(cls, value: dict[str, str]) -> dict[str, str]:
        """Aplica la regla dura de autonomía al cargar (auditoría 2026-09-03, C1).

        Un ``A3`` en una etapa de juicio apagaba todo el HITL en silencio; ahora
        el protocolo no carga.
        """
        for stage, level in value.items():
            if stage not in STAGES:
                raise ValueError(
                    f"autonomy: etapa desconocida {stage!r}. Etapas válidas: {', '.join(STAGES)}."
                )
            if level not in AUTONOMY_LEVELS:
                raise ValueError(
                    f"autonomy.{stage}: nivel {level!r} inválido; usa uno de "
                    f"{', '.join(AUTONOMY_LEVELS)}."
                )
            if stage in JUDGMENT_STAGES and level not in ("A0", "A1"):
                raise ValueError(
                    f"autonomy.{stage}: {level} no permitido. Regla no negociable de "
                    "AGENTS.md: screening, extracción y riesgo de sesgo nunca superan A1 "
                    "(la decisión final es siempre humana). Usa A0 o A1."
                )
        return value
```

- [ ] **Step 4: Verificar B-1**

Run: `uv run pytest tests/test_config.py -p no:cacheprovider -q` → PASS.

- [ ] **Step 5: Tests que fallan para B-2** — crear `tests/test_hitl.py`:

```python
"""Tests del checkpoint humano file-based (auditoría 2026-09-03, C1 y bajos)."""

from __future__ import annotations

from pathlib import Path

import pytest

from revisia.orchestration.hitl import DecisionFileError, review_gate
from revisia.orchestration.run_context import RunContext


def _gate(tmp_path: Path, decision_text: str | None, *, auto_approve: bool = False):
    ctx = RunContext("demo", tmp_path, "T")
    stage_dir = ctx.stage_dir("reporte")
    if decision_text is not None:
        (stage_dir / "decision.yml").write_text(decision_text, encoding="utf-8")
    result = review_gate(
        stage="reporte",
        autonomy="A1",
        run_ctx=ctx,
        review_payload={"included": 1},
        auto_approve=auto_approve,
    )
    return ctx, result


def test_decision_string_false_does_not_approve(tmp_path: Path) -> None:
    # bool("false") es True: antes, esta decisión APROBABA.
    with pytest.raises(DecisionFileError, match="booleano"):
        _gate(tmp_path, 'approved: "false"\n')


def test_decision_false_rechaza(tmp_path: Path) -> None:
    ctx, result = _gate(tmp_path, "approved: false\nactor: human:revisora\n")
    assert result.status == "rejected"
    entry = ctx.ledger.read_all()[-1]
    assert entry.action == "reject"
    assert entry.actor == "human:revisora"


def test_decision_booleana_aprueba_y_registra_actor(tmp_path: Path) -> None:
    ctx, result = _gate(tmp_path, "approved: true\nactor: human:jhon\nreason: ok\n")
    assert result.status == "approved"
    entry = ctx.ledger.read_all()[-1]
    assert entry.actor == "human:jhon"
    assert entry.detail == {"reason": "ok"}


def test_campos_extra_se_conservan_en_el_ledger(tmp_path: Path) -> None:
    ctx, _ = _gate(tmp_path, "approved: true\nnota: revisado a mano\n")
    assert ctx.ledger.read_all()[-1].detail == {"nota": "revisado a mano"}


@pytest.mark.parametrize(
    "text",
    [
        "- approved: true\n",  # raíz lista (antes: AttributeError)
        "",  # vacío (antes: rechazo silencioso de human:desconocido)
        "approved: [\n",  # YAML roto (antes: traceback de yaml)
        "actor: human:x\n",  # falta approved
    ],
)
def test_malformed_decision_yaml_is_actionable(tmp_path: Path, text: str) -> None:
    with pytest.raises(DecisionFileError, match="decision.yml"):
        _gate(tmp_path, text)


def test_auto_approve_sin_decision(tmp_path: Path) -> None:
    ctx, result = _gate(tmp_path, None, auto_approve=True)
    assert result.status == "approved"
    entry = ctx.ledger.read_all()[-1]
    assert entry.actor == "auto-approve (demo)"
    assert entry.detail == {}


def test_sin_decision_pausa(tmp_path: Path) -> None:
    _, result = _gate(tmp_path, None)
    assert result.status == "paused"
```

- [ ] **Step 6: Verificar que fallan**

Run: `uv run pytest tests/test_hitl.py -p no:cacheprovider -q`
Expected: ERROR de colección (`ImportError: cannot import name 'DecisionFileError'`).

- [ ] **Step 7: Implementar B-2** en `revisia/orchestration/hitl.py`. Añadir a los imports `from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError`. Tras `GateResult` añadir:

```python
class DecisionFileError(ValueError):
    """``decision.yml`` ilegible o inválido: mensaje accionable, no traceback."""


class HumanDecision(BaseModel):
    """Contenido validado de ``<stage>/decision.yml`` (auditoría 2026-09-03, C1).

    ``approved`` es un booleano YAML estricto: la cadena ``"false"`` ya no
    aprueba (``bool("false")`` es ``True``). Los campos extra se conservan y
    viajan al ``detail`` del ledger.
    """

    model_config = ConfigDict(extra="allow")

    approved: StrictBool
    actor: str = "human:desconocido"
    reason: str | None = None
```

En `review_gate`, sustituir desde `decision = _read_decision(...)` hasta el final de la función por:

```python
    decision = _read_decision(stage_dir / "decision.yml")
    if decision is None and auto_approve:
        decision = HumanDecision(approved=True, actor="auto-approve (demo)")

    if decision is None:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}' ({autonomy}). Revisa "
                f"{request_path} y crea {stage_dir / 'decision.yml'} con "
                f"`approved: true` (o vuelve a correr con --auto-approve)."
            ),
        )

    run_ctx.ledger.append(
        DecisionEntry(
            stage=stage,
            actor=decision.actor,
            autonomy=autonomy,
            action="approve" if decision.approved else "reject",
            detail=decision.model_dump(exclude={"approved", "actor"}, exclude_none=True),
        )
    )
    if decision.approved:
        return GateResult("approved", f"{stage}: aprobado por {decision.actor}.")
    return GateResult("rejected", f"{stage}: rechazado por {decision.actor}.")
```

Sustituir `_read_decision` por:

```python
_DECISION_HINT = (
    "Se espera un mapa YAML con `approved: true` o `approved: false` (booleano, sin "
    "comillas) y, opcionalmente, `actor: human:<nombre>` y `reason: <texto>`."
)


def _read_decision(path: Path) -> HumanDecision | None:
    """Lee y valida ``decision.yml``; ``None`` si no existe.

    Raises:
        DecisionFileError: si el fichero está vacío, no es YAML válido, su raíz
            no es un mapa o ``approved`` no es un booleano.
    """
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DecisionFileError(f"{path}: YAML inválido ({exc}). {_DECISION_HINT}") from exc
    if raw is None:
        raise DecisionFileError(f"{path}: está vacío. {_DECISION_HINT}")
    if not isinstance(raw, dict):
        raise DecisionFileError(
            f"{path}: la raíz es {type(raw).__name__}, no un mapa. {_DECISION_HINT}"
        )
    try:
        return HumanDecision.model_validate(raw)
    except ValidationError as exc:
        detalle = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise DecisionFileError(
            f"{path}: decisión inválida ({detalle}). `approved` debe ser un booleano "
            f"YAML. {_DECISION_HINT}"
        ) from exc
```

Actualizar la docstring del módulo: en la viñeta de `decision.yml` añadir "(validado: `approved` booleano estricto; un fichero inválido detiene la corrida con un mensaje accionable)".

- [ ] **Step 8: Verificar B-2**

Run: `uv run pytest tests/test_hitl.py tests/test_pipeline_fake.py -p no:cacheprovider -q` → PASS.

- [ ] **Step 9: Tests que fallan para el CLI** — crear `tests/test_cli_errores.py`:

```python
"""Errores de configuración y de decisión humana: mensaje, no traceback."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from revisia.cli import main
from revisia.orchestration.hitl import DecisionFileError

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "protocols" / "_TEMPLATE"
EXAMPLE = ROOT / "examples" / "demo-mini-review"


def _protocolo_con_autonomia(tmp_path: Path, stage: str, level: str) -> Path:
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["autonomy"][stage] = level
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return proto


def test_cli_validate_protocolo_con_a3_sale_2_sin_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = main(["validate", str(_protocolo_con_autonomia(tmp_path, "screening_ta", "A3"))])
    err = capsys.readouterr().err
    assert rc == 2
    assert "nunca superan A1" in err
    assert "Traceback" not in err


def test_cli_run_protocolo_con_a3_no_arranca(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_debe_correr(*_a, **_k):
        raise AssertionError("run_review no debe llamarse con un protocolo inválido")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _no_debe_correr)
    rc = main(["run", str(_protocolo_con_autonomia(tmp_path, "extraccion", "A2"))])
    assert rc == 2
    assert "nunca superan A1" in capsys.readouterr().err


def test_cli_run_decision_invalida_sale_2(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _falla(*_a, **_k):
        raise DecisionFileError("runs/x/reporte/decision.yml: está vacío.")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _falla)
    rc = main(["run", str(EXAMPLE)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "decision.yml" in err
    assert "Traceback" not in err
```

- [ ] **Step 10: Verificar que fallan**

Run: `uv run pytest tests/test_cli_errores.py -p no:cacheprovider -q`
Expected: FAIL los tres (la `ValidationError`/`DecisionFileError` escapa de `main`).

- [ ] **Step 11: Implementar el manejo en `main()`** (`revisia/cli.py`). Añadir `from pydantic import ValidationError` a los imports de terceros (arriba, tras stdlib). Sustituir el bloque final de `main()`:

```python
    if args.command == "validate":
        return _cmd_validate(protocol_dir)
    if args.command == "run":
        return _cmd_run(args)
```

por:

```python
    if args.command in {"validate", "run"}:
        # Un protocol.yml inválido (p. ej. A3 en una etapa de juicio) se informa
        # como error de uso, no como traceback (auditoría 2026-09-03, C1).
        try:
            load_protocol(protocol_dir)
        except ValidationError as exc:
            print(f"error: protocol.yml inválido en {protocol_dir}:\n{exc}", file=sys.stderr)
            return 2
    if args.command == "validate":
        return _cmd_validate(protocol_dir)
    if args.command == "run":
        from revisia.orchestration.hitl import DecisionFileError

        try:
            return _cmd_run(args)
        except DecisionFileError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
```

- [ ] **Step 12: Verificar**

Run: `uv run pytest -p no:cacheprovider -q` → PASS todo.
Lint (comando de Global Constraints) → limpio.

- [ ] **Step 13: Commit**

```bash
git add revisia/config.py revisia/orchestration/hitl.py revisia/cli.py tests/test_config.py tests/test_hitl.py tests/test_cli_errores.py
git commit -m "fix(hitl): validar autonomía y decision.yml; errores accionables en el CLI (C1)" -m "autonomy rechaza etapas desconocidas, niveles fuera de A0-A3 y A2/A3 en etapas de juicio. decision.yml validado con HumanDecision (approved booleano estricto: 'false' ya no aprueba; vacío, lista o YAML roto -> DecisionFileError). validate/run devuelven rc 2 con mensaje en vez de traceback. Auditoría 2026-09-03, C1." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: El rechazo final es un rechazo (B-3) y procedencia en manifiesto y auditor (B-4)

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (guarda tras `run_ctx.write_manifest(...)`, l.589-599)
- Modify: `revisia/orchestration/run_context.py` (constante; `write_manifest` l.52-73)
- Modify: `revisia/audit.py` (import; check `provenance` tras el bloque del check `manifest`, antes de `# ── 2 · Prompts hash-eados`)
- Test: `tests/test_pipeline_fake.py`, `tests/test_provenance.py`, `tests/test_audit.py`, `tests/test_cli_errores.py`

**Interfaces:**
- Consumes: `HumanDecision`/`DecisionFileError` de la Tarea 3 (indirectamente, vía `review_gate`).
- Produces: `revisia.orchestration.run_context.PROVENANCE_PIPELINE = "pipeline"`; clave `provenance` en `manifest.yml`; check de auditoría con `check_id="provenance"`.

- [ ] **Step 1: Test que falla para B-3** — añadir al final de `tests/test_pipeline_fake.py`:

```python
def test_rejected_final_gate_is_not_completed(tmp_path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST")
    (ctx.stage_dir("reporte") / "decision.yml").write_text(
        "approved: false\nactor: human:revisora\nreason: síntesis sin respaldo\n",
        encoding="utf-8",
    )
    result = run_pipeline(
        protocol, EXAMPLE, ctx, max_results=10, auto_approve=True, search_fn=_fake_search
    )
    assert result.status == "rejected"  # antes: "completed"
    assert "rechazado por human:revisora" in result.message
    assert (ctx.run_dir / "manifest.yml").exists()  # el rechazo deja rastro en disco
    last = ctx.ledger.read_all()[-1]
    assert (last.stage, last.action) == ("reporte", "reject")
```

y en `test_pipeline_end_to_end_offline`, tras `assert (ctx.run_dir / "manifest.yml").exists()`, añadir (con `import yaml` arriba):

```python
    manifest = yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["provenance"] == "pipeline"
```

Añadir al final de `tests/test_cli_errores.py`:

```python
def test_cli_run_rechazado_sale_1_y_no_sedimenta(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from revisia.orchestration.pipeline import PipelineResult

    run_dir = tmp_path / "runs" / "demo-T"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "revisia.orchestration.flow.run_review",
        lambda *_a, **_k: PipelineResult(
            "rejected", "reporte: rechazado por human:x.", run_dir=run_dir
        ),
    )
    brain = tmp_path / "cerebro"
    rc = main(["run", str(EXAMPLE), "--brain", str(brain)])
    assert rc == 1
    assert "REJECTED" in capsys.readouterr().out
    assert list(brain.rglob("*.md")) == []  # una revisión rechazada no se sedimenta
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest tests/test_pipeline_fake.py tests/test_cli_errores.py -p no:cacheprovider -q`
Expected: FAIL `test_rejected_final_gate_is_not_completed` (`'completed' == 'rejected'`) y `test_pipeline_end_to_end_offline` (`KeyError: 'provenance'`). `test_cli_run_rechazado_sale_1_y_no_sedimenta` ya pasa (documenta el contrato del CLI; ver spec B-3).

- [ ] **Step 3: Implementar B-3** en `revisia/orchestration/pipeline.py`: sustituir

```python
    if final_gate.status == "paused":
        return PipelineResult(
            "paused",
            final_gate.message,
```

por

```python
    # Un reporte rechazado ya no se informa como "completed" (auditoría
    # 2026-09-03, C1): el manifiesto queda escrito arriba como rastro.
    if final_gate.status != "approved":
        return PipelineResult(
            final_gate.status,
            final_gate.message,
```

(el resto de argumentos del `PipelineResult` no cambia).

- [ ] **Step 4: Test que falla para `write_manifest`** — añadir al final de `tests/test_provenance.py` (con `import yaml` y `from revisia.orchestration.run_context import RunContext` si faltan):

```python
def test_write_manifest_declara_procedencia_no_sobrescribible(tmp_path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    path = ctx.write_manifest(
        protocol_snapshot={}, counts={}, extra={"provenance": "reconstruction"}
    )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["provenance"] == "pipeline"
    assert list(data)[:4] == ["slug", "created_utc", "timestamp", "provenance"]
```

- [ ] **Step 5: Implementar en `run_context.py`.** Tras los imports, añadir:

```python
# Procedencia que el motor escribe en todo manifiesto que produce (auditoría
# 2026-09-03, C3): distingue una corrida real de una reconstrucción a mano.
PROVENANCE_PIPELINE = "pipeline"
```

En `write_manifest`, añadir `"provenance": PROVENANCE_PIPELINE,` justo después de `"timestamp": self.timestamp,` y, tras cerrar el dict (después de `**(extra or {}),` y la llave de cierre), añadir:

```python
        # La procedencia no es configurable desde `extra`: la fija el motor.
        manifest["provenance"] = PROVENANCE_PIPELINE
```

- [ ] **Step 6: Tests que fallan para el auditor** — en `tests/test_audit.py`, cambiar la firma de `_make_run` a

```python
def _make_run(
    tmp_path,
    *,
    human_decisions: bool = True,
    with_gold: bool = True,
    provenance: str | None = "pipeline",
):
```

y, tras construir `manifest = {...}`, añadir:

```python
    if provenance is not None:
        manifest["provenance"] = provenance
```

Añadir al final del fichero:

```python
def test_audit_fails_on_reconstruction_provenance(tmp_path) -> None:
    report = run_audit(_make_run(tmp_path, provenance="reconstruction"))
    statuses = {c.check_id: c.status for c in report.checks}
    assert statuses["provenance"] == "FAIL"
    assert report.publishable is False


def test_audit_sin_procedencia_falla(tmp_path) -> None:
    report = run_audit(_make_run(tmp_path, provenance=None))
    check = next(c for c in report.checks if c.check_id == "provenance")
    assert check.status == "FAIL"
    assert "ausente" in check.detail


def test_audit_procedencia_pipeline_pasa(tmp_path) -> None:
    report = run_audit(_make_run(tmp_path))
    assert {c.check_id: c.status for c in report.checks}["provenance"] == "PASS"


def test_audit_sin_manifiesto_no_duplica_fail_de_procedencia(tmp_path) -> None:
    run = _make_run(tmp_path)
    (run / "manifest.yml").unlink()
    report = run_audit(run)
    assert "provenance" not in {c.check_id for c in report.checks}
```

- [ ] **Step 7: Verificar que fallan**

Run: `uv run pytest tests/test_audit.py -p no:cacheprovider -q`
Expected: FAIL los tres primeros (`KeyError: 'provenance'` / `StopIteration`); el cuarto pasa.

- [ ] **Step 8: Implementar el check** en `revisia/audit.py`. Añadir a los imports `from revisia.orchestration.run_context import PROVENANCE_PIPELINE`. Justo antes de `# ── 2 · Prompts hash-eados por llamada (trAIce M6) ──` insertar:

```python
    # ── 1b · Procedencia: la corrida la produjo el pipeline (auditoría C3) ────
    if manifest is not None:
        provenance = manifest.get("provenance")
        if provenance == PROVENANCE_PIPELINE:
            add(
                AuditCheck(
                    "provenance",
                    "PRISMA 27 / trAIce M2",
                    "PASS",
                    "Corrida producida por el pipeline de revisia (provenance: pipeline).",
                )
            )
        else:
            found = "ausente" if provenance is None else repr(provenance)
            add(
                AuditCheck(
                    "provenance",
                    "PRISMA 27 / trAIce M2",
                    "FAIL",
                    f"Procedencia {found}: el manifiesto no declara `provenance: pipeline`. "
                    "Una corrida reconstruida, o generada antes de que el motor registrara "
                    "su procedencia, no es evidencia publicable: regenérala con `revisia run`.",
                )
            )
```

Añadir a la docstring del módulo, en la lista de PRISMA-trAIce, "procedencia de la corrida (pipeline vs reconstrucción)".

- [ ] **Step 9: Verificar**

Run: `uv run pytest -p no:cacheprovider -q` → PASS todo (incluido `test_audit_corrida_completa_es_publicable`, que ahora lleva `provenance: pipeline` por defecto).
Lint → limpio.

- [ ] **Step 10: Commit**

```bash
git add revisia/orchestration/pipeline.py revisia/orchestration/run_context.py revisia/audit.py tests/test_pipeline_fake.py tests/test_provenance.py tests/test_audit.py tests/test_cli_errores.py
git commit -m "fix(pipeline): un reporte rechazado no es completed; procedencia en manifiesto y auditor (C1, C3)" -m "run_pipeline devuelve el estado del gate final si no es approved (el CLI ya sale con 1 y no sedimenta en --brain). write_manifest escribe provenance: pipeline, no sobrescribible; revisia audit falla si falta o es otra cosa. Auditoría 2026-09-03, C1 y C3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Pista C · PR-C `fix/ola0-higiene`

### Task 5: Modelo por defecto vigente y lista de modelos retirados (C-1, C-2)

**Files:**
- Create: `revisia/llm/deprecations.py`
- Modify: `revisia/llm/providers/gemini.py` (docstring l.7-9; `DEFAULT_MODEL` l.27)
- Modify: `protocols/_TEMPLATE/protocol.yml` (l.64, 69, 99)
- Modify: `revisia/cli.py` (imports; helper `_today`, `_configured_models`; `_cmd_validate` l.48-72; `p_check --model` l.365-367)
- Modify: `tests/test_llm_registry.py:23-25`, `tests/test_provenance.py:17` (id del modelo)
- Test: `tests/test_deprecations.py` (nuevo), `tests/test_cli_validate.py` (nuevo)

**Interfaces:**
- Produces: `revisia.llm.deprecations.RETIRED_MODELS: dict[str, date]`; `Retirement` (dataclass `model: str`, `shutdown: date`, `is_past(today: date) -> bool`); `retirement_for(model: str) -> Retirement | None`; `revisia.cli._today() -> date` (inyectable en tests).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_deprecations.py`:

```python
"""Modelos retirados por su proveedor (auditoría 2026-09-03, C4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from revisia.config import load_protocol
from revisia.llm.deprecations import RETIRED_MODELS, Retirement, retirement_for
from revisia.llm.providers.gemini import DEFAULT_MODEL

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"


def test_gemini_2_0_flash_esta_retirado() -> None:
    r = retirement_for("gemini-2.0-flash")
    assert r == Retirement("gemini-2.0-flash", date(2026, 6, 1))
    assert r.is_past(date(2026, 6, 1))
    assert not r.is_past(date(2026, 5, 31))


def test_modelo_desconocido_no_esta_retirado() -> None:
    assert retirement_for("gemini-3.5-flash-lite") is None
    assert retirement_for("sonnet") is None


def test_default_gemini_no_esta_retirado() -> None:
    assert DEFAULT_MODEL == "gemini-3.5-flash-lite"
    assert retirement_for(DEFAULT_MODEL) is None


def test_plantilla_no_usa_modelos_retirados() -> None:
    protocol = load_protocol(TEMPLATE_DIR)
    assert all(retirement_for(cfg.model) is None for cfg in protocol.llm.values())


def test_lista_de_retirados_bien_formada() -> None:
    assert RETIRED_MODELS
    assert all(isinstance(d, date) for d in RETIRED_MODELS.values())
```

Crear `tests/test_cli_validate.py`:

```python
"""`revisia validate` detiene el quickstart ante un modelo retirado (C4, D7)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from revisia import cli

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"


def _protocolo_con_modelo(tmp_path: Path, model: str) -> Path:
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    for cfg in raw["llm"].values():
        cfg["model"] = model
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return proto


def test_validate_exits_2_on_retired_model(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = cli.main(["validate", str(_protocolo_con_modelo(tmp_path, "gemini-2.0-flash"))])
    err = capsys.readouterr().err
    assert rc == 2
    assert "gemini-2.0-flash" in err
    assert "2026-06-01" in err


def test_validate_avisa_retiro_futuro_sin_fallar(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 9, 25))
    rc = cli.main(["validate", str(_protocolo_con_modelo(tmp_path, "gemini-2.5-flash"))])
    assert rc == 0
    assert "2026-10-16" in capsys.readouterr().out


def test_validate_plantilla_pasa(capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["validate", str(TEMPLATE_DIR)]) == 0


def test_check_usa_el_modelo_por_defecto_vigente() -> None:
    from revisia.llm.providers.gemini import DEFAULT_MODEL

    args = cli.build_parser().parse_args(["check", "manuscrito.md"])
    assert args.model == DEFAULT_MODEL
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest tests/test_deprecations.py tests/test_cli_validate.py -p no:cacheprovider -q`
Expected: ERROR de colección en `test_deprecations.py` (`ModuleNotFoundError: revisia.llm.deprecations`); en `test_cli_validate.py` falla `exits_2` (rc 0) y `avisa_retiro_futuro` (`AttributeError: _today`).

- [ ] **Step 3: Crear `revisia/llm/deprecations.py`:**

```python
"""Modelos retirados por su proveedor.

El quickstart de v0.6.0 se rompió en silencio: el modelo por defecto
(``gemini-2.0-flash``) se apagó el 2026-06-01 y la primera llamada devolvía un
404 a mitad de corrida (auditoría 2026-09-03, C4). Esta tabla permite que
``revisia validate`` lo detecte ANTES de gastar una corrida.

Se mantiene a mano: la fuente es la documentación oficial de cada proveedor.
Gemini: https://ai.google.dev/gemini-api/docs/deprecations y
https://ai.google.dev/gemini-api/docs/changelog (consultadas 2026-09-08).
La clave es el id exacto que se escribe en ``protocol.yml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

RETIRED_MODELS: dict[str, date] = {
    "gemini-2.0-flash": date(2026, 6, 1),
    "gemini-2.0-flash-001": date(2026, 6, 1),
    "gemini-2.0-flash-lite": date(2026, 6, 1),
    "gemini-2.0-flash-lite-001": date(2026, 6, 1),
    "gemini-2.5-flash": date(2026, 10, 16),
    "gemini-2.5-flash-lite": date(2026, 10, 16),
    "gemini-2.5-pro": date(2026, 10, 16),
    "gemini-3.1-flash-lite-preview": date(2026, 5, 25),
}


@dataclass(frozen=True, slots=True)
class Retirement:
    """Retirada anunciada de un modelo."""

    model: str
    shutdown: date

    def is_past(self, today: date) -> bool:
        """``True`` si el modelo ya está apagado en ``today``."""
        return today >= self.shutdown


def retirement_for(model: str) -> Retirement | None:
    """Retirada conocida de ``model``, o ``None`` si no consta ninguna."""
    shutdown = RETIRED_MODELS.get(model)
    return None if shutdown is None else Retirement(model, shutdown)
```

- [ ] **Step 4: Default vigente.** En `revisia/llm/providers/gemini.py`, sustituir la línea `DEFAULT_MODEL = "gemini-2.0-flash"` por `DEFAULT_MODEL = "gemini-3.5-flash-lite"` y el párrafo de la docstring:

```
Proveedor por defecto de la plantilla (``gemini-2.0-flash``): tier gratis y sin
fricción para empezar. Cualquier investigador puede elegir otro proveedor en
``protocol.yml`` sin tocar nada del núcleo.
```

por:

```
Proveedor por defecto de la plantilla: tier gratis y sin fricción para empezar.
El id concreto vive solo en ``DEFAULT_MODEL`` (los ids caducan: ver
:mod:`revisia.llm.deprecations`). Cualquier investigador puede elegir otro
proveedor o modelo en ``protocol.yml`` sin tocar nada del núcleo.
```

En `protocols/_TEMPLATE/protocol.yml`, sustituir las tres apariciones de `gemini-2.0-flash` (l.64, 69 y la comentada l.99) por `gemini-3.5-flash-lite`. En `tests/test_llm_registry.py:23-25` y `tests/test_provenance.py:17`, sustituir `gemini-2.0-flash` por `gemini-3.5-flash-lite`.

Verificar: `grep -rn "gemini-2" revisia protocols/_TEMPLATE tests` → solo aparece en `revisia/llm/deprecations.py` y `tests/test_deprecations.py`/`tests/test_cli_validate.py`.

- [ ] **Step 5: `validate` y `check` en `revisia/cli.py`.** Añadir `from datetime import date` (junto al `from datetime import UTC, datetime` existente: `from datetime import UTC, date, datetime`), y a los imports del paquete:

```python
from revisia.llm.deprecations import retirement_for
from revisia.llm.providers.gemini import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
```

(importar `gemini` es barato: el SDK de Google solo se importa bajo `TYPE_CHECKING` y dentro de los métodos.) Antes de `_cmd_validate` añadir:

```python
def _today() -> date:
    """Fecha de hoy (función aparte para poder fijarla en los tests)."""
    return date.today()


def _configured_models(protocol) -> list[str]:
    """Ids de modelo de todas las etapas y miembros de ensemble del protocolo."""
    models = {cfg.model for cfg in protocol.llm.values()}
    models |= {cfg.model for members in protocol.ensemble_llm.values() for cfg in members}
    return sorted(models)
```

En `_cmd_validate`, sustituir el `return 0` final por:

```python
    # Modelos retirados (auditoría 2026-09-03, C4): el quickstart debe fallar
    # aquí con un mensaje, no con un 404 a mitad de corrida.
    rc = 0
    today = _today()
    for model in _configured_models(protocol):
        retirement = retirement_for(model)
        if retirement is None:
            continue
        fecha = retirement.shutdown.isoformat()
        if retirement.is_past(today):
            print(
                f"error: el modelo {model!r} fue retirado por su proveedor el {fecha}; "
                "las llamadas fallarán. Cámbialo en protocol.yml.",
                file=sys.stderr,
            )
            rc = 2
        else:
            print(f"  aviso: el modelo {model!r} se retira el {fecha}; planifica el cambio.")
    return rc
```

En el subparser `check`, sustituir

```python
    p_check.add_argument(
        "--model", default="gemini-2.0-flash", help="Modelo (default: gemini-2.0-flash)."
    )
```

por

```python
    p_check.add_argument(
        "--model",
        default=GEMINI_DEFAULT_MODEL,
        help=f"Modelo (default: {GEMINI_DEFAULT_MODEL}).",
    )
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider -q` → PASS todo.
Lint → limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/llm/deprecations.py revisia/llm/providers/gemini.py protocols/_TEMPLATE/protocol.yml revisia/cli.py tests/test_deprecations.py tests/test_cli_validate.py tests/test_llm_registry.py tests/test_provenance.py
git commit -m "fix(llm): modelo por defecto vigente y validate con modelos retirados (C4)" -m "gemini-2.0-flash se apagó el 2026-06-01: default a gemini-3.5-flash-lite (plantilla, proveedor y check). RETIRED_MODELS con fuente y fecha; revisia validate sale con 2 ante un modelo retirado y avisa de retiros futuros. Auditoría 2026-09-03, C4." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Empaquetado limpio (C-3)

**Files:**
- Modify: `pyproject.toml` (nueva sección tras `[tool.hatch.build.targets.wheel]`)
- Modify: `.gitignore`

**Interfaces:** ninguna de código.

- [ ] **Step 1: Reproducir el problema** (evidencia antes del arreglo):

Run:
```bash
OUT="$(mktemp -d)"; uv build --sdist -o "$OUT" -q && tar tzf "$OUT"/revisia-*.tar.gz | grep -E "runs/|\.superpowers|\.claude|\.coverage|__pycache__|/dist/" | head
```
Expected: lista entradas sospechosas (o ninguna si esta máquina no las tiene; anotar el resultado en el commit).

- [ ] **Step 2: Implementar.** En `pyproject.toml`, tras el bloque `[tool.hatch.build.targets.wheel]`, añadir:

```toml
# El sdist solo lleva lo que se versiona y sirve para reconstruir el paquete:
# nada de corridas (`runs/`), ficheros de proceso (`.superpowers/`, `.claude/`),
# cobertura ni un `dist/` previo (auditoría 2026-09-03, A14).
[tool.hatch.build.targets.sdist]
only-include = [
    "revisia",
    "docs",
    "protocols/_TEMPLATE",
    "tests",
    "examples",
    "assets",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "NOTICE",
    "CITATION.cff",
    "pyproject.toml",
    "uv.lock",
]
```

En `.gitignore`, tras el bloque `# Cobertura local (pytest-cov)`, añadir:

```gitignore

# Artefactos de proceso de agentes (planes/borradores locales): no son del repo.
.superpowers/
```

y sobre las líneas `!runs/*/manifest.yml` / `!runs/*/deliverable/`, añadir el comentario:

```gitignore
# OJO: estas negaciones son inoperantes porque `runs/*/` excluye el directorio
# padre (git no re-incluye hijos de un directorio ignorado). Hoy ninguna corrida
# se versiona. Decidir qué se versiona de una corrida es trabajo de la Ola 1.
```

- [ ] **Step 3: Verificar**

Run:
```bash
OUT="$(mktemp -d)"; uv build --sdist -o "$OUT" -q && T="$(ls "$OUT"/revisia-*.tar.gz)"; echo "sospechosos:"; tar tzf "$T" | grep -E "runs/|\.superpowers|\.claude|\.coverage|__pycache__|/dist/"; echo "esenciales:"; tar tzf "$T" | grep -cE "revisia/cli.py|protocols/_TEMPLATE/protocol.yml|README.md|uv.lock"
```
Expected: ninguna línea bajo "sospechosos"; "esenciales" ≥ 4.

Run: `uv build --wheel -o "$(mktemp -d)" -q` → sin error.
Run: `uv run pytest -p no:cacheprovider -q` → PASS.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .gitignore
git commit -m "chore(build): sdist con only-include y .superpowers/ ignorado (A14)" -m "El sdist ya no arrastra runs/, ficheros de proceso, cobertura ni dist/ previo. Se documenta que las negaciones de runs/ en .gitignore son inoperantes (Ola 1). Auditoría 2026-09-03, A14." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Métricas honestas (C-4) y corrección de continuidad solo con ceros (C-5)

**Files:**
- Modify: `revisia/metrics.py` (`ScreeningMetrics` l.28-41; `mcc` l.60-63; `wmcc` l.66-74; `cohen_kappa` l.77-85; nuevo `fmt_metric`)
- Modify: `revisia/extraction_agreement.py:34,88`
- Modify: `revisia/exports/methods.py:48-49,100`
- Modify: `revisia/exports/checklist.py:241-242`
- Modify: `revisia/cli.py:167`
- Modify: `revisia/audit.py` (check `gold`, l.249-264)
- Modify: `revisia/schemas/effects.py` (`_log_or` l.63-73)
- Test: `tests/test_metrics.py`, `tests/test_meta_analysis.py`, `tests/test_coverage_gaps.py`, `tests/test_audit.py`

**Interfaces:**
- Produces: `revisia.metrics.fmt_metric(value: float | None, spec: str = ".3f") -> str`; `mcc/wmcc/cohen_kappa -> float | None`; `ScreeningMetrics.mcc/wmcc/cohen_kappa: float | None = None`; `ExtractionAgreement.presence_kappa: float | None = None`.

- [ ] **Step 1: Tests que fallan para C-4** — añadir a `tests/test_metrics.py` (importar también `fmt_metric` desde `revisia.metrics`):

```python
def test_mcc_and_kappa_none_when_undefined() -> None:
    # Una sola clase en gold y predicción: MCC y κ no están definidos (antes: 0.0,
    # que se leía como "acuerdo nulo" y el auditor daba PASS · auditoría A11).
    assert mcc(4, 0, 0, 0) is None
    assert wmcc(4, 0, 0, 0) is None
    assert cohen_kappa([True] * 4, [True] * 4) is None
    assert cohen_kappa([], []) is None


def test_compute_screening_metrics_persiste_none() -> None:
    decisions = [ScreeningDecision(record_id=r, ensemble_label="include") for r in "abc"]
    m = compute_screening_metrics(decisions, {"a": True, "b": True, "c": True})
    assert m.mcc is None and m.wmcc is None and m.cohen_kappa is None
    assert m.model_dump()["cohen_kappa"] is None  # metrics.json persistirá null


def test_fmt_metric() -> None:
    assert fmt_metric(None) == "no calculable"
    assert fmt_metric(0.12345) == "0.123"
    assert fmt_metric(0.5, ".2f") == "0.50"
```

Añadir a `tests/test_coverage_gaps.py`, tras `test_acuerdo_extraccion_valor_y_kappa`:

```python
def test_acuerdo_extraccion_sin_pares_kappa_none() -> None:
    agr = compute_extraction_agreement({}, {})
    assert agr.presence_kappa is None
    assert agr.value_agreement is None


def test_acuerdo_extraccion_kappa_indefinido_no_revienta() -> None:
    # Todos los campos presentes en ambos extractores: κ de presencia indefinido.
    # Antes cohen_kappa devolvía 0.0; con None, el modelo debe aceptarlo.
    def ext(rid: str) -> ExtractionRecord:
        return ExtractionRecord(study_id=rid, fields={"d": ExtractionField(value="RCT")})

    agr = compute_extraction_agreement({"a": ext("a")}, {"a": ext("a")})
    assert agr.presence_kappa is None
```

Añadir al final de `tests/test_audit.py`:

```python
def test_audit_gold_kappa_no_calculable_advierte(tmp_path) -> None:
    run = _make_run(tmp_path)
    (run / "03_screening" / "metrics.json").write_text(
        json.dumps({"recall": 1.0, "cohen_kappa": None}), encoding="utf-8"
    )
    report = run_audit(run)
    gold = next(c for c in report.checks if c.check_id == "gold")
    assert gold.status == "WARN"  # antes: PASS con κ inventado
    assert "no calculable" in gold.detail
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest tests/test_metrics.py tests/test_coverage_gaps.py tests/test_audit.py -p no:cacheprovider -q`
Expected: ERROR de import (`fmt_metric`) en `test_metrics.py`; FAIL en `..._kappa_indefinido_no_revienta` (`0.0 is None`), `..._sin_pares_kappa_none` y `test_audit_gold_kappa_no_calculable_advierte`.

- [ ] **Step 3: Implementar C-4 en `revisia/metrics.py`.** En `ScreeningMetrics`, sustituir `mcc: float = 0.0`, `wmcc: float = 0.0` y `cohen_kappa: float = 0.0` por `float | None = None` (conservar `wmcc_fn_weight: float = 10.0`) y añadir a la docstring de la clase: "``None`` = indefinida (denominador 0: el gold no tiene ambas clases); nunca ``0.0`` inventado (auditoría 2026-09-03, A11)." Sustituir las tres funciones y añadir `fmt_metric`:

```python
def fmt_metric(value: float | None, spec: str = ".3f") -> str:
    """Formatea una métrica; ``None`` (indefinida) se muestra como ``no calculable``."""
    return "no calculable" if value is None else format(value, spec)


def mcc(tp: int, fp: int, fn: int, tn: int) -> float | None:
    """Coeficiente de correlación de Matthews (``None`` si el denominador es 0)."""
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return ((tp * tn) - (fp * fn)) / denom if denom else None


def wmcc(tp: int, fp: int, fn: int, tn: int, *, fn_weight: float = 10.0) -> float | None:
    """MCC con el falso negativo ponderado por ``fn_weight`` (coste FN ≫ FP).

    Variante pragmática (no estandarizada): se reemplaza ``fn`` por
    ``fn_weight * fn`` para penalizar perder evidencia relevante. ``None`` si
    el denominador es 0.
    """
    fnw = fn_weight * fn
    denom = math.sqrt((tp + fp) * (tp + fnw) * (tn + fp) * (tn + fnw))
    return ((tp * tn) - (fp * fnw)) / denom if denom else None


def cohen_kappa(pred: list[bool], gold: list[bool]) -> float | None:
    """Cohen's kappa entre dos clasificaciones binarias (``None`` si indefinido)."""
    tp, fp, fn, tn = confusion(pred, gold)
    n = tp + fp + fn + tn
    if n == 0:
        return None
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    return (po - pe) / (1 - pe) if (1 - pe) else None
```

- [ ] **Step 4: Consumidores.**

`revisia/extraction_agreement.py`: `presence_kappa: float = 0.0` → `presence_kappa: float | None = None`; `presence_kappa=cohen_kappa(present_a, present_b) if n_pairs else 0.0,` → `presence_kappa=cohen_kappa(present_a, present_b) if n_pairs else None,`.

`revisia/exports/methods.py`: añadir `from revisia.metrics import fmt_metric` (import en tiempo de ejecución, fuera del bloque `TYPE_CHECKING`); `f"Cohen's kappa humano-IA = {metrics.cohen_kappa:.3f}"` → `f"Cohen's kappa humano-IA = {fmt_metric(metrics.cohen_kappa)}"`; `f"kappa de presencia={ea.presence_kappa:.3f}."` → `f"kappa de presencia={fmt_metric(ea.presence_kappa)}."`.

`revisia/exports/checklist.py`: añadir `from revisia.metrics import fmt_metric`; sustituir las dos líneas:

```python
            f"- MCC: {fmt_metric(metrics.mcc)} · "
            f"WMCC (w={metrics.wmcc_fn_weight:g}): {fmt_metric(metrics.wmcc)}",
            f"- Cohen's kappa humano-IA: {fmt_metric(metrics.cohen_kappa)}",
```

`revisia/cli.py` (resumen de `_cmd_run`): añadir `from revisia.metrics import fmt_metric` a los imports del paquete y sustituir la línea de MCC por:

```python
            f"· MCC={fmt_metric(m.mcc, '.2f')} · WMCC={fmt_metric(m.wmcc, '.2f')} "
            f"· kappa={fmt_metric(m.cohen_kappa, '.2f')}"
```

`revisia/audit.py`, check `gold`: sustituir el `add(AuditCheck("gold", ..., "PASS", ...))` del bloque `try` por:

```python
            if kappa is None:
                add(
                    AuditCheck(
                        "gold",
                        "trAIce M9/R2",
                        "WARN",
                        f"Métricas vs gold humano: recall={recall} · kappa no calculable "
                        "(denominador 0: el gold no tiene ambas clases). Amplía el gold con "
                        "registros relevantes e irrelevantes.",
                    )
                )
            else:
                add(
                    AuditCheck(
                        "gold",
                        "trAIce M9/R2",
                        "PASS",
                        f"Métricas vs gold humano: recall={recall} · kappa={kappa} "
                        "(accuracy omitida a propósito).",
                    )
                )
```

- [ ] **Step 5: Verificar C-4**

Run: `uv run pytest -p no:cacheprovider -q` → PASS todo. Además: `grep -rn "\.mcc:\|\.wmcc:\|cohen_kappa:\.\|presence_kappa:\." revisia` → sin resultados (ningún formateo directo de un valor que puede ser `None`).

- [ ] **Step 6: Tests para C-5** — en `tests/test_meta_analysis.py`, sustituir `test_log_or_desde_2x2` completo por:

```python
def test_log_or_desde_2x2_sin_ceros_no_corrige() -> None:
    # e1=10/n1=100, e0=20/n0=100: sin celdas en cero no hay corrección de
    # continuidad (Sweeting 2004; auditoría 2026-09-03, M10). Antes: -0.786.
    eff = EffectInput(study_id="x", e1=10, n1=100, e0=20, n0=100)
    yi, vi = eff.to_yi_vi("logOR")
    assert yi == pytest.approx(-0.810930, abs=1e-6)
    assert vi == pytest.approx(0.173611, abs=1e-6)


def test_log_or_con_celda_cero_aplica_haldane_anscombe() -> None:
    # e1=0: se suma 0.5 a las cuatro celdas (a=.5, b=10.5, c=5.5, d=5.5).
    eff = EffectInput(study_id="z", e1=0, n1=10, e0=5, n0=10)
    yi, vi = eff.to_yi_vi("logOR")
    assert yi == pytest.approx(-3.044522, abs=1e-6)
    assert vi == pytest.approx(2.458874, abs=1e-6)
```

- [ ] **Step 7: Verificar que fallan**

Run: `uv run pytest tests/test_meta_analysis.py -p no:cacheprovider -q`
Expected: FAIL `test_log_or_desde_2x2_sin_ceros_no_corrige` (yi ≈ -0.786); el de celda cero pasa.

- [ ] **Step 8: Implementar C-5** — sustituir `_log_or` en `revisia/schemas/effects.py`:

```python
    def _log_or(self) -> tuple[float, float]:
        if None in (self.e1, self.n1, self.e0, self.n0):
            raise ValueError(f"{self.study_id}: faltan e1/n1/e0/n0 para logOR.")
        a = self.e1
        b = self.n1 - self.e1
        c = self.e0
        d = self.n0 - self.e0
        # Corrección de continuidad 0.5 (Haldane-Anscombe) SOLO si alguna celda es
        # 0: aplicarla siempre sesga hacia el nulo (+0,017 medido en la auditoría
        # 2026-09-03, M10; Sweeting, Sutton y Lambert 2004).
        if 0 in (a, b, c, d):
            a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
        yi = math.log((a * d) / (b * c))
        vi = 1 / a + 1 / b + 1 / c + 1 / d
        return yi, vi
```

- [ ] **Step 9: Verificar**

Run: `uv run pytest -p no:cacheprovider -q` → PASS todo.
Lint → limpio.

- [ ] **Step 10: Commit** (dos commits, uno por hallazgo):

```bash
git add revisia/metrics.py revisia/extraction_agreement.py revisia/exports/methods.py revisia/exports/checklist.py revisia/cli.py revisia/audit.py tests/test_metrics.py tests/test_coverage_gaps.py tests/test_audit.py
git commit -m "fix(metrics): MCC, WMCC y kappa indefinidos son None, no 0.0 (A11)" -m "Las métricas indefinidas se persisten como null y se muestran como 'no calculable'; el auditor da WARN (no PASS) cuando kappa no es calculable. presence_kappa de la doble extracción también admite None (antes Pydantic lo habría rechazado). Cambio de tipo público. Auditoría 2026-09-03, A11." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add revisia/schemas/effects.py tests/test_meta_analysis.py
git commit -m "fix(meta): corrección de continuidad 0.5 solo con celdas en cero (M10)" -m "Aplicarla siempre sesgaba el logOR hacia el nulo. Se actualiza la expectativa del test 2x2 sin ceros (-0.786 -> -0.811) y se añade el caso con celda cero. Auditoría 2026-09-03, M10." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Integración y cierre (controlador)

### Task 8: Apilar las ramas, documentar y verificar

- [ ] **Step 1: Apilar.** `git -C C:\revisia-wt\b rebase fix/ola0-seguridad-exportador`; `git -C C:\revisia-wt\c rebase fix/ola0-honestidad-pipeline`. Conflicto esperado solo al final de `tests/test_audit.py` (conservar ambos bloques). Tras cada rebase: suite completa en verde.
- [ ] **Step 2: CHANGELOG.** Un commit por rama bajo `## [Unreleased]`: PR-A en `### Security`; PR-B en `### Fixed`/`### Changed`; PR-C en `### Fixed`/`### Changed` con el cambio de tipo de `mcc`/`cohen_kappa`/`presence_kappa` marcado como **incompatible**, el nuevo default de Gemini y `nh3` como dependencia del núcleo. Re-apilar tras cada commit.
- [ ] **Step 3: Corrida fundacional.** En `C:\revisia\runs\prisma-ia-origen-20260706-080747\manifest.yml` (no versionado), insertar tras la línea `timestamp:` la línea `provenance: reconstruction` con un comentario YAML que cite la auditoría. Verificar: `uv run revisia audit runs/prisma-ia-origen-20260706-080747` → veredicto NO publicable con `provenance FAIL`.
- [ ] **Step 4: Matriz completa** sobre la punta de la pila (rama C): `uv run pytest`; la misma suite en 3.11 y 3.12 con venv desechable (spec §7); lint completo; `uv lock --check`; comprobación del sdist de la Tarea 6.
- [ ] **Step 5: Spec al día.** Anotar en el spec cualquier desviación del plan que haya resultado de la implementación.

### Task 9: Auditoría final

- [ ] **Step 1:** Revisión de código de la pila completa (`main..fix/ola0-higiene`) a esfuerzo alto: corrección, seguridad (¿se puede saltar alguna guardia?), consistencia de mensajes, tests que realmente reproducen la evidencia de la auditoría.
- [ ] **Step 2:** Corregir lo confirmado con TDD en la rama que corresponda; re-apilar; repetir la matriz de la Tarea 8 Step 4.
- [ ] **Step 3:** Publicar: push de las tres ramas y tres PRs apiladas (A→`main`, B→A, C→B), cada una con resumen, hallazgos cerrados, evidencia de verificación y la línea de atribución. El merge queda en manos del arquitecto.
