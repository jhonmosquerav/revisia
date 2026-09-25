# Ola 0 del plan de remediación · diseño

- **Fecha:** 2026-09-25
- **Origen:** `docs/auditoria/2026-09-03-auditoria-completa.md` §8, "Ola 0 · esta semana, sin cambiar el diseño".
- **Base:** `main` @ `fd8dd64` (v0.6.0, 188 tests en verde).
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
| D4 | Saneado del HTML con **`nh3` en el núcleo**, sobre el HTML ya convertido | El exportador inyecta HTML propio (`figure` con la imagen en base64, tablas del flujo PRISMA) *antes* de convertir; escapar el markdown de entrada escaparía también lo nuestro. Sanear la salida con allowlist evita reordenar `_embed_md_images` y `_prisma_flow`. `nh3` es un wheel precompilado sin dependencias transitivas. |
| D5 | Ítem 7: **marca en el manifiesto + guardia en `audit.py`** | Es la única variante que impide que el auditor vuelva a decir APTA sobre el artefacto reconstruido: el aviso en Markdown no lo lee el motor. ~30 líneas, sin invadir el rework del auditor de la Ola 1. |
| D6 | MCC/WMCC/κ indefinidos → **`float \| None`** en funciones y esquema | Mientras `0.0` sea un valor válido, cualquier umbral `kappa_min` se compara contra un número inventado (A11: hoy el auditor da PASS a `gold` con κ=0.0). Propuesta de Claude aceptada con el diseño; revocable. |
| D7 | Un modelo retirado hace que `revisia validate` **salga con `rc = 2`** | El ítem 1 existe porque el quickstart está roto; una advertencia que no cambia el código de salida no lo detiene. Es un cambio de tres líneas y no adelanta el rework de `validate` de la Ola 1 (M6, fail-fast de proveedores), que sigue fuera de alcance. |

## 4. PR-A · `fix/ola0-seguridad-exportador`

Cierra **A1** (inyección de comandos en Windows), **A2** (lectura arbitraria de
ficheros en el export) y la parte de **M1** que la Ola 0 puede cubrir.

### A-1 · Validación del nombre de modelo (`llm/registry.py`)

`ProviderConfig.model` pasa a `Field(pattern=r"^[A-Za-z0-9._:/-]{1,64}$")`. Un
`protocol.yml` con un `model` que contenga comillas, `&` o `|` deja de cargar
con `ValidationError`. Es la barrera primaria de A1 y protege a todos los
proveedores, no solo a `claude_code`.

### A-2 · Escapado del shim de Windows (`llm/providers/claude_code.py`)

`_resolve_cli` devuelve hoy la ruta que da `shutil.which`, que en Windows es
`claude.CMD`. `CreateProcess` sobre un `.CMD`/`.BAT` delega en `cmd.exe`, que
**vuelve a parsear** la línea de comandos (BatBadBut): los argumentos que
`subprocess` ya citó se re-interpretan y `&`, `|`, `^`, `%` recuperan su
significado. Defensa en profundidad tras A-1: cuando el ejecutable resuelto
tiene extensión `.cmd` o `.bat`, los argumentos se escapan con las reglas de
`cmd.exe` antes de entregarlos a `subprocess`.

Alcance explícito: no se cambia el transporte (sigue siendo `subprocess` con
lista de argumentos, sin `shell=True`) ni se tocan los flags de `claude -p`
(A10 es Ola 2).

### A-3 · Confinamiento de las imágenes embebidas (`exports/document.py`)

`_embed_md_images` acepta hoy cualquier ruta relativa: una referencia
`![x](../../.env)` se embebe en el HTML como `data:` y el secreto viaja en el
entregable. Pasa a exigir dos condiciones:

1. `target.resolve().is_relative_to(base_dir.resolve())` — nada fuera de
   `deliverable/`, con symlinks resueltos.
2. `target.suffix.lower() in _MIME` — solo extensiones de imagen declaradas.

Lo que no cumple se degrada a su texto alternativo, como hoy hacen las
referencias externas y rotas.

### A-4 · Saneado del HTML de salida (`exports/document.py`)

Tras `_md_to_html`, el HTML pasa por `nh3.clean` con una allowlist:

- **Etiquetas:** las que emite `markdown` con `tables` y `fenced_code`, más
  `figure`, `figcaption` e `img`.
- **Atributos:** `src`, `alt`, `class`, `colspan`, `rowspan`, y `href` en los
  enlaces. Ningún `on*`.
- **Esquemas de URL:** solo `data:` para imágenes; `https:` y `mailto:` para
  enlaces.

Esto tumba `<script>`, los manejadores `onerror=` y las imágenes remotas (fuga
de red al abrir el entregable). El `figure` que inyecta el propio exportador
sobrevive porque el saneado corre **después** de la conversión, no antes. Nota:
`.svg` sigue en `_MIME`; dentro de una imagen con `src` `data:` el SVG no
ejecuta scripts, así que no se retira.

### A-5 · `url_fetcher` de WeasyPrint (`exports/document.py`)

`HTML(string=…)` usa hoy el fetcher por defecto, que resuelve `file://` y
`http://`. Se le pasa un `url_fetcher` que solo acepta `data:` y lanza
`ValueError` para cualquier otro esquema. Cierra la mitad PDF de M1, que la
auditoría solo pudo reproducir en HTML (WeasyPrint no estaba instalado).

### A-6 · `pyproject.toml`

`nh3>=0.2` entra en `dependencies`. El núcleo deja de ser pura-Python; se
documenta en el comentario del bloque, junto al de `markdown`.

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

- YAML malformado o con raíz que no sea mapa → `ValueError` con mensaje
  accionable (ruta del fichero y qué se esperaba), no un traceback.
- Los campos desconocidos se conservan en `detail` del ledger, como hoy.

Cierra tres hallazgos bajos y el vector en que `bool("false")` es verdadero.

### B-3 · El rechazo final es un rechazo (`orchestration/pipeline.py`)

La guarda `if final_gate.status == "paused"` pasa a
`if final_gate.status != "approved"`, devolviendo el estado del gate.
Consecuencias que se verifican con tests:

- Un `reporte/decision.yml` con `approved: false` produce `status: rejected`,
  no `completed`.
- El CLI sale con `rc != 0` para `rejected` (hoy `paused` ya lo hace).
- `--brain` no sedimenta una revisión rechazada.

### B-4 · Procedencia en el manifiesto y guardia en el auditor

- `RunContext.write_manifest` escribe `provenance: pipeline`.
- `audit.py` gana un check `provenance`: **FAIL** si el manifiesto no declara
  `provenance` o declara algo distinto de `pipeline`. Como `publishable` es
  `n_fail == 0`, una corrida reconstruida deja de ser publicable.
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
- `protocols/_TEMPLATE/protocol.yml` (líneas 64, 69, 99) y `README.md:84` al día.

### C-2 · Lista de modelos retirados

`revisia/llm/deprecations.py` con `RETIRED_MODELS: dict[str, str]` (id → fecha
de apagado ISO), poblada con lo verificado el 2026-09-08:

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
  "protocols/_TEMPLATE", "tests", "README.md", "CHANGELOG.md", "LICENSE",
  "NOTICE", "CITATION.cff", "pyproject.toml", "uv.lock"]`. Fuera quedan `runs/`,
  `.superpowers/`, `.claude/`, `.coverage` y el `dist/` ya construido.
- `.gitignore`: añadir `.superpowers/`. La negación inoperante
  `!runs/*/manifest.yml` se documenta como tal en un comentario; arreglarla es
  Ola 1 (depende de qué se decida versionar de las corridas).
- `dist/` se reconstruye y se verifica con `tar tzf` que no quedan entradas
  sospechosas.

### C-4 · Métricas honestas (`metrics.py`)

`mcc()`, `wmcc()` y `cohen_kappa()` devuelven `None` cuando el denominador es 0
(o cuando `1 - pe` es 0 en κ). `ScreeningMetrics.mcc`, `.wmcc` y
`.cohen_kappa` pasan a `float | None` con default `None`. Consumidores a
recorrer:

- `audit.py` — el check `gold` distingue "no calculable" de "por debajo del
  umbral"; no calculable es **WARN**, no PASS.
- `exports/checklist.py`, `exports/prisma_flow.py`, `cli.py` — imprimen
  `no calculable` en vez de `0.000`.
- `manifest.yml` y `03_screening/metrics.json` persisten `null`.

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
| `test_windows_cmd_shim_escapes_arguments` | BatBadBut sobre `.CMD` (sin ejecutar el CLI real) |
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

Todos offline, sin red, deterministas. Cada PR cierra con la suite completa en
verde bajo 3.11, 3.12 y 3.13, `ruff` y `black` limpios y `uv lock --check` OK.

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
   id nuevo sino `RETIRED_MODELS` más `validate` con `rc = 2`: la próxima vez el
   quickstart falla con un mensaje, no con un 404.
