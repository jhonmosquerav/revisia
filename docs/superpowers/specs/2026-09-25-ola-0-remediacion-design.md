# Ola 0 del plan de remediación · diseño

- **Fecha:** 2026-09-25
- **Origen:** `docs/auditoria/2026-09-03-auditoria-completa.md` §8, "Ola 0 · esta semana, sin cambiar el diseño".
- **Base:** `main` @ `fd8dd64` (v0.6.0; 190 tests en verde medidos el 2026-09-25).
- **Alcance declarado por la auditoría:** cierra C4, A1, A2, A3, M2 y la mitad de C1.

## 1. Por qué esta ola existe

La auditoría concluye que RevisIA es *apto como motor de investigación y
prototipo, no apto todavía para sustentar una revisión sistemática publicable*.
La Ola 0 es el subconjunto de remediaciones que **no toca el diseño**: son
correcciones locales, cada una con su evidencia reproducida en la auditoría.
Las olas 1 y 2 (HITL por registro, auditor exigente, grounding real) dependen de
que esta base esté limpia.

## 2. Estado de partida verificado

Dos de los ocho ítems ya están cerrados o casi, y conviene no volver a hacerlos:

| Ítem | Estado real en `main` |
|---|---|
| 4 · redactar `api_key` y no tragar `ValidationError` | **Cerrado** en `261b82c`. `pipeline.py:122` ya comprueba `db_key(db) in BACKENDS` antes de despachar y `pipeline.py:132` redacta el error con `_http.redact_secrets`. Sin trabajo pendiente. |
| 7 · re-etiquetar la corrida fundacional | **Parcial.** `docs/benchmark-cribado.md` lleva el aviso de procedencia (`91954c2`). Falta la marca legible por el motor: `revisia audit` sigue declarando APTA la corrida reconstruida. |

Un hallazgo que cambia el alcance del ítem 7: **`runs/` y `protocols/<slug>/`
no están versionados** (`git ls-files runs` → 0 ficheros). La corrida
`prisma-ia-origen-20260706-080747` existe solo en la máquina del autor. Lo que
está en el repositorio son las referencias a ella y lo que el sdist arrastraba
por las negaciones inoperantes del `.gitignore` (M23), que el ítem 6 corta.

## 3. Decisiones tomadas

| # | Decisión | Razón |
|---|---|---|
| D1 | Entrega en **tres PRs temáticas secuenciales** sobre `main` | El ítem 5 es el único que cambia comportamiento observable y merece revisión aislada; mezclarlo con empaquetado hace que un rollback arrastre lo que no debe. Secuenciales y no en paralelo porque PR-B y PR-C tocan ambas `audit.py`. |
| D2 | El validador de `autonomy` es **error duro al cargar** | C1 es exactamente que un `A3` apaga el HITL en silencio; un aviso por stdout es el mismo fallo con más letras (y M8 documenta que stdout se rompe en Windows redirigido). Es además el principio no negociable de `AGENTS.md`: `screening`, `extraccion` y `rob` nunca superan A1. |
| D3 | Modelo por defecto: **`gemini-3.5-flash-lite`** | `gemini-2.0-flash` se apagó el 2026-06-01 y `gemini-2.5-flash` se retira el 2026-10-16 (fuentes: changelog y página de deprecations de la Gemini API, consultadas 2026-09-08). El default sirve al quickstart, no al juicio metodológico: una corrida de cribado son ~1.400 llamadas, y quien publique elige modelo en su `protocol.yml`. |
| D4 | Saneado del HTML con **`nh3` en el núcleo**, sobre el HTML ya convertido | El exportador inyecta HTML propio (`figure` con la imagen en base64, tablas del flujo PRISMA) *antes* de convertir; escapar el markdown de entrada escaparía también lo nuestro. Sanear la salida con allowlist evita reordenar `_embed_md_images` y `replace_mermaid_blocks`. `nh3` es un wheel precompilado sin dependencias transitivas. |
| D5 | Ítem 7: **marca en el manifiesto + guardia en `audit.py`** | Es la única variante que impide que el auditor vuelva a decir APTA sobre el artefacto reconstruido: el aviso en Markdown no lo lee el motor. ~30 líneas, sin invadir el rework del auditor de la Ola 1. |
| D6 | MCC/WMCC/κ indefinidos → **`float \| None`** en funciones y esquema | Mientras `0.0` sea un valor válido, cualquier umbral `kappa_min` se compara contra un número inventado (A11: hoy el auditor da PASS a `gold` con κ=0.0). Propuesta de Claude aceptada con el diseño; revocable. |
| D7 | Un modelo retirado hace que `revisia validate` **salga con `rc = 2`** | El ítem 1 existe porque el quickstart está roto; una advertencia que no cambia el código de salida no lo detiene. Es un cambio de tres líneas y no adelanta el rework de `validate` de la Ola 1 (M6, fail-fast de proveedores), que sigue fuera de alcance. |

## 4. PR-A · `fix/ola0-seguridad-exportador`

Cierra **A1** (inyección de comandos en Windows), **A2** (lectura arbitraria de
ficheros en el export) y la parte de **M1** que la Ola 0 puede cubrir.

### A-1 · Validación del nombre de modelo (`llm/registry.py`)

`ProviderConfig.model` pasa a `Field(pattern=r"^[A-Za-z0-9._:/@+-]{1,128}$")`.
Frente al patrón de la auditoría se añaden `@` y `+` (ids estilo Vertex como
`claude-x@20260101`) y se sube el tope a 128 (ids de OpenRouter/HF con
organización y sufijo): ninguno de los dos es metacarácter de `cmd.exe`, y se
verificó con `grep` que todos los ids usados hoy en tests, ejemplos y plantilla
cumplen el patrón. Un
`protocol.yml` con un `model` que contenga comillas, `&` o `|` deja de cargar
con `ValidationError`. Es la barrera primaria de A1 y protege a todos los
proveedores, no solo a `claude_code`.

### A-2 · Guardia fail-closed del shim de Windows (`llm/providers/claude_code.py`)

`_resolve_cli` devuelve hoy la ruta que da `shutil.which`, que en Windows es
`claude.CMD`. `CreateProcess` sobre un `.CMD`/`.BAT` delega en `cmd.exe`, que
**vuelve a parsear** la línea de comandos (BatBadBut): los argumentos que
`subprocess` ya citó se re-interpretan y `&`, `|`, `<`, `>`, `^`, `%`, `!` y
`"` recuperan su significado.

**Rechazar, no escapar.** La primera versión de este diseño proponía escapar
los argumentos con las reglas de `cmd.exe`. Se descarta: `%VAR%` no se puede
neutralizar dentro de comillas, `!` depende de si la expansión retardada está
activa, y un escapador de `cmd.exe` es precisamente el tipo de código que
BatBadBut demostró que casi nadie acierta. En su lugar, cuando el ejecutable
resuelto tiene extensión `.cmd` o `.bat`, `_command` comprueba que **ningún
argumento** contiene esos metacaracteres ni saltos de línea, y si alguno los
contiene lanza `RuntimeError` antes de crear el proceso, con un mensaje que
explica el porqué y sugiere instalar el binario nativo de Claude Code.

Es viable porque se verificó que todos los argumentos actuales son seguros: los
flags son constantes, `model` queda acotado por A-1, y los siete `_SYSTEM` que
viajan en `--append-system-prompt` (`agents/{screening,screening_ft,extraccion,
rob,reporte}.py`, `check.py`, `rag/grounding.py`) no contienen ningún
metacarácter. El prompt, que sí trae texto no confiable (abstracts), viaja por
stdin y no pasa por `cmd.exe`. Con el binario nativo (`claude.exe`) la guardia
no se activa: `CreateProcess` no re-parsea.

Alcance explícito: no se cambia el transporte (sigue siendo `subprocess` con
lista de argumentos, sin `shell=True`) ni se tocan los flags de `claude -p`
(A10 es Ola 2).

### A-3 · Confinamiento de las imágenes embebidas (`exports/document.py`)

`_embed_md_images` acepta hoy cualquier ruta relativa: una referencia
`![x](../../.env)` se embebe en el HTML como `data:` y el secreto viaja en el
entregable. Pasa a exigir, en este orden (helper `_resolve_inside`, compartido
con `_figuras_meta`):

0. Ninguna ancla: `PureWindowsPath(ref).anchor` y `PurePosixPath(ref).anchor`
   vacíos. Se comprueba **antes** de tocar el sistema de ficheros: en Windows,
   `resolve()` sobre `//host/share/x.png` abre una conexión SMB al host que
   elija el texto (fuga de hash NTLM). La primera versión del plan resolvía
   primero; lo detectó la revisión de la Tarea 2 (ver §10).
1. `target.resolve().is_relative_to(base_dir.resolve())` — nada fuera de
   `deliverable/`, con symlinks resueltos.
2. `target.suffix.lower() in _MIME` — solo extensiones de imagen declaradas.

Lo que no cumple se degrada a su texto alternativo, como hoy hacen las
referencias externas y rotas.

### A-4 · Saneado del HTML convertido (`exports/document.py`)

**Un solo punto de estrangulamiento: `_md_to_html`.** Todo el texto no
confiable del entregable (el `documento.md` que redacta el LLM y los anexos
`.md`) entra al HTML por esa función; lo que el exportador genera él mismo
(`_portada`, que ya escapa con `html.escape`; `_figuras_meta`; el anexo BibTeX,
también escapado; `_wrap_html` con su `<style>`) no pasa por ella y no se
sanea. `_md_to_html` pasa a devolver `nh3.clean(markdown(...), ...)` con:

- **Etiquetas:** las que emite `markdown` con `tables` y `fenced_code`
  (encabezados, párrafos, listas, énfasis, `code`/`pre`, `blockquote`, `hr`,
  `br`, tablas completas, `a`), más `figure`, `figcaption` e `img`.
- **`clean_content_tags`:** `script` y `style` se eliminan con su contenido,
  no solo la etiqueta.
- **Atributos:** `alt` y `src` en `img`; `href` y `title` en `a`; `class` en
  `code` (el `language-x` de los bloques de código); `style` en `th`/`td`.
  Ningún `on*`.
- **`filter_style_properties={"text-align"}`:** la extensión `tables` de
  `markdown` alinea columnas con `style="text-align: …"`; se conserva eso y
  nada más (un `background: url(http://…)` en `style` sería otra fuga de red).
- **`attribute_filter`:** el `src` de `img` solo sobrevive si empieza por
  `data:image/`; el `href` de `a` se descarta si empieza por `data:` o
  `javascript:`.
- **`url_schemes`:** `{"http", "https", "mailto", "data"}`; el filtro anterior
  restringe `data:` a imágenes.

Esto tumba `<script>`, los manejadores `onerror=` y las imágenes remotas (fuga
de red al abrir el entregable). El `figure` que inyecta `_embed_md_images`
viaja dentro del markdown y **sí** pasa por el saneado: sobrevive porque su
`img` lleva `src` `data:image/…` y `alt`, ambos permitidos. Nota: `.svg` sigue
en `_MIME`; dentro de una imagen con `src` `data:` el navegador no ejecuta los
scripts del SVG, así que no se retira. API verificada contra `nh3 0.3.7`
(`filter_style_properties` y `attribute_filter` existen en esa versión).

### A-5 · `url_fetcher` de WeasyPrint (`exports/document.py`)

`HTML(string=…)` usa hoy el fetcher por defecto, que resuelve `file://` y
`http://`. Se le pasa `url_fetcher=URLFetcher(allowed_protocols={"data"})`:
WeasyPrint descarta cualquier otro esquema antes de abrirlo. Cierra la mitad
PDF de M1, que la auditoría solo pudo reproducir en HTML (WeasyPrint no estaba
instalado).

WeasyPrint 70 cambió el contrato: `url_fetcher` ya no es un *callable* sino una
instancia de `weasyprint.URLFetcher` (verificado leyendo `weasyprint/urls.py`
del wheel 70.0). Por eso el extra `pdf` sube a `weasyprint>=70`; con el
suelo actual (`>=63`) el mismo código no funcionaría en todas las versiones
admitidas. El test no necesita WeasyPrint instalado: sustituye el módulo en
`sys.modules` y comprueba qué fetcher recibe `HTML`.

### A-6 · `pyproject.toml`

`nh3>=0.3` entra en `dependencies` (la API de A-4 se verificó en 0.3.7), el
extra `pdf` sube a `weasyprint>=70` (A-5) y se regenera `uv.lock`. El núcleo deja de ser pura-Python; se documenta en el
comentario del bloque, junto al de `markdown`.

## 5. PR-B · `fix/ola0-honestidad-pipeline`

Cierra la mitad de **C1** que no exige rediseño y la parte de **C3** relativa al
auditor.

### B-1 · Validador de autonomía (`config.py`)

`@field_validator("autonomy")` sobre `ReviewProtocol`:

- Toda clave debe ser una etapa de `STAGES`; todo valor, uno de `A0`–`A3`.
- `screening_ta`, `screening_ft`, `extraccion` y `rob` no admiten `A2` ni `A3`.

El error cita la regla de `AGENTS.md` y la etapa infractora. Protocolos
existentes con `A3` en etapas de juicio dejan de cargar — hoy solo existe
`protocols/_TEMPLATE`, así que el coste real es nulo.

### B-2 · `decision.yml` validado (`orchestration/hitl.py`)

Modelo Pydantic `HumanDecision`:

- `approved: bool` en modo estricto — la cadena `"false"` deja de aprobar.
- `actor: str`, por defecto `human:desconocido`.
- `reason: str | None`.

`_read_decision` deja de devolver un `dict` crudo:

- YAML malformado o con raíz que no sea mapa → `DecisionFileError` (subclase
  de `ValueError`) con mensaje accionable (ruta del fichero y qué se esperaba).
- En el CLI, `main()` convierte `DecisionFileError` y la `ValidationError` de
  un `protocol.yml` inválido en `error: …` por stderr y `rc = 2`, sin
  traceback. Solo para `validate` y `run`, y solo esas dos excepciones: un
  error inesperado del motor sigue mostrando su traceback.
- Los campos desconocidos se conservan en `detail` del ledger, como hoy.
- `approved` es obligatorio: un `decision.yml` vacío deja de leerse como
  rechazo de `human:desconocido` (hallazgo bajo de la auditoría) y pasa a ser
  el mismo `ValueError` accionable. `approved` usa `StrictBool`; el resto del
  modelo admite campos extra (`extra="allow"`).

Cierra tres hallazgos bajos y el vector en que `bool("false")` es verdadero.

### B-3 · El rechazo final es un rechazo (`orchestration/pipeline.py`)

La guarda `if final_gate.status == "paused"` pasa a
`if final_gate.status != "approved"`, devolviendo el estado del gate.
Consecuencias que se verifican con tests:

- Un `reporte/decision.yml` con `approved: false` produce `status: rejected`,
  no `completed`.
- El CLI no necesita cambios: `cli.py:169` ya devuelve `1` para todo estado
  que no sea `completed` ni `paused`, y `cli.py:133-146` solo sedimenta en
  `--brain` cuando el estado es `completed`. Bastaba con que el pipeline dejara
  de mentir; el test lo comprueba a través del CLI (rc 1, cerebro vacío).
- El manifiesto se sigue escribiendo antes de la guarda: una revisión
  rechazada deja rastro en disco, como hoy una pausada.

### B-4 · Procedencia en el manifiesto y guardia en el auditor

- `RunContext.write_manifest` escribe `provenance: pipeline` justo después de
  `timestamp`. La clave no se puede sobrescribir desde `extra`: se aplica
  después del desempaquetado.
- `audit.py` gana un check `provenance` (ítem `PRISMA 27 / trAIce M2`), justo
  después del de `manifest`: **FAIL** si el manifiesto no declara
  `provenance` o declara algo distinto de `pipeline`, con el valor encontrado
  en el detalle. Si el manifiesto falta, no se añade un segundo FAIL (el de
  `manifest` ya lo cubre). Como `publishable` es `n_fail == 0`, una corrida
  reconstruida deja de ser publicable.
- El fixture de `tests/test_audit.py` (el manifiesto de
  `test_audit_corrida_completa_es_publicable`) gana `provenance: pipeline`:
  sin eso el test que hoy pasa fallaría, y es la señal correcta.
- El `manifest.yml` local de `runs/prisma-ia-origen-20260706-080747` se marca a
  mano con `provenance: reconstruction`. No se versiona (no está en git); queda
  registrado aquí y en el CHANGELOG para que la marca sobreviva a la memoria.

Fuera de alcance: validar esquemas, artefactos por etapa, aritmética de
`counts`, plausibilidad temporal y umbrales. Todo eso es la Ola 1.

## 6. PR-C · `fix/ola0-higiene`

Cierra **C4**, **A14** y dos hallazgos bajos de estadística.

### C-1 · Modelo por defecto vigente

- `gemini.DEFAULT_MODEL = "gemini-3.5-flash-lite"`.
- El docstring del módulo deja de nombrar un id concreto (la auditoría lo pide
  explícitamente: "no fijar el modelo en docstrings").
- `protocols/_TEMPLATE/protocol.yml` (líneas 64, 69, 99), y el default de
  `--model` en `cli.py:366` (subcomando `check`, que pasa a leer
  `gemini.DEFAULT_MODEL` en vez de repetir el literal) al día. `README.md` no nombra
  ningún id de modelo (la auditoría citaba `README.md:84`, que hoy es la tabla
  de principios): no se toca.
  Inventario hecho con `grep -rn gemini-2`; los tests que usan
  `gemini-2.0-flash` como cadena arbitraria (`test_llm_registry.py:23`,
  `test_provenance.py:17`) pasan al id nuevo para no normalizar un modelo
  retirado en la suite.

### C-2 · Lista de modelos retirados

`revisia/llm/deprecations.py` con `RETIRED_MODELS: dict[str, date]` (id →
fecha de apagado), `Retirement` y `retirement_for(model)`, poblada con lo verificado el 2026-09-08:

| Modelo | Apagado |
|---|---|
| `gemini-2.0-flash`, `gemini-2.0-flash-001` | 2026-06-01 |
| `gemini-2.0-flash-lite`, `gemini-2.0-flash-lite-001` | 2026-06-01 |
| `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-lite` | 2026-10-16 |
| `gemini-3.1-flash-lite-preview` | 2026-05-25 |

`_cmd_validate` recorre los proveedores del protocolo, imprime una línea de
error por modelo retirado (con la fecha) y devuelve `2`. Un modelo cuya fecha de
retirada aún no ha llegado se imprime como advertencia con la fecha, sin cambiar
el código de salida.

### C-3 · Empaquetado

- `[tool.hatch.build.targets.sdist]` con `only-include = ["revisia", "docs",
  "protocols/_TEMPLATE", "tests", "examples", "assets", "README.md",
  "CHANGELOG.md", "LICENSE", "NOTICE", "CITATION.cff", "pyproject.toml",
  "uv.lock"]` más los ficheros raíz que enlaza el README (`.env.example`,
  `AGENTS.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`,
  `RELEASING.md`; ver §10 V9). Fuera quedan `runs/`, `.superpowers/`, `.claude/`, `.coverage`,
  `__pycache__` y el `dist/` ya construido. Criterio de aceptación: `tar tzf`
  del sdist reconstruido no lista ninguna ruta con `runs/`, `.superpowers`,
  `.claude`, `.coverage`, `__pycache__` ni `dist/`.
- `.gitignore`: añadir `.superpowers/`. La negación inoperante
  `!runs/*/manifest.yml` se documenta como tal en un comentario; arreglarla es
  Ola 1 (depende de qué se decida versionar de las corridas).
- `dist/` se reconstruye y se verifica con `tar tzf` que no quedan entradas
  sospechosas.

### C-4 · Métricas honestas (`metrics.py`)

`mcc()`, `wmcc()` y `cohen_kappa()` devuelven `None` cuando el denominador es 0
(o cuando `n == 0` o `1 - pe` es 0 en κ). `ScreeningMetrics.mcc`, `.wmcc` y
`.cohen_kappa` pasan a `float | None` con default `None`. Consumidores,
inventariados con `grep` (no hay otros):

| Consumidor | Cambio |
|---|---|
| `extraction_agreement.py:34,88` | `presence_kappa: float \| None`; hoy recibe `cohen_kappa(...)` y, sin este cambio, **Pydantic rechazaría el `None`** y la doble extracción reventaría. Es el consumidor que la primera versión de este diseño omitía. |
| `exports/methods.py:48-49,100` | `kappa` y `presence_kappa` imprimen `no calculable` en vez de `0.000`. |
| `exports/checklist.py:241-242` | MCC, WMCC y κ imprimen `no calculable`. |
| `cli.py:167` | idem en el resumen de la corrida. |
| `audit.py` (check `gold`) | **WARN** si κ o MCC son `None`, o si la matriz de confusión muestra que el gold tiene una sola clase (`tp+fn == 0` o `tn+fp == 0`): con gold de una sola clase κ vale 0.0 (definido) y es justo el caso A11. Con todo definido y ambas clases, PASS como hoy (los umbrales `kappa_min` son Ola 1). |

Un único helper `fmt_metric(value, spec=".3f") -> str` en `metrics.py` evita
repetir el `if value is None` en cinco sitios. `manifest.yml` y
`03_screening/metrics.json` persisten `null`.

### C-5 · Corrección de continuidad (`schemas/effects.py`)

`_log_or` aplica el `+0.5` de Haldane-Anscombe **solo** cuando alguna de las
cuatro celdas vale 0. Con celdas no nulas el logOR se calcula directo. El
docstring cita Sweeting 2004 y el sesgo hacia el nulo (+0,017) que la auditoría
midió.

## 7. Método de trabajo

TDD estricto, un test rojo por hallazgo antes de cada arreglo. Los tests
reproducen la evidencia citada en la auditoría, no una versión suavizada:

| Test | Reproduce |
|---|---|
| `test_provider_model_rejects_injection` | un `model` con comillas y `&` → `ValidationError` |
| `test_windows_cmd_shim_rejects_metachars` | BatBadBut sobre `.CMD`: argumento con `&` o `%` → `RuntimeError` sin crear proceso |
| `test_embed_images_rejects_traversal` | `../../.env` no se embebe |
| `test_export_html_strips_script_and_handlers` | `script`, `onerror=`, imagen remota |
| `test_pdf_url_fetcher_rejects_non_data` | `file://` y `http://` lanzan |
| `test_autonomy_a3_in_judgement_stage_rejected` | `screening_ta: A3` no carga |
| `test_decision_string_false_does_not_approve` | `approved: "false"` |
| `test_malformed_decision_yaml_is_actionable` | raíz lista → `ValueError`, no traceback |
| `test_rejected_final_gate_is_not_completed` | `approved: false` → `rejected`, rc ≠ 0 |
| `test_audit_fails_on_reconstruction_provenance` | manifiesto sin `provenance: pipeline` → no publicable |
| `test_validate_exits_2_on_retired_model` | `gemini-2.0-flash` → rc 2 |
| `test_mcc_and_kappa_none_when_undefined` | denominador 0 → `None`, no `0.0` |
| `test_continuity_correction_only_with_zero_cell` | logOR sin corrección con celdas no nulas |

Todos offline, sin red, deterministas. Línea base medida el 2026-09-25: **190
tests en verde** en 3.13 (la auditoría decía 188; se sumaron dos después).

Criterio de cierre de cada PR:

- `uv run pytest` en verde (3.13, el `requires-python` actual).
- La misma suite en 3.11 y 3.12 con un venv desechable, porque
  `requires-python >= 3.13` impide `uv run --python 3.11` (M24 es Ola 2):
  `uv venv --python 3.11 <tmp>`, `uv pip install --python <tmp> pydantic pyyaml
  python-dotenv markdown httpx nh3 pytest`, `PYTHONPATH=. <tmp>/Scripts/python
  -m pytest`.
- `uv run ruff check .`, `uv run ruff format --check .` y `uv run black
  --check .` limpios; `uv lock --check` OK.

## 8. Fuera de alcance (Olas 1 y 2)

`revisia run --resume`, `overrides` por registro en `decision.yml`,
`request_sha256`, `decisions.jsonl` incremental, el rework completo de
`audit.py` (esquemas, aritmética, plausibilidad temporal, umbrales), el
`01_search/log.json` de PRISMA-S, el fail-fast de proveedores, todo el
grounding (C2), el `normalize_doi()` único, `RunMeta` con parámetros realmente
aplicados, los flags de `claude -p`, el RoB por herramienta, la regeneración del
benchmark y la matriz de CI.

## 9. Riesgos asumidos

1. **`nh3` en el núcleo** introduce un wheel binario. Si una plataforma no tiene
   wheel, instalar RevisIA falla donde antes funcionaba. Mitigación: se verifica
   en la matriz de la Ola 2; si aparece el problema, se degrada a extra opcional
   con escapado como fallback (la opción descartada en D4).
2. **`float | None` es un cambio de tipo público.** Cualquier consumidor externo
   que lea `metrics.mcc` como `float` se rompe. RevisIA está en `0.6.0` y
   `Development Status :: 3 - Alpha`; se anota en el CHANGELOG como cambio
   incompatible.
3. **El error duro de autonomía** impide correr protocolos que hoy corren. Es
   intencional: correr con el HITL apagado en silencio es el fallo que C1
   describe.
4. **`gemini-3.5-flash-lite` también se retirará.** Por eso el arreglo no es el
   id nuevo sino `RETIRED_MODELS` consultado por `validate` **y por `run`** con
   `rc = 2`: la próxima vez el quickstart falla con un mensaje, no con un 404.
   La tabla se mantiene a mano y compara el id exacto: un id con prefijo
   (`models/…`, `google/…` en OpenRouter) no se detecta todavía.

## 10. Desviaciones durante la implementación

Registro de lo que cambió respecto a §4–§6 y al plan, y por qué. Todas salen de
las revisiones por tarea o de la revisión final de la pila; ninguna amplía el
alcance fuera de los hallazgos de la Ola 0.

| # | Dónde | Cambio | Origen |
|---|---|---|---|
| V1 | A-3 | Ancla rechazada antes de `resolve()` (UNC tocaba la red) y `_figuras_meta` confinada con el mismo helper. | Revisión Tarea 2 (Important, fallo del plan) |
| V2 | A-4 | `style` en `th`/`td` reconstruido a `text-align:<keyword>`: `filter_style_properties` de nh3 filtra por nombre de propiedad, no por valor (`text-align:url(…)` pasaba). | Revisión Tarea 2 |
| V3 | A-4 | `href` protocol-relative (`//host`) o con barra invertida descartado: abierto desde `file://` y clicado resuelve a UNC. Los chequeos de `href` se hacen sobre el valor normalizado como el parser WHATWG (sin tab/LF/CR y sin C0 ni espacios en los extremos): `/&#9;/host` y `&#1;//host` se saltaban la primera versión. | Revisión final (dos pasadas) |
| V4 | A-1 | Patrón de modelo con primer carácter alfanumérico: `^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$` (un id que empiece por guion se parece a un flag). | Revisión final |
| V5 | A-2 | La guardia del shim también inspecciona `cmd[0]` (la ruta del CLI). | Revisión final |
| V6 | B | Nuevo check `final_gate` en `revisia audit`: FAIL si el reporte final fue rechazado o no se decidió (un reporte rechazado o pausado hacía la corrida "APTA" aunque B-3 ya no la informara como `completed`); WARN si lo aprobó un actor no humano (`--auto-approve`, `auto-proceed`); sin ledger no duplica el FAIL de `ledger`. | Revisión final (Important + segunda pasada) |
| V7 | B/C | `main()` convierte también `yaml.YAMLError` de `protocol.yml` en `error: …` con rc 2 (vive en la rama C para no chocar al re-apilar). | Revisión final |
| V8 | C-2 | `revisia run` consulta `RETIRED_MODELS` antes de crear la carpeta de la corrida: el quickstart del README no llama a `validate`, así que D7 solo no bastaba. `validate` ya no imprime "Protocolo válido" antes de salir con 2. | Revisión final (Important, fallo del plan) |
| V9 | C-3 | `only-include` conserva los ficheros raíz que enlaza el README: `.env.example` (paso 1 del quickstart), `AGENTS.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `RELEASING.md`. | Revisión Tarea 6 y revisión final (fallo del plan) |
| V10 | C-4 | WARN de `gold` también con MCC `None` y con gold de una sola clase (ver tabla de C-4). | Revisión final (Important) |
| V11 | Todas | Los trailers `Co-Authored-By` nombran el modelo que escribió cada commit, no el literal del plan. | Harness de los subagentes |

Seguimientos, resueltos después de abrir las PRs (2026-09-25):

| # | Seguimiento | Resolución | Rama |
|---|---|---|---|
| S1 | Ids con prefijo en `RETIRED_MODELS` | `retirement_for` compara el último segmento de la ruta, sin mayúsculas y sin la variante `:tag` (`models/…`, `google/…:free`, `publishers/google/models/…`); el mensaje conserva el id original. | C |
| S2 | Traceback de `revisia check` con `--model`/`--provider` inválidos | Validación previa con `available_providers()` y `ProviderConfig`; código 2 y mensaje. | C |
| S3 | `<img>` sin `src` (imagen remota con título, de estilo referencia o HTML crudo) | Tras el saneado, se degrada a su texto alternativo en cursiva. | A |
| S4 | La prueba real del `URLFetcher` de WeasyPrint solo corría con el extra `pdf` | CI instala Pango y el extra `pdf` y falla si WeasyPrint no importa. Verificado además en Linux (WSL, WeasyPrint 70.0): suite completa sin omitidos y exportación PDF real de la corrida fundacional; con un HTML trampa, WeasyPrint pidió `file://` y `http://` pero solo abrió el `data:`. | A |
