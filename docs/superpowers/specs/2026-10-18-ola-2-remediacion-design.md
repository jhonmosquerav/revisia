# Ola 2 del plan de remediación · diseño

- **Fecha:** 2026-10-18
- **Origen:** `docs/auditoria/2026-09-03-auditoria-completa.md` §8, "Ola 2 · rigor y honestidad de las afirmaciones", más lo que la Ola 1 dejó explícitamente para esta ola (spec anterior §12 y §14, filas 24a, 31g, 45j, 45m; backlog de ejecución de la Ola 1).
- **Base:** `main` @ `c1af7c3` (v0.8.0; 1 359 funciones `test_` en 65 ficheros, ≈2 100 casos recogidos al cerrar la Ola 1, en verde en 3.11, 3.12 y 3.13; cobertura medida el 2026-10-18: 95 %).
- **Alcance declarado por la auditoría:** cierra C2, C3 en la parte del benchmark, A4, A5, A6, A7, A8, A10, A12, A15 y A16. Además cierra M3, M14, M15, M16, M17, M22, M24 y lo que la Ola 1 dejó pendiente (§1).
- **Spec anterior:** [`2026-10-04-ola-1-remediacion-design.md`](2026-10-04-ola-1-remediacion-design.md).

## 1. Por qué esta ola existe

La Ola 1 consiguió que el pipeline **pueda decir la verdad**: hay decisión
humana por registro, la corrida se reanuda sin repetir trabajo y el auditor
comprueba coherencia y no presencia. Lo que no consiguió, porque la auditoría lo
dejó para después, es que **lo que el pipeline afirma sea verificable**:

- El verificador anti-alucinación aprueba todo. En el modo por defecto
  (`embedder`, hash léxico con umbral 0,12) una cifra falsa, una dirección de
  efecto invertida o una afirmación sin relación pasan como fundamentadas (C2).
  Solo se comprueba la primera aparición de cada cita, y en modo `agent` el juez
  es el mismo proveedor que redactó la síntesis.
- El manifiesto registra parámetros que no viajaron (`seed`, `temperature` en
  `claude_code` y `anthropic`), el hash de una plantilla y no del prompt
  enviado, y nada del entorno (A6, A7, A15).
- El riesgo de sesgo usa una sola escala para seis herramientas, con dominios
  que no son los oficiales (A12). La extracción lee título y resumen, no el
  texto completo, y su `source_quote` no se comprueba nunca (M14).
- El benchmark del artículo fundacional hereda la corrida reconstruida y mezcla
  27 efectos de un mismo artículo (C3). Y la corrida de referencia sigue siendo
  esa reconstrucción: RevisIA no tiene todavía **una sola corrida real** que
  mostrar.

El veredicto vigente de la auditoría es «apto como motor de investigación y
prototipo; no apto todavía para sustentar una revisión sistemática publicable».
Esta ola existe para **revertir ese veredicto**, y para que lo revierta una
re-auditoría independiente y una corrida real auditada, no esta sesión.

Lo que la Ola 1 dejó para aquí, y dónde se resuelve:

| Pendiente de la Ola 1 | Origen | Dónde |
|---|---|---|
| Ingerir el texto completo en los rescates de no recuperados | §14 fila 31g, backlog B24 | PR-C, D21 |
| Ligar el meta-análisis (`effects.yml`) a los estudios incluidos | §14 fila 45p, backlog | PR-F, D16 |
| Extracción sobre texto completo (M14) | §12 | PR-C |
| `on_meta` por llamada (las llamadas pagadas de un registro que falla a mitad no se registran) | §14 fila 45j, backlog B10 | PR-A, D14 |
| Partir `checks_flow.py` (2 190 líneas) y `checks_hitl.py` (1 389) | backlog | PR-G, D26 |
| Recalcular `agreement.json` desde los diarios | backlog | PR-G |
| M15: bucle de rc 3 por fallo determinista de un registro | §14 fila 45j, README | PR-A + PR-C, D9 |
| ¿Rechazar `<<` también en `gold.yml`/`effects.yml`/criterios/formulario? | backlog | **Ya resuelto** en la Ola 1 (§14 fila 45v): cerrado, sin trabajo |
| Tests de pico de memoria sensibles a los extras instalados | memoria de la Ola 1 | PR-H |
| `pypdf` en algún extra | pendiente 3 | **Ya resuelto** en PR #21 (`search` y `demo`) |

## 2. Estado de partida verificado

Todo lo que sigue se verificó leyendo `main` @ `c1af7c3` el 2026-10-18. Los
números de línea de la auditoría están desfasados; aquí van los vigentes.

| Área | Estado real | Dónde |
|---|---|---|
| Grounding (C2) | `ReviewProtocol.grounding: str = "embedder"` sin validador: cualquier valor distinto de `agent`/`existence` se trata como embedder. El juez (`agent`) usa el proveedor de **síntesis**. Solo la primera aparición de cada cita (`extract_citations` deduplica). `_CITATION_RE` acepta `[2019]` y `[1]`. Una fuente vacía (`""`) también pasa al juez o al embedder; el coseno de un vector nulo es 0. El prompt del juez está en código, no en `prompts/`. `support_quote` se imprime, no se comprueba. | `config.py:129`; `pipeline.py:943-955,998,1013`; `verificador.py:30,33,76-92`; `rag/grounding.py:24,46` |
| Auditor `grounding` | FAIL solo ante marcas sin adjudicar, bandera incoherente o `exists_in_corpus` falso. **No distingue el modo**: una corrida `existence` o `embedder` sin marcas pasa en PASS. | `audit/checks_quality.py:412` |
| `RunMeta` (A6, A7) | `seed`/`temperature` repiten lo pedido en `LLMRequest`, aunque `claude_code` no pasa ninguno al CLI y `anthropic` no envía `seed`. `prompt_sha256 = sha256(system + "\n" + prompt)` del `req` **original**: sin el JSON Schema que `claude_code` y `local_openai` inyectan en el texto, sin el sufijo de reintento, sin el schema que viaja como tool/`response_schema`. Sin versión ni hash de plantilla, sin `effort`, sin coste, sin latencia. | `provenance/runmeta.py:56-85`; `claude_code.py:273-286,309-333`; `local_openai.py:39-58` |
| Reintentos de `claude_code` | Hasta 3 subprocesos por llamada; solo el último produce `RunMeta`. Los intentos fallidos (llamadas reales, pagadas) no quedan en ningún sitio. | `claude_code.py:316-333` |
| Registro de llamadas | `journaled` registra las metas **después** de `compute()`: si falla el segundo miembro del ensemble o el juez a mitad, las llamadas ya hechas de ese registro no llegan a `llm_calls.jsonl`. No hay `on_meta` en `screening.py`; solo en `grounding.py`. | `orchestration/journal.py:170-215`; `agents/screening.py:45-82` |
| Manifiesto (A15) | `run.json` lleva `engine_version` y `python_version`; el manifiesto los copia en `run`. Nada de plataforma, commit, dependencias ni hashes de plantilla (están solo en `run.json.prompt_sha256`, que el auditor no contrasta con las llamadas). | `run_context.py:190-238`; `snapshot.py:76,140-141`; `checks_provenance.py:289` |
| `claude -p` (A10) | Ya: `--tools ""`, `--strict-mcp-config`, `--safe-mode`, `--no-session-persistence`, cwd temporal neutro. Falta: `--json-schema` (el schema va como texto en el prompt), `--max-budget-usd`, entorno acotado (`_subprocess_env` copia todo `os.environ`), versión del CLI en la procedencia. `--bare` descartado a propósito (rompe la suscripción). El único `claude` en el PATH de la máquina del arquitecto es el shim npm `2.1.126`: anuncia `--json-schema`, `--max-budget-usd` y `--bare`, pero **no** `--safe-mode` ni `--max-turns`; el código vigente se probó con `2.1.285` (comentario en `_command`), que no está localizable hoy. `ProviderConfig` no tiene campo `cli`. Cómo devuelve `--json-schema` el objeto validado con `--output-format json` (en `result` o en otra clave) no está verificado: exige una llamada real autenticada, que una sesión anidada no puede hacer (401). | `claude_code.py:92-105,119-146`; `registry.py:51-68` |
| `agent` (A8) | El modelo que reporta es el texto de `protocol.yml`; el callback no puede decir qué modelo contestó. `agent_driver.run_review_with_agent(auto_approve=True)` por defecto. | `agent.py:90-145`; `agent_driver.py:37` |
| DOI (A4) | Cuatro normalizadores: `busqueda._normalize_doi` (quita solo `https://doi.org/` **antes** de `lower()`), `open_backends._doi` (cuatro prefijos, exige `10.`), `search_backends`/`ncbi` (`lower().strip()`), `manual_import._record_id` (quita el prefijo del id **pero guarda `doi` con prefijo**: el RIS no se fusiona con OpenAlex y sale renombrado `#2`). `SearchRecord` no valida ni normaliza `doi`. | `busqueda.py:41-44`; `open_backends.py:44-53`; `manual_import.py:22-25,52,99`; `records.py:44-61` |
| Dedup (A5) | `dedup_key` no quita prefijos. Los títulos de relleno `"(sin título)"` colapsan en una sola clave (`_NON_ALNUM` elimina la `í`). Sin NFKD. BibTeX por regex: `title = {The {IMF} and growth}` pierde el título. | `agents/dedup.py:24-35`; `manual_import.py:81-84` |
| Extracción (M14) | `extract_record` recibe **solo título y resumen**; el texto completo entra en `inputs` como `text_sha256` pero no en el prompt. `source_quote` es texto plano sin offsets; nadie la busca en la fuente. `status` nunca es `verified`. Las `key` devueltas no se contrastan con el formulario. | `agents/extraccion.py:35-64`; `pipeline.py:735-770` |
| Doble extracción (A16) | Docstring: «PRISMA exige ≥ 20 %» (falso). `value_agreement` compara `lower()` + espacios; `presence_kappa` degenera. El gate de extracción se invoca sin `records`: aprobar o rechazar la etapa entera. | `extraction_agreement.py:1-14,54-89`; `pipeline.py:1404` |
| Texto completo | `fetch_fulltext(max_chars=20000)` recorta sin registrarlo; el pipeline no pasa `max_chars`. Un rescate humano no tiene texto: RoB cae al resumen y el verificador marca sus citas (fila 31g). | `agents/fulltext.py:133-134,190,238`; `pipeline.py:643-644` |
| RoB (A12) | `TOOL_DOMAINS` con 5/7/3/6/4/5 dominios inventados; una sola escala `low/some_concerns/high/unclear`; la respuesta no se contrasta con los dominios (ni faltantes ni sobrantes); sin agregación; GRADE tratado como RoB por estudio. Gate sin `records`. | `agents/rob.py:23-62,77-117`; `schemas/rob.py:15-41`; `pipeline.py:1414` |
| Meta-análisis | `_meta_analysis(run)` no recibe los incluidos; solo hay un WARN (`_meta_sin_incluidos`) y una advertencia en `metodologia.md`. Sin intervalo de predicción, sin subgrupos, Egger desde k = 3, sin detección de duplicados. `effects.yml` sin `outcome`. | `pipeline.py:885-898`; `meta_analysis.py:125-208`; `checks_flow.py:2161` |
| Benchmark (C3) | `docs/benchmark-cribado.md` cita 0,820 e I² 90,7 % con aviso de procedencia. No existe comando ni módulo de benchmark. `protocols/prisma-ia-origen` vive **solo en el checkout principal** (git-ignorado), **sin `gold.yml`**, con `effects.yml` k = 28 (27 de un artículo) y todo el bloque `llm` en `agent`. | `docs/benchmark-cribado.md:1-14`; `C:\revisia\protocols\prisma-ia-origen\` |
| Auditor, tamaño | `checks_flow.py` 2 190 líneas (6 familias mezcladas), `checks_hitl.py` 1 389. `agreement.json` se compara con la solicitud, no se recalcula. | `audit/checks_flow.py`; `audit/checks_hitl.py` |
| CI (M22, M24) | Un job `ubuntu-latest`, Python 3.13, sin matriz, sin `uv lock --check`, sin cobertura, sin `permissions:`. `requires-python >= 3.13`, `target-version py313`. | `.github/workflows/ci.yml`; `pyproject.toml:10,98` |
| Pico de memoria | `test_auditoria_de_una_corrida_real_cabe_en_el_pico_de_memoria` arranca `tracemalloc` **antes** del import perezoso de `scipy.stats` que hace `meta_analyze`: con el extra `meta` instalado, el import cuenta en el pico. | `tests/test_audit_hitl_registro.py:473-508`; `meta_analysis.py:32,42` |
| Qdrant (M16) | Extra `rag`, `QDRANT_URL`/`QDRANT_API_KEY` en `.env.example`; ningún código lo usa. | `pyproject.toml`; `.env.example`; `rag/store.py` |
| Textos en caché | `04_fulltext/texts/` guarda el texto completo recuperado. Puede tener copyright: una corrida no se puede depositar tal cual en un repositorio abierto. | `pipeline.py:558`; `checks_flow.py:1008` |

Cinco hallazgos de la exploración condicionan el diseño:

1. **El protocolo es inmutable por corrida** (Ola 1, riesgo 9) y `effects.yml`
   y `gold.yml` entran en la instantánea al arrancar. Pero el gold se etiqueta
   sobre los registros que la búsqueda devuelve, y los efectos salen de los
   estudios incluidos: ambos se conocen **después** de arrancar. La corrida real
   necesita una corrida exploratoria previa (D18).
2. **Los textos completos no son depositables.** Hace falta una copia de depósito
   que los sustituya por sus hashes y que el auditor acepte (D17).
3. **`claude -p` cambia de flags entre versiones** y hay dos instalaciones
   distintas en la máquina del arquitecto. Los flags nuevos se detectan por
   capacidad, no se asumen (D11).
4. **Un registro que falla de forma determinista no tiene salida** sin pasar por
   el humano: la IA no va a producir una etiqueta válida por más que se reanude.
   La salida es el gate (D9).
5. **Los gates de extracción y RoB son los únicos sin decisión por registro.** El
   mecanismo de la Ola 1 (`records` en `decision.yml`, acciones `label` en el
   ledger, políticas por gate) se extiende a campos y dominios sin cambiar su
   forma (D3, D5).

## 3. Decisiones tomadas

D1–D6 las tomó el arquitecto el 2026-10-18 entre alternativas presentadas con
recomendación. D7–D27 son supuestos propuestos con el diseño y aceptados con él;
son revocables.

| # | Decisión | Razón |
|---|---|---|
| D1 | **La corrida real entra en la ola y es su criterio de cierre.** La Ola 2 no se declara cerrada hasta que exista una corrida de `prisma-ia-origen` producida por el motor liberado, con las decisiones del arquitecto en el ledger, que `revisia audit` declare APTA y que esté depositada (Zenodo) junto con la re-auditoría. Entonces se publica **1.0.0**. | Sin una corrida real, «reproducible» sigue siendo una promesa. El coste monetario es cero (suscripción Max, proveedor `claude_code`); el coste son horas del arquitecto repartidas en cinco gates. Se escogió frente a «motor ahora, corrida después» para que la ola cierre con evidencia y no con código. |
| D2 | **Publicable exige verificación por juez con modelo distinto.** `grounding` ∈ {`existence`, `judge`, `embedder`} validado. `existence` es el **default** (barato, honesto: solo comprueba que la cita exista) y el auditor da **FAIL** a una corrida `existence` o `embedder`. `judge` exige `llm.verificador` con `provider:model` distinto del de `sintesis` (error de preflight si coinciden; WARN si son del mismo fabricante, D24). `embedder` queda etiquetado experimental. | El README promete un verificador anti-alucinación como parte del diseño, no como opción. Si una corrida es publicable sin que nadie verificara las afirmaciones, la promesa vuelve a ser decorativa (C2). El juez solo se llama para citas que existen en el corpus; una síntesis típica tiene decenas de afirmaciones. |
| D3 | **Corrección por campo en la extracción.** `extraccion/decision.yml` admite `records: {"<study_id>": {fields: {<key>: {value, reason}}}}`. El valor humano manda, queda en el ledger con actor y razón (acción `edit_field`), la tabla final marca qué campos corrigió un humano y la síntesis usa los valores corregidos. Sin interfaz de formulario ni edición de texto libre. | Hoy un dato mal extraído solo se puede aprobar o rechazar con la etapa entera. En la Ola 1 se descartó por tamaño; aquí la extracción sobre texto completo y la verificación literal de la cita de origen bajan el coste marginal. Es lo que A0 significa: la IA propone, el humano decide campo a campo. |
| D4 | **La «doble extracción» pasa a ser concordancia IA–IA.** Se renombra a lo que es: una señal de calidad que apunta qué campos revisar primero. Comparación normalizada (números, unidades, espacios, mayúsculas), κ solo donde está definido, lista de desacuerdos en la solicitud del gate. `metodologia.md` declara: «extracción por IA, verificada campo a campo por un humano; concordancia IA–IA del 20 % como señal». Se borra «PRISMA exige ≥ 20 %». | Con D3 el humano revisa el 100 % de las tablas con capacidad de corregir, que es más fuerte que una doble extracción ciega del 20 %. Una doble extracción humana parcial costaría horas y código y tampoco cumpliría MECIR C43 (dos humanos al 100 %). Mejor declarar con precisión lo que se hizo. |
| D5 | **RoB por herramienta, definido como datos; GRADE fuera.** Cada herramienta (RoB2, ROBINS-I, Newcastle-Ottawa en sus dos formularios —cohortes, `NewcastleOttawa`, y casos-controles, `NewcastleOttawaCaseControl`—, AMSTAR-2, QUADAS-2: seis especificaciones) se define en un fichero con sus dominios o ítems oficiales, preguntas señalizadoras, escala de juicio y regla de agregación. El esquema admite escalas distintas por herramienta; RoB2 y ROBINS-I agregan con su algoritmo oficial. El humano corrige el juicio **por dominio** (y el global) en `rob/decision.yml` con razón (acción `edit_domain`). GRADE sale de `RoBTool` y del README: califica certeza por desenlace sobre el conjunto de estudios, no riesgo de sesgo por estudio; vuelve en una ola futura como etapa propia tras la síntesis. | Un revisor que conozca cualquiera de las herramientas ve los dominios inventados a la primera (A12). Mantener GRADE «aproximado» con una nota es lo contrario del título de esta ola. |
| D6 | **Comando `revisia benchmark` dentro del motor; el estudio, fuera.** Recibe un protocolo con corpus congelado (solo bases `imported/`) y `gold.yml`, más un fichero de panel (proveedor+modelo por celda, réplicas), corre el pipeline hasta el cribado T/A sin gates, una corrida por celda×réplica, y emite la tabla modelo × (recall, lost-evidence, MCC, WMCC, κ, IC de Wilson) y el meta-análisis por subgrupos corpus→modelo con intervalo de predicción, sin Egger bajo k = 10 y con detección de duplicados. El panel, el gold, los resultados y el artículo viven en el estudio externo (Dragon OS), como ya decidió el arquitecto. El repo deja de citar 0,820 e I² 90,7 % como evidencia. | El argumento del artículo fundacional es «valida el modelo en tu corpus contra tu gold»: si el motor público trae el comando, cualquier lector repite el benchmark sobre su propia revisión y la honestidad metodológica (unidad de análisis, sin duplicados) vive en código testeado, no en un script privado. |
| D7 | **Versión intermedia 0.9.0.** El motor terminado se publica como 0.9.0 (tag, release, DOI) **antes** de la corrida real, para que esa corrida registre un `engine_version` liberado y no un commit de desarrollo. 1.0.0 llega con la corrida depositada y la re-auditoría; el cambio entre ambas es documental (README, CITATION, auditoría §11). | Repetir «motor liberado → corrida con él» es lo que convierte el manifiesto en evidencia. |
| D8 | **Orden de la ola:** motor completo (PR-0 a PR-I) → 0.9.0 → re-auditoría del código (cinco áreas en paralelo, solo lectura, sobre el tag) → correcciones (0.9.x) → corrida exploratoria → gold y efectos → corrida real → `revisia audit` APTA → `revisia deposit` → Zenodo → re-auditoría de la corrida → 1.0.0. Si la corrida real destapa fallos, se corrigen en el motor y se repite lo que haga falta; la ola no cierra con parches a mano sobre la corrida. | Una corrida real sobre un motor sin re-auditar obligaría a repetirla si la re-auditoría encuentra algo. El orden minimiza las horas del arquitecto en riesgo. |
| D9 | **M15: un fallo determinista de un registro pasa al humano.** Los proveedores distinguen `TransientCallError` (429, 5xx, red, timeout: se reanuda) de `DeterministicCallError` (4xx distinto de 408/429, bloqueo de contenido, salida que no valida tras los reintentos). `journaled` escribe para la segunda una línea de diario con `output: null` y `error: {type, message}` (redactado) y el registro llega al gate como **pendiente de humano** (`must_label`/campos a rellenar), con la nota «la IA falló de forma determinista». La corrida ya no sale con rc 3 en bucle. | Reanudar no arregla un 400 por contexto ni un bloqueo de seguridad. La única salida honesta es la decisión humana, que ya existe. |
| D10 | **M3: los textos externos entran al prompt como datos.** Resúmenes, textos completos y fuentes del juez van delimitados (`<<<DOCUMENTO id=…>>> … <<<FIN>>>`) con la instrucción de ignorar cualquier orden dentro de ellos. Todas las plantillas suben de versión (`v2.md`) y conservan el nombre con versión en `RunMeta.prompt_template`. | Es barato, toca las mismas plantillas que se versionan en esta ola, y el juez de grounding lee el mismo texto atacante que la síntesis. No elimina la inyección; la hace declarable. |
| D11 | **`claude -p` acotado por capacidad detectada y versión mínima.** `claude --help` y `claude --version` se consultan una vez por proceso (cacheados). `MIN_CLI_VERSION` (la menor que anuncia `--safe-mode`, `--tools` y `--json-schema`; la fija PR-A con la sonda real) es error de preflight por debajo: «actualiza el CLI (`npm i -g @anthropic-ai/claude-code@latest`)». Flags que se añaden si el CLI los anuncia: `--json-schema <schema>` (sustituye al schema en el texto del prompt), `--max-turns 1`, `--max-budget-usd <x>` solo con `ANTHROPIC_API_KEY` en el entorno (con suscripción no aplica). `--safe-mode` y `--tools ""` son **obligatorios** (los garantiza la versión mínima). Entorno por **allowlist** (autenticación, red, locale, lo que el CLI necesita para arrancar; §5.3), nunca `os.environ` entero. Sin `--bare`. `cli_version` entra en `RunMeta.backend_version`. **Sonda real previa a PR-A:** el arquitecto ejecuta desde un terminal con sesión válida el script `scripts/sonda_claude_cli.py` (lo entrega PR-0: `--help`, `--version`, una llamada `-p --output-format json --json-schema` con un schema de dos campos, y vuelca la salida cruda redactada a `docs/superpowers/sondas/<fecha>-claude-cli.md`); el implementador de PR-A fija con esa salida el contrato de `--json-schema` (dónde viene el objeto validado) y `MIN_CLI_VERSION`. | El CLI de la máquina del arquitecto anuncia flags distintos del que se usó para probar el código vigente (§2). Asumir un flag es un `RuntimeError` a mitad de corrida; un entorno vacío rompe OAuth; una sesión anidada no puede hacer la llamada real (401, auditoría §9). |
| D12 | **Corridas 0.8 no son publicables; esquemas en versión 2.** `RunMeta`/`LLMCall`, `VerificationReport`, `ExtractionRecord`, `RoBAssessment`, `JournalEntry` y `MetaAnalysisResult` llevan `schema_version: 2`. Una corrida con artefactos v1 se audita entera como diagnóstico y recibe FAIL en `environment` («anterior a la Ola 2 (motor < 0.9): sin procedencia aplicada ni verificación por juez; regenera la corrida con el motor actual»), como D13 hizo con las anteriores a la Ola 1. Siguen siendo exportables y reanudables **no**: `--resume` de una corrida 0.8 da rc 2. | El coste real es nulo: la única corrida existente sigue siendo la reconstrucción. Permitir reanudar mezclaría metas v1 y v2 en el mismo `llm_calls.jsonl`. |
| D13 | **Fuera de alcance:** paralelismo de llamadas; Prefect/TUI; firma criptográfica del manifiesto; GRADE como etapa; migración de corridas; edición de texto libre en extracción; `rc` de `paused`; Hartung-Knapp como default (se ofrece como opción, §10.1). | Realizable en una ola. |
| D14 | **Cada llamada se registra al ocurrir, incluidos los intentos fallidos.** Un `MetaSink` por contexto (`contextvars`) recibe cada `RunMeta` en el momento en que el proveedor termina un intento; `journaled` instala el sink, `RunContext.record_meta` escribe en `llm_calls.jsonl` **en el acto**, y la línea del diario lleva las metas de ese registro. Un intento fallido tiene `outcome ≠ "ok"` y no necesita línea de diario. | Cierra la limitación B10/45j: si falla el segundo miembro del ensemble, la llamada pagada del primero queda registrada. Los reintentos de `claude_code` (hoy invisibles) pasan a ser procedencia. |
| D15 | **Afirmaciones, no citas.** El verificador parte la narrativa en oraciones; una **afirmación** es cada oración con al menos una cita del corpus. Se verifica **cada par (afirmación, cita)**, no la primera aparición. Una cita es `[id]` con `id` exactamente igual a un `record_id` del corpus; lo que va entre corchetes y no es un id del corpus pero tiene forma de id (`prefijo:…`, DOI) es `exists_in_corpus: false`; lo puramente numérico (`[2019]`, `[1]`) **no** es cita. Una oración con cifras y sin cita es «cuantitativa sin cita»: se cuenta y se lista, no se marca (WARN del auditor). Las cifras de una afirmación se buscan en la **fuente completa** de forma determinista antes del juez: una cifra ausente marca la afirmación aunque el juez diga lo contrario. **El juez recibe una ventana determinista de la fuente**, no el texto entero: el resumen siempre, más los párrafos de la fuente que contengan alguna cifra o algún término (≥ 4 letras, sin *stopwords*) de la afirmación, en orden del documento, hasta `verificador.max_source_chars` (default 12 000; configurable en `protocol.yml`); `inputs` del diario lleva `ventana_sha256`; si la ventana se recortó, el check lo anota (`window_truncated`). | C2: la alucinación típica es una cifra o una dirección de efecto. La comprobación determinista de cifras es la única que no depende de otro modelo. Los falsos positivos (cifras derivadas) los adjudica el humano por la vía de D8 de la Ola 1. La ventana acota el coste (decenas de llamadas × 120 000 caracteres sería dinero en API y horas con `claude_code`) y el riesgo de fallo por contexto, y es reproducible porque se construye sin IA. |
| D16 | **El meta-análisis se liga a los incluidos y a su unidad de análisis.** Cada efecto de `effects.yml` lleva `outcome`; se agrupa por desenlace. Un efecto cuyo `study_id` no está entre los incluidos tras el gate FT se excluye del análisis y se lista en `08_meta/excluded_effects.json` (`reason: not_included`); los incluidos sin efecto se listan también. Dos efectos del mismo estudio en el mismo desenlace son error (`unidad de análisis`) salvo `multiple_per_study: {allowed: true, justification}` en el fichero. Con k < 2 tras filtrar, no hay meta-análisis y se declara. El auditor da FAIL si el conjunto agregado ≠ efectos ∩ incluidos. | Cochrane Handbook §23.3. El `effects.yml` actual de `prisma-ia-origen` es el caso contrario (27 efectos de un artículo) y dejaría de cargar. |
| D17 | **Copia de depósito sin textos completos.** `revisia deposit <run_dir> --out <dir>` copia la corrida sin `04_fulltext/texts/` ni `screening_ft/rescues/`, escribe `deposit.json` (`schema_version`, `withheld: ["04_fulltext/texts/", …]`, hashes de lo retenido, `created_utc`, motivo) y el auditor, al ver `deposit.json`, trata la relación «textos en caché frente a `retrieval.json`» como verificada por hash y lo anota. Nada más cambia. | Los textos completos recuperados pueden tener copyright. Sin esto, D1 (depositar la corrida) no es realizable con honestidad. |
| D18 | **Corrida exploratoria y corrida real.** El protocolo sigue inmutable por corrida. El gold y los efectos se preparan a partir de una corrida exploratoria (sin publicabilidad; puede usar `--auto-approve`) con `revisia gold-template` y con las extracciones aprobadas, y la corrida real arranca después con `gold.yml` y `effects.yml` en el protocolo. | Alternativa descartada: enmendar el protocolo a mitad de corrida con registro en el ledger. Es diseño nuevo en la instantánea y en cinco checks del auditor, para un problema que la práctica resuelve con un piloto. |
| D19 | **Un solo `normalize_doi()` y validación en el modelo.** `revisia/ingest/doi.py` con la única normalización del paquete, aplicada por un `field_validator` de `SearchRecord.doi` (todo backend queda normalizado al construir el registro). `record_id` = DOI normalizado o el fallback de cada backend. En el dedup, los títulos de relleno nunca forman clave (un registro sin DOI y sin título no se fusiona con nadie); los títulos se normalizan con NFKD y sin diacríticos. BibTeX con parser de llaves. | A4 y A5, y la causa de los `#2` de la Ola 1 (§2 hallazgo 3). |
| D20 | **Texto completo entero, con el recorte registrado.** `fulltext.max_chars` es configurable en `protocol.yml` (default 120 000 caracteres); `RetrievalOutcome` gana `truncated` y `n_chars_total`; la extracción, RoB y el verificador reciben el texto, y `metodologia.md` declara qué estudios se recortaron. | M14. 20 000 caracteres son la introducción y parte de los métodos; con un límite declarado el revisor sabe qué leyó la IA. |
| D21 | **El humano puede aportar el texto de un rescate.** En `screening_ft/decision.yml`, un rescate admite `text_file: "rescues/<nombre>"` (PDF, TXT, MD o HTML dentro de `run_dir/screening_ft/rescues/`). Al reanudar, el pipeline lo ingiere a `04_fulltext/texts/`, marca `retrieval.json` con `source: human_rescue` y el hash del fichero, y el estudio llega a extracción, RoB y verificación con texto. Sin `text_file`, el rescate sigue como hoy y se declara. | Fila 31g: hoy un rescate llega a RoB sin texto y el verificador marca sus citas. |
| D22 | **Cita de origen literal.** `source_quote` (extracción, RoB, juez) se busca en la fuente: `quote_status ∈ {exact, normalized, not_found, none}` (normalizado = espacios, mayúsculas, guiones, comillas tipográficas). Un campo con valor y `not_found` sale en `attention` de la solicitud del gate; en el juez, una `support_quote` no encontrada vuelve el veredicto `grounded: false`. | A12 y C2: «cita textual» que nadie comprueba no es evidencia. |
| D23 | **Benchmark: corridas que nunca son revisiones, sobre un corpus nativo congelado.** `run.json.kind ∈ {review, benchmark}`; una corrida `benchmark` se detiene tras T/A, no abre gates, no escribe entregable y el auditor la declara «corrida de benchmark: no es una revisión» (no publicable, sin cascada de FAIL). El corpus congelado se importa en **formato nativo**: `imported/*.records.json` (una `list[SearchRecord]`, p. ej. la copia de `02_dedup/records.json` de la corrida exploratoria), nuevo tipo de importación en `manual_import` junto a RIS y BibTeX, que conserva los `record_id` tal cual; así el `gold.yml` etiquetado sobre la exploratoria casa con el corpus del panel. `revisia benchmark` acepta además RIS/BibTeX, con el aviso de que los ids de registros sin DOI cambian. | Las corridas del panel no deben confundirse con revisiones ni exigir decisiones humanas que no tienen sentido. Sin importación nativa, un registro sin DOI recibe `hash:<título>` al importar y el gold de la exploratoria no casaría (§2, `manual_import.py:22-25`). |
| D24 | **Fabricante del modelo para la regla del juez.** `VENDOR = {claude_code, anthropic, agent → anthropic; gemini → google; openai → openai; zai → zhipu; openrouter, local_openai → desconocido}`. Distinto `provider:model` es obligatorio; mismo fabricante da WARN en preflight y en el auditor («juez de la misma familia que el redactor»). | «Proveedor distinto» literal bloquearía Opus redactando y Sonnet juzgando, que es legítimo pero menos independiente. |
| D25 | **CI:** matriz `ubuntu-latest`/`windows-latest` × 3.11/3.12/3.13 con `uv`, caché, `uv lock --check`, `permissions: contents: read`; `requires-python >= 3.11`; cobertura con `pytest-cov` y `--cov-fail-under=90` en `ubuntu` 3.13 (la auditoría pedía ≥ 80 %; hoy está en 95 %, así que 80 no protegería nada); el extra `pdf` (WeasyPrint) solo en Ubuntu; `uv build` como humo. | M22, M24. El autor desarrolla en Windows y el CI nunca lo ha probado. |
| D26 | **Partición del auditor sin cambio de comportamiento:** `checks_flow.py` → `checks_flow.py` (embudo, conteos, CSV, diagrama), `checks_journals.py` (relaciones 12–13, consolidados, llamadas), `checks_meta.py` (meta-análisis y sus entregables), `checks_artifacts.py` (`stage_artifacts`, `deliverable`); `checks_hitl.py` → `checks_ledger.py`, `checks_hitl.py`, `checks_request_hash.py`, `checks_final_gate.py`. Ningún módulo del auditor supera 900 líneas. Primer commit de PR-G: la partición, con la suite en verde. | Backlog. Los módulos de 2 000 líneas no se revisan. |
| D27 | **Qdrant desaparece como promesa.** Se eliminan el extra `rag`, `QDRANT_*` de `.env.example` y `InMemoryVectorStore`; `semantic_similarity` se queda (lo usa el modo `embedder`). | M16: nada lo usa. |

## 4. Contratos de artefactos (PR-0)

Esta sección es el contrato entre las pistas. Se implementa en `revisia/schemas/`
y `revisia/provenance/` en PR-0, para que todas las pistas importen los mismos
modelos. Se conservan las convenciones de la Ola 1 (§4.1 del spec anterior):
`canonical_json`, horas ISO-8601 UTC, rutas relativas con `/`, ningún
`record_id` como nombre de fichero, claves de registro entre comillas en YAML.

### 4.1 Árbol del directorio de corrida

N = nuevo, M = modificado respecto a la Ola 1.

| Ruta | Formato | | Cuándo existe |
|---|---|---|---|
| `run.json` | `RunInfo` v2: + `kind`, + `environment` | M | Siempre |
| `llm_calls.jsonl` | líneas `LLMCall` v2 (una por **intento**) | M | Desde la primera llamada |
| `decisions_ledger.jsonl` | + acciones `edit_field`, `edit_domain`, `rescue_text` | M | — |
| `01_search/records.json`, `02_dedup/*` | DOI normalizados; `DedupReport.unmerged_placeholders` | M | — |
| `03_screening/journal.jsonl` | líneas con `error` posible (D9) | M | — |
| `04_fulltext/retrieval.json` | + `truncated`, `n_chars_total`, `source: oa \| human_rescue`, `rescue_file_sha256` | M | — |
| `screening_ft/rescues/<nombre>` | fichero aportado por el humano | N | Solo si hubo rescate con texto |
| `05_extraction/extractions.json` | `ExtractionRecord` v2 (+ `source_text`, `quote_status`, `human_*`) | M | — |
| `05_extraction/agreement.json` | `ExtractionAgreement` v2 (+ `kind`, `disagreements`) | M | Con segundo extractor |
| `06_synthesis/verification.jsonl` | `JournalEntry` por **comprobación** (`record_id = "check:<i>:<id>"`) | M | En modo `judge`; una sola línea `verificacion` en los demás |
| `06_synthesis/verification.json` | `VerificationReport` v2 | M | — |
| `07_rob/assessments.json` | `RoBAssessment` v2 | M | — |
| `08_meta/meta_analysis.json` | `MetaAnalysisResult` v2 (por desenlace, PI, subgrupos) | M | Con efectos válidos tras filtrar |
| `08_meta/excluded_effects.json` | `list[ExcludedEffect]` + `included_without_effect: [ids]` | N | Con `effects.yml` en la instantánea |
| `deliverable/riesgo_de_sesgo.md`, `interop/robvis.csv` | por herramienta (D5) | M | — |
| `deposit.json` | `DepositInfo` (D17) | N | Solo en una copia de depósito |
| `manifest.yml` | + `environment`, + `verification.mode/judge`, + `rob.tool_version` | M | — |

Benchmark (D6, D23): `benchmarks/<slug>-<fecha>/` con `panel.yml` (copia),
`runs/<celda>-r<k>/` (corridas `kind: benchmark`), `benchmark.json`,
`benchmark.md` y, con `benchmark-report`, `pooled/`.

### 4.2 Campos

**`RunMeta` v2** (`provenance/runmeta.py`). Conserva todos los campos de v1
con su significado («lo pedido») y añade:

| Campo | Tipo | Significado |
|---|---|---|
| `schema_version` | `2` | — |
| `seed_applied`, `temperature_applied`, `top_p_applied` | `int \| None`, `float \| None`, `float \| None` | lo que **viajó** al backend; `None` si el backend no lo admite (`claude_code`: todos `None`; `anthropic`: `seed_applied None`) |
| `prompt_sha256` | redefinido | `sha256(system + "\n" + texto_enviado)`, donde `texto_enviado` incluye el schema inyectado y el sufijo de reintento cuando el proveedor los mete en el texto |
| `schema_sha256` | `str \| None` | `canonical_sha256(schema.model_json_schema())` cuando el schema viaja aparte (tool, `response_schema`, `--json-schema`) |
| `prompt_template`, `prompt_template_sha256` | `str \| None` | `"extraccion/v2.md"` y su hash (texto LF), el mismo que `run.json.environment.prompt_templates` |
| `attempt`, `outcome` | `int ≥ 1`, `Literal["ok","invalid_output","transient_error","deterministic_error"]` | cada intento es una meta; solo `ok` lleva resultado |
| `effort` | `str \| None` | `claude_code` |
| `backend_version` | `str \| None` | versión del SDK o del CLI (`claude --version`) |
| `latency_ms` | `int \| None` | pared, medido por el proveedor |
| `cost_usd` | `float \| None` | si el backend lo reporta (`claude -p` JSON `total_cost_usd`) |
| `model_source` | `Literal["config","backend","callback"]` | de dónde salió `model`: `backend` cuando la respuesta trae el id real; `callback` en `agent` (A8) |

`deterministic` sigue valiendo `True` solo en `fake`. `LLMCall` v2 =
`RunMeta` v2 + `stage`, `record_id`, `role`, como en la Ola 1.

**`RunInfo` v2** añade `kind: Literal["review","benchmark"]` y
`environment: Environment`:
`{engine_version, python_version, python_implementation, platform
(platform.platform()), git_commit: str | None, git_dirty: bool | None,
packages: dict[str, str]` (versión instalada de `pydantic`, `pyyaml`,
`python-dotenv`, `markdown`, `nh3`, `httpx`, `pypdf`, `scipy`, `matplotlib`,
`google-genai`, `openai`, `anthropic`, `weasyprint`, los presentes),
`prompt_templates: dict["<agente>/<ver>.md", sha]` (sustituye a
`RunInfo.prompt_sha256`, que se retira para quitar la colisión de nombre con
`RunMeta.prompt_sha256`), `created_utc}`. `git_commit` solo cuando el paquete
se importa desde un checkout con `.git` (`subprocess` a `git rev-parse HEAD`,
timeout 5 s, `None` si falla). El manifiesto copia `environment` entero.

**`JournalEntry` v2**: `output: dict | None`, `error: {type: str, message:
str (redactado), attempts: int} | None`, `status: Literal["ok","failed"]`.
`status == failed ⇔ output is None ⇔ error is not None`. La clave sigue siendo
`(record_id, input_sha256)`; una línea `failed` es definitiva para esas entradas
(no se reintenta al reanudar).

**`FullText`/`RetrievalOutcome`**: + `truncated: bool`, `n_chars_total: int |
None`, `source: Literal["oa","human_rescue"]`, `rescue_file: str | None`
(`"screening_ft/rescues/<nombre>"`), `rescue_file_sha256: str | None`.

**`ExtractionField` v2**: `value`, `source_quote`, `quote_status:
Literal["exact","normalized","not_found","none"]`, `quote_offset: int | None`,
`confidence`, `status` (como hoy; `verified` solo lo pone el humano), `human_value:
str | int | float | None`, `human_reason`, `human_actor`, `human_edited: bool`.
Propiedad `final_value` = `human_value` si `human_edited`, si no `value`.
**`ExtractionRecord` v2**: + `source_text: Literal["fulltext","abstract"]`,
`text_sha256: str | None`, `truncated: bool`, `status: Literal["ok","failed"]`
(D9: un estudio cuya extracción falló llega vacío al gate).

**`ExtractionAgreement` v2**: + `kind: Literal["ia_ia_concordance"]`,
`disagreements: list[{study_id, key, value_a, value_b}]`, `presence_kappa_note:
str | None` («sin varianza: todos los campos presentes en ambos»).

**`RoBToolSpec`** (`revisia/rob/tools/<tool>.yml`, validado al cargar):
`{id, name, version (p. ej. "RoB 2 · 2019-08-22"), unit: domain | item | star,
judgment_scale: [valores], overall_scale: [valores] | None, domains:
[{id, name, signalling_questions: [{id, text, answers: [valores]}], scale?:
[valores]}], aggregation: rob2 | robins_i | amstar2 | nos_stars | none,
critical_items: [ids] (AMSTAR-2), applicability: [{id, name}] (QUADAS-2),
robvis_template: rob2 | robins_i | quadas2 | generic}`. Las cinco
especificaciones son parte del paquete; su hash entra en
`environment.prompt_templates` bajo la clave `rob/<tool>.yml`.

**`RoBAssessment` v2**: `study_id`, `tool`, `tool_version`, `domains:
[{id, judgment: str (validado contra la escala del dominio), rationale,
support_quote, quote_status, answers: {q_id: answer}, human_judgment,
human_reason, human_actor}]`, `applicability: [{id, judgment, rationale}]`
(QUADAS-2), `overall_llm: str | None` (lo que dijo el modelo; informativo),
`overall_algorithm: str | None` (lo que da la regla de agregación sobre los
juicios finales), `overall_human`, `overall_reason`, `overall: str | None`
(final: `overall_human` o `overall_algorithm`; `None` en herramientas sin
global), `source_text`, `status: ok | failed`.

**`VerificationReport` v2**: `stage`, `mode: existence | judge | embedder`,
`judge: {provider, model} | None`, `n_claims`, `n_uncited_quantitative`,
`uncited_quantitative: [{claim_index, sentence (≤ 300), numbers}]`, `checks:
[CitationCheck v2]`, `hallucination_flagged`, `notes`.
**`CitationCheck` v2**: `index`, `claim_index`, `claim` (la oración entera,
≤ 600), `cited_id`, `exists_in_corpus`, `source_available: bool` (fuente no
vacía), `numbers_in_claim: [str]`, `numbers_missing: [str]`, `grounded`,
`support_quote`, `quote_status`, `verdict_reason`, `note`. La regla de «cita
marcada» no cambia: `flagged_indices()` = `not exists_in_corpus or not
grounded`. `grounded` se calcula así: `exists and source_available and not
numbers_missing and (modo existence → True; judge → verdict.grounded and
quote_status ≠ not_found; embedder → sim ≥ umbral)`.

**`EffectInput` v2**: + `outcome: str` (obligatorio), `subgroup: str | None`.
**`EffectsFile` v2**: + `multiple_per_study: {allowed: bool, justification:
str} | None`, `random_method: DL | HKSJ = DL`. **`MetaAnalysisResult` v2**:
`outcomes: [{outcome, k, measure, studies, fixed, random, heterogeneity,
prediction_interval: {low, high, df} | None (k ≥ 3), egger: … | None (solo
k ≥ 10; si no, `egger_note`), subgroups: [{subgroup, k, random, q_between?}],
duplicates: [{study_ids, yi, vi}]}]`, `excluded: int`, `random_method`.
**`ExcludedEffect`**: `study_id`, `outcome`, `reason: not_included |
unit_of_analysis | invalid`.

**`DepositInfo`** (`deposit.json`): `schema_version`, `created_utc`, `source_run:
{slug, timestamp, manifest_sha256}`, `withheld: [{path, reason: copyright |
private, files: [{relpath, sha256, n_bytes}]}]`, `engine_version`.

**`BenchmarkPanel`** (`panel.yml`): `{name, replicas: int ≥ 1, cells:
[{name, provider, model, temperature: 0.0, effort?}]}`. **`BenchmarkResult`**
(`benchmark.json`): `{schema_version, protocol: {slug, corpus_sha256,
gold_sha256, n_records, n_gold_positives}, environment, cells: [{cell,
replica, run_dir, metrics: ScreeningMetrics, recall_ci95: [lo, hi],
models_used, n_calls, n_failed_records}], created_utc}`.

**`review_request.yml`**, claves nuevas por gate:

| Gate | Claves nuevas |
|---|---|
| `screening_ta`, `screening_ft` | `failed: [ids]` (D9; están también en `must_label` con nota) |
| `screening_ft` | en `rescuable[]`: `accepts_text_file: true`, `rescues_dir: "screening_ft/rescues/"` |
| `extraccion` | `studies[].fields{}` gana `quote_status` y `source_text`; `attention: [{study_id, key, reason: quote_not_found \| disagreement \| failed}]`; `editable: {study_id: [keys]}`; `second_extraction` renombrado `concordance` |
| `rob` | `tool_version`; `studies[].domains[]` con `id`, `answers`, `quote_status`; `overall_algorithm`; `editable: {study_id: {domains: [ids], overall: bool}}`; `attention` |
| `reporte` | `verification{mode, judge, n_claims, n_uncited_quantitative, …}`; `flagged[].numbers_missing` |

**`decision.yml`** (`HumanDecision`, `extra="allow"`):
- `records` admite tres formas según el gate, validadas por la política del
  gate: `RecordLabel` (cribado, como hoy, + `text_file: str | None` solo en un
  rescate de FT); `FieldEdits(fields: dict[str, FieldEdit(value: str | int |
  float | None, reason: str)])` en `extraccion`; `DomainEdits(domains:
  dict[str, DomainEdit(judgment: str, reason: str)], overall: DomainEdit |
  None)` en `rob`. `extra="forbid"` en todas.
- Al aprobar: estudio o clave fuera de `editable` → error; `reason` vacía →
  error; `judgment` fuera de la escala → error; `text_file` fuera de
  `rescues/` o inexistente → error. Con `approved: false` nada se aplica.

**Ledger.** `LEDGER_ACTIONS` gana `edit_field`, `edit_domain` y
`rescue_text`.

| Acción | Contenido |
|---|---|
| `edit_field` | stage `extraccion`, `target = "<study_id>#<key>"`, actor = el de `decision.yml`, `detail{from, to, reason, request_sha256, decision_sha256}` |
| `edit_domain` | stage `rob`, `target = "<study_id>#<domain_id>"` o `"<study_id>#overall"`, `detail{from, to, reason, request_sha256, decision_sha256}` |
| `rescue_text` | stage `screening_ft`, `target = record_id`, `detail{text_file, file_sha256, n_chars, request_sha256, decision_sha256}`; va junto a su `label` |

Las ediciones se escriben antes de su `approve`, en orden de id y clave;
nunca acompañan a un `reject`. `GateSummary` gana `n_edits`.

### 4.3 Relaciones que deben cumplirse

Se añaden a las 18 de la Ola 1. Las verifica el auditor y las garantiza el
pipeline; cada una tiene su test en el lado que la produce.

*Procedencia*

19. Cada línea de `llm_calls.jsonl` con `outcome == ok` aparece idéntica en
    la línea de diario de su `(stage, record_id)`; las de `outcome ≠ ok` no
    necesitan diario. Para cada llamada, `prompt_template_sha256 ==
    environment.prompt_templates[prompt_template]`.
20. `manifest.environment == run.json.environment`; `engine_version` es un
    SemVer; `models_used` y `deterministic_token_level` se calculan sobre las
    llamadas `ok`.
21. Un `RunMeta` de `claude_code` tiene `seed_applied == temperature_applied ==
    None`; uno de `anthropic`, `seed_applied == None`; `deterministic == True`
    solo con `provider == fake`.

*Diarios con fallo (D9)*

22. Una línea `failed` del diario de T/A o FT ⇒ ese registro tiene
    `ensemble_label == None`, `votes == []` y, con el gate aprobado,
    `human_label ≠ None`. Una línea `failed` de extracción o RoB ⇒ el
    consolidado tiene `status: failed` y, con el gate aprobado, todas sus claves
    (dominios) con edición humana.

*Texto completo y extracción*

23. `retrieval.source == human_rescue` ⇔ hay `rescue_text` para ese id en la
    decisión efectiva de FT, con `file_sha256` igual al del fichero en
    `rescues/` y `text_sha256` igual al del texto en caché.
24. `ExtractionRecord.source_text == fulltext` ⇔ `retrieval.available` para ese
    id; `text_sha256` coincide con el de `retrieval.json`. `quote_status` se
    recalcula desde el texto en caché (o el resumen) y coincide.
25. `human_edited` ⇔ hay `edit_field` con ese `target` y el `decision_sha256`
    de la decisión efectiva, con `to == human_value` y `reason ==
    human_reason`; `final_value` coherente. La narrativa (diario `sintesis`)
    tiene en `inputs.extracciones_sha256` el hash de las extracciones **con**
    los valores finales.
26. `agreement.json` se recalcula desde `journal.jsonl` y `journal_2.jsonl`
    (sin campos humanos) y coincide; `n_studies` = tamaño del subconjunto
    determinista.

*Riesgo de sesgo*

27. `assessment.tool == protocol.rob_tool`; `tool_version == spec.version`; los
    ids de dominios == los de la especificación, en su orden; cada juicio ∈ su
    escala; `overall_algorithm == aggregate(spec, juicios finales)`; `overall ==
    overall_human or overall_algorithm`; `human_judgment` ⇔ `edit_domain`
    (como la 25).

*Verificación (D2, D15)*

28. `verification.mode == protocol.grounding`; en `judge`, `judge.provider:model
    == protocol.llm.verificador` ≠ `protocol.llm.sintesis`. Las afirmaciones se
    recalculan desde la narrativa de `documento.md` y coinciden en número e ids
    con `checks`; `n_uncited_quantitative` coincide. Cada `check` con
    `exists_in_corpus and source_available` en modo `judge` tiene su línea
    `check:<i>:<id>` en `verification.jsonl` con exactamente una llamada `ok` y
    con `inputs.ventana_sha256 == sha256(source_window(...))` recalculada desde
    el texto en caché (D15). `grounded` se recalcula con la regla de §4.2 y
    coincide; `numbers_missing` se recalcula sobre la fuente completa.

*Meta-análisis (D16)*

29. Conjunto agregado por desenlace == `{efectos de la instantánea} ∩
    {incluidos}` − `excluded_effects`; `excluded_effects` ∪ agregados == efectos
    de la instantánea; `included_without_effect` == incluidos − estudios con
    efecto; sin `multiple_per_study.allowed`, ningún `study_id` se repite en un
    desenlace; `egger is None` ⇔ k < 10; `prediction_interval is None` ⇔ k < 3.

*Depósito (D17)*

30. Con `deposit.json`: cada fichero retenido tiene su `sha256` en
    `withheld`; `retrieval.json.text_sha256` ∈ esos hashes para cada
    `available`; no hay ficheros fuera de la lista en `04_fulltext/texts/`.
    `deposit.source_run.manifest_sha256 == sha256(manifest.yml)`.

*Benchmark (D23)*

31. `run.json.kind == benchmark` ⇒ no hay `decisions_ledger.jsonl` ni gates ni
    `deliverable/`; `03_screening/metrics.json` existe; `benchmark.json`
    referencia cada `run_dir` y copia sus métricas tal cual.

### 4.4 Qué contiene PR-0 en código

- `revisia/provenance/runmeta.py`: `RunMeta` v2 y `Outcome`.
- `revisia/provenance/sink.py`: `MetaSink`, `emit(meta)`, `collecting() ->
  ContextManager[list[RunMeta]]`, `current_sink()`. Sin consumidores todavía.
- `revisia/llm/base.py`: `TransientCallError`, `DeterministicCallError`
  (ambas `RuntimeError`), `LLMRequest.prompt_template: str | None`.
- `revisia/schemas/artifacts.py`: `RunInfo` v2, `Environment`, `JournalEntry`
  v2, `LLMCall` v2, `RetrievalOutcome` v2, `DepositInfo`, `RunKind`.
- `revisia/schemas/extraction.py`, `rob.py`, `verification.py`, `effects.py`:
  modelos v2 (aditivos: defaults que reproducen v1 donde se pueda; `RoBTool`
  sin `GRADE`).
- `revisia/schemas/rob_tools.py`: `RoBToolSpec`, `load_tool_spec(tool)`, y los
  seis YAML en `revisia/rob/tools/` con la **estructura oficial** de cada
  herramienta (RoB 2 2019; ROBINS-I 2016; NOS cohortes y NOS casos-controles;
  AMSTAR 2 de 16 ítems con los 7 críticos; QUADAS-2 con 4 dominios + 3 de
  aplicabilidad): ids y nombres de dominios/ítems, número y orden de las
  preguntas señalizadoras, escalas y reglas de agregación. **El texto de las
  preguntas señalizadoras de RoB 2 y ROBINS-I no se transcribe literalmente**
  (se publican bajo CC BY-NC-ND y el paquete es Apache-2.0): cada pregunta
  lleva un id oficial (`1.1`, `1.2`…), una paráfrasis corta propia y la
  referencia a la fuente (URL y versión); el prompt remite al evaluador a la
  herramienta oficial por su id. AMSTAR 2 (BMJ, CC BY-NC) y QUADAS-2 (Annals)
  reciben el mismo trato; NOS (Ottawa Hospital Research Institute) también.
  Un test por herramienta fija el número de dominios/ítems, los ids y la
  escala.
- `revisia/schemas/benchmark.py`: `BenchmarkPanel`, `BenchmarkResult`.
- `revisia/ingest/doi.py`: `normalize_doi()` con sus tests (sin cablearlo
  todavía).
- `scripts/sonda_claude_cli.py` (D11): script autónomo, sin dependencias del
  paquete, que el arquitecto ejecuta desde un terminal con sesión válida y
  cuya salida redactada va a `docs/superpowers/sondas/`.
- `revisia/provenance/ledger.py`: acciones nuevas; `GateSummary.n_edits`.
- `revisia/orchestration/hitl.py`: `FieldEdits`, `DomainEdits`, `FieldEdit`,
  `DomainEdit`, `RecordLabel.text_file` (solo modelos y validación estructural).
- `tests/fakes.py`: `ScriptedProvider` gana `fail_deterministic_at`, `judge`
  (veredictos por palabra clave), `extraccion` (valores por clave) y `rob`
  (juicios por dominio); `fetch_disponible_largo(n_chars)`.
- Este spec y los planes de implementación.

## 5. PR-A · `feat/ola2-procedencia` (A6, A7, A8, A10, A15, M17, D9 en proveedores, D11, D14)

### 5.1 Sink y registro por intento (D14)

`journaled()` instala `collecting()` alrededor de `compute()`; cada proveedor
llama a `emit(meta)` al terminar **cada intento** (también los fallidos, con
`outcome` e `attempt`). `RunContext.record_meta` se engancha al sink: escribe
`llm_calls.jsonl` en el acto. La línea del diario lleva las metas recogidas
(las `ok` y las fallidas de ese registro). El valor devuelto por `structured`
sigue siendo `(obj, meta)` por compatibilidad; `journaled` deduplica por
identidad.

`screen_record` deja de devolver la lista de metas como única vía (sigue
devolviéndola; el sink es la fuente de verdad). `make_provider_judge` conserva
`on_meta` como alias de `emit`.

### 5.2 `RunMeta` honesto (A6, A7)

Cada proveedor:
- pone `*_applied` con lo que de verdad envió (`gemini`: seed y temperature;
  `openai`/`zai`/`openrouter`/`local_openai`: seed y temperature; `anthropic`:
  temperature; `claude_code` y `agent`: ninguno);
- calcula `prompt_sha256` sobre el texto enviado (`claude_code` y
  `local_openai`: con el schema y el sufijo de reintento incluidos; con
  `--json-schema` el schema sale del texto y va a `schema_sha256`);
- rellena `prompt_template`/`prompt_template_sha256` desde
  `LLMRequest.prompt_template` (lo pone cada agente al renderizar:
  `load_prompt` devuelve `(texto, "agente/vN.md", sha)`);
- `model_source = backend` cuando la respuesta trae el modelo
  (`gemini.model_version`, `openai.model`, `anthropic.model`); `claude -p`
  JSON no trae el modelo: `config`;
- `backend_version` (`importlib.metadata.version(sdk)` o `claude --version`),
  `latency_ms`, `cost_usd` (`claude -p`: `total_cost_usd`).

`PROMPT_VERSIONS: dict[str, str]` en `revisia/prompts/__init__.py` fija la
versión vigente por agente; `snapshot.prompt_fingerprint()` sigue hasheando
todas las plantillas y además las especificaciones de RoB.

### 5.3 `claude -p` (A10, D11)

`ClaudeCodeProvider`:
- `probe_cli(cli) -> CliCapabilities(version, flags: frozenset[str])`
  (cacheado por proceso; `claude --help` + `claude --version`, timeout 20 s).
  `_command` añade `--json-schema <json>` si está; `--max-turns 1` si está;
  `--max-budget-usd <budget>` si está **y** hay `ANTHROPIC_API_KEY` y el
  protocolo declara `llm.<etapa>.max_budget_usd` (M17; default 1.0). Sin
  `--safe-mode` o sin `--tools` en el `--help`: `PreflightError`.
- Entorno: `_subprocess_env()` construye un dict **solo** con las variables de
  `ENV_ALLOWLIST = {PATH, PATHEXT, SYSTEMROOT, SYSTEMDRIVE, COMSPEC, WINDIR,
  TEMP, TMP, HOME, USERPROFILE, HOMEDRIVE, HOMEPATH, APPDATA, LOCALAPPDATA,
  XDG_CONFIG_HOME, XDG_DATA_HOME, LANG, LC_ALL, LC_CTYPE, TZ, TERM,
  SSL_CERT_FILE, SSL_CERT_DIR, REQUESTS_CA_BUNDLE, NODE_EXTRA_CA_CERTS,
  HTTP_PROXY, HTTPS_PROXY, NO_PROXY (y minúsculas), CLAUDE_CODE_OAUTH_TOKEN,
  ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, CLAUDE_CONFIG_DIR}` más
  `ANTHROPIC_BASE_URL`/`USE_*_OAUTH` solo si `clean_env` está apagado (como
  hoy). `REVISIA_CLAUDE_CODE_ENV_EXTRA="A,B"` añade nombres (documentado) para
  entornos corporativos. Un test fija la lista y otro comprueba que el proceso
  hijo no ve una variable ajena (`REVISIA_TEST_LEAK`).
- Reintentos: cada intento emite su meta (`invalid_output` si no valida,
  `transient_error` si el proceso falla por red/timeout/429 en stderr,
  `deterministic_error` si `is_error` con 4xx o si se agotan los intentos por
  validación). Agotados ⇒ `DeterministicCallError`.
- Clasificación de errores por proveedor (D9): `gemini`/`openai`/`anthropic`
  mapean las excepciones del SDK (429, 5xx, timeouts, conexión →
  `TransientCallError`; 400/403/404/422, bloqueo de seguridad, validación
  agotada → `DeterministicCallError`). `fake` no cambia salvo
  `fail_deterministic_at`.

### 5.4 `agent` (A8)

`AgentCallback` puede devolver `AgentReply(payload, model: str | None,
usage: dict | None)`; `AgentProvider` toma `model` del reply (`model_source:
callback`) y, si falta, el de la config (`config`) con WARN de preflight en
`validate`/`run`: «el callback no informa el modelo: dos miembros `agent`
pueden ser el mismo modelo». `agent_driver.run_review_with_agent(...,
auto_approve=False)`; el driver imprime el mensaje de pausa como el CLI.

### 5.5 `run.json.environment` y manifiesto (A15)

`snapshot.ensure_snapshot` escribe `environment` al crear la corrida (D12:
`RunInfo.prompt_sha256` se retira; una corrida con `prompt_sha256` y sin
`environment` es 0.8). `write_manifest` copia `environment`. `metodologia.md`
y `checklist_traice.md` (M2, M6, M7 de trAIce) dicen qué se aplicó:
«temperatura declarada 0,0; no aplicable en `claude_code`» cuando corresponde.

**Tests nuevos (selección):** `test_sink_registra_cada_intento_en_el_acto`,
`test_fallo_del_segundo_miembro_deja_la_llamada_del_primero_registrada` (B10),
`test_claude_code_reintento_emite_tres_metas_con_outcome`,
`test_prompt_sha256_es_del_texto_enviado_con_schema_y_sufijo` (A7, con los
hashes `57b517…`/`2f1666…` del hallazgo reproducidos en espíritu),
`test_applied_none_en_claude_code_y_seed_none_en_anthropic` (A6),
`test_probe_cli_sin_safe_mode_es_error_de_preflight`,
`test_json_schema_solo_si_el_cli_lo_anuncia`,
`test_subprocess_env_es_allowlist_y_no_filtra_variables_ajenas`,
`test_max_budget_solo_con_api_key`, `test_agent_reply_informa_el_modelo`,
`test_agent_driver_no_auto_aprueba_por_defecto`,
`test_environment_en_run_json_y_manifest_coinciden`,
`test_prompt_template_sha_coincide_con_environment` (relación 19),
`test_error_4xx_es_determinista_y_429_transitorio` por proveedor.

## 6. PR-B · `feat/ola2-identidad-registros` (A4, A5, D19)

- `revisia/ingest/doi.py`: `normalize_doi(value) -> str | None`: `strip`,
  URL-decode, quita (sin distinguir mayúsculas) `https?://(dx\.)?doi\.org/`,
  `doi:`, `info:doi/`; `lower()`; quita puntuación final `.,;)]`; exige
  `^10\.\d{4,9}/\S+$`; si no, `None`. `doi_url(doi) -> str`.
- `SearchRecord.doi`: `field_validator` que aplica `normalize_doi` (un DOI que
  no normaliza queda `None` y el original va a `extra["doi_raw"]`). Los
  backends dejan de normalizar por su cuenta (`busqueda._normalize_doi`,
  `open_backends._doi`, los `lower().strip()` de `search_backends` y `ncbi`,
  `manual_import._record_id`) y usan `normalize_doi` para el `record_id`.
- `dedup.dedup_key`: `doi:<norm>` si hay DOI; si no, `title:<clave>` con
  `unicodedata.normalize("NFKD")`, sin diacríticos, solo `[a-z0-9]`; si el
  título es de relleno (`PLACEHOLDER_TITLES = {"", "(sin título)",
  "untitled", "[no title]", "sin título", "no title"}`, tras normalizar) la
  clave es `none:<record_id>` y el registro **nunca se fusiona**;
  `DedupReport.unmerged_placeholders: int`.
- `manual_import.parse_bibtex`: tokenizador de entradas (`@tipo{clave,` …
  `}` con conteo de llaves), campos `nombre = {…} | "…" | número`, llaves
  anidadas aplanadas, `#` concatenación simple; RIS: sin cambios funcionales.
  El `doi` del registro importado queda normalizado (hoy con prefijo).
  `parse_records_json` (D23): `imported/*.records.json` como `list[SearchRecord]`
  validada, con `source_db` conservado y `record_id` intacto; en el log de
  búsqueda, `kind: manual_import` con `format: records_json`.
- Ids estables entre corridas: con el DOI normalizado al construir, el mismo
  artículo de dos fuentes produce el mismo `record_id` y una sola clave; el
  renombrado `#n` queda para colisiones reales (mismo id, distinto DOI o sin
  DOI).

**Tests:** la evidencia de A4 (`https://doi.org/10.1000/ABC` en RIS +
`10.1000/abc` en OpenAlex → **un** registro, sin `#2`), la de A5 (`title =
{The {IMF} and growth}` conserva el título; dos `(sin título)` siguen siendo
dos), `test_normalize_doi_tabla` (parametrizado: prefijos, mayúsculas, `doi:`,
URL-encoded, puntuación final, no-DOI), `test_todos_los_backends_normalizan_el
doi_al_construir` (recorre `BACKENDS` con fixtures de respuesta),
`test_dedup_nfkd_fusiona_titulos_con_y_sin_acentos`.

## 7. PR-C · `feat/ola2-texto-completo-extraccion` (M14, A16, D3, D4, D9 en pipeline, D20, D21, D22)

### 7.1 Texto completo (D20, D21)

- `ReviewProtocol.fulltext: {max_chars: int = 120_000}`; `fetch_fulltext(…,
  max_chars)` recibe el del protocolo; `FullText.truncated`, `n_chars_total`.
- Rescate con texto: `ft_policy` acepta `text_file` en `rescue_ids`; `_validate`
  comprueba que esté bajo `screening_ft/rescues/` (sin `..`, sin absolutos) y
  exista; `_register` escribe `rescue_text` junto a la `label`. Al reanudar,
  `_fulltext` ingiere los rescates con texto (`ingest_rescue(path) -> FullText`:
  PDF con `pypdf`, HTML con `strip_html`, TXT/MD tal cual; `source:
  human_rescue`), escribe la caché y actualiza `retrieval.json`. `inputs` de
  extracción/RoB/verificación cambian con el `text_sha256` nuevo: se recalculan
  (es lo correcto: antes no tenían texto).
- `metodologia.md`: lista de estudios recortados (id, `n_chars_total`,
  `max_chars`) y de rescates con y sin texto.

### 7.2 Extracción sobre texto completo (M14, D22)

- `extract_record(provider, *, record, form_fields, text: str | None,
  temperature, seed)`: la plantilla `extraccion/v2.md` recibe el texto
  completo delimitado (D10) o, si no hay, el resumen con la indicación
  explícita «solo resumen»; `ExtractionRecord.source_text`, `text_sha256`,
  `truncated`.
- Validación de la salida: claves fuera del formulario se descartan con nota;
  claves ausentes se rellenan `not_found`; `quote_status` por campo con
  `find_quote(quote, text) -> (status, offset)`.
- Fallo determinista (D9): `ExtractionRecord(status="failed")` con campos
  vacíos; `editable` incluye todas sus claves; aprobar exige editarlas todas o
  rechazar.

### 7.3 Corrección por campo (D3)

- `gates.extraction_payload` añade `attention`, `editable`, `concordance`;
  `gates.extraction_policy(...) -> FieldPolicy(editable: dict[str,
  frozenset[str]], required: dict[str, frozenset[str]])`.
- `review_gate(..., fields=policy)`; `_validate` aplica las reglas de §4.2;
  `_register` escribe `edit_field` antes del `approve`; `GateResult.edits`.
- `gates.apply_field_edits(extractions, edits, actor)` → `human_*`,
  `human_edited`, `status="verified"`; se reescribe `extractions.json`
  **después** del gate (como `decisions.json` tras T/A). La síntesis recibe
  valores finales (`_studies_block` usa `final_value` y marca `†` los editados).
- Plantilla `decision.template.yml`: por estudio, cada campo con su valor
  propuesto, `quote_status` y la marca de `attention` en comentario, y
  `fields: {}` vacío para rellenar.

### 7.4 Concordancia IA–IA (D4, A16)

`extraction_agreement.py`: `normalize_value(v)`: NFKC, `casefold`, espacios
colapsados, comillas y guiones unificados; si ambos valores contienen números,
se comparan los multiconjuntos de números (con `,`/`.` decimal y `%`
normalizados); `value_agreement` sobre pares con ambos valores no nulos;
`presence_kappa` `None` con nota si no hay varianza; `disagreements`.
`select_double_extraction_subset` no cambia. Docstrings y
`metodologia.md`/`checklist_traice.md` con la frase de D4; README y
AGENTS.md sin «doble 20 %» (los edita el integrador).

**Tests:** `test_extraccion_recibe_el_texto_completo_delimitado`,
`test_source_quote_exacta_normalizada_y_no_encontrada`,
`test_campo_con_cita_no_encontrada_sale_en_attention`,
`test_edicion_por_campo_queda_en_ledger_y_en_extractions`,
`test_editar_clave_fuera_de_editable_es_error`,
`test_editar_sin_razon_es_error`, `test_sintesis_usa_el_valor_final`,
`test_rescate_con_texto_se_ingiere_al_reanudar_y_llega_a_rob`,
`test_rescate_fuera_de_rescues_es_error`, `test_recorte_registrado_y_declarado`,
`test_fallo_determinista_en_ta_pasa_a_must_label` (M15: dos reanudaciones
seguidas no repiten la llamada ni salen con rc 3),
`test_concordancia_normaliza_numeros_y_unidades` (`'240'` = `'240 patients'`),
`test_presence_kappa_none_sin_varianza_con_nota`,
`test_pipeline_fake_con_edicion_de_campo_audita_sin_fail` (frontera, con PR-G).

## 8. PR-D · `feat/ola2-verificador` (C2, D2, D10, D15, D22, D24)

- `config.py`: `grounding: Literal["existence","judge","embedder"] =
  "existence"` (`agent` se acepta como alias de `judge` con aviso de
  deprecación un ciclo); `llm.verificador` opcional; `verificador:
  {max_source_chars: int = 12_000}`; validador: `judge` sin `verificador` →
  error; `verificador == sintesis` (`provider:model`) → error; mismo `VENDOR`
  → aviso. `preflight` lo reporta; `embedder` → aviso «experimental: no sirve
  para una corrida publicable». `verificador` entra en `STAGES`/`LLMStage`
  como etapa con proveedor (sin gate propio: su gate es `reporte`).
- `revisia/agents/verificador.py`: `split_claims(narrative, corpus_ids) ->
  list[Claim]` (segmentación por oraciones con abreviaturas comunes en es/en;
  `cited_ids` por coincidencia exacta con el corpus; candidatos con forma de id
  pero fuera del corpus; `numbers` por regex de cifras, porcentajes y rangos);
  `verify_narrative(stage, text, corpus_ids, *, sources, mode, judge=None,
  embedder=None, threshold=0.12) -> VerificationReport`, con la regla de
  `grounded` de §4.2, `numbers_missing` por comparación normalizada de cifras,
  y una comprobación por **par** (afirmación, cita).
- `revisia/rag/grounding.py`: la plantilla pasa a `prompts/verificador/v1.md`
  (fuente delimitada, D10; instrucción de citar literal y de confirmar cada
  cifra); `GroundingVerdict` + `numbers_confirmed: list[str]`;
  `make_provider_judge(provider, cfg, *, on_meta)` registra `prompt_template`.
  `source_window(claim, source, *, abstract, max_chars) -> Window(text,
  truncated, sha256)` construye la ventana determinista de D15 (párrafos por
  `\n\n` o, sin ellos, bloques de ~1 500 caracteres); `support_quote` se busca
  en la **fuente completa**, no solo en la ventana.
- Pipeline: `_verify_one` usa `provider_for("verificador")` en `judge`; cada
  comprobación va al diario `verification.jsonl` como `check:<i>:<id>`
  (`inputs = {claim, cited_id, fuente_sha256, modo, juez}`), de modo que un
  fallo a mitad no repite las ya hechas; el informe se consolida al final. Las
  afirmaciones cuantitativas sin cita van a `verification.json` y a
  `metodologia.md` («n afirmaciones con cifras sin cita; revisadas por el
  humano en el gate final»).
- `report_payload`: `verification.mode/judge/n_claims/n_uncited_quantitative`;
  `flagged[].numbers_missing`. La política de adjudicación (D8 de la Ola 1) no
  cambia.
- `FakeProvider`/`ScriptedProvider` como juez: fail-closed por defecto
  (`grounded: false` salvo que la afirmación contenga una palabra del guion):
  el test `tests/test_grounding.py:15` que consagraba «todo grounded» cambia.

**Tests (reproducen la tabla de C2):** fuente «sensitivity 0.91, specificity
0.62, reduced workload 40 %»; afirmación correcta → grounded; «sensitivity
0.55» → `numbers_missing=["0.55"]`, marcada **sin** llamar al juez;
«specificity 0.99, worse than human» → marcada; «reduced mortality in sepsis»
→ el juez fake la rechaza; solo *stopwords* → sin cifras ni cita, no es
afirmación; cita repetida `[r1]` con segunda afirmación absurda → **dos**
comprobaciones, la segunda marcada; `[2019]` no es cita; síntesis sin citas con
incluidos → WARN del auditor; fuente vacía → `source_available: false`,
marcada; `judge` con el mismo modelo que `sintesis` → rc 2 en `validate`;
mismo fabricante → aviso; `existence` → auditor FAIL (PR-G).

## 9. PR-E · `feat/ola2-rob-por-herramienta` (A12, D5, D22)

- `revisia/rob/`: `tools/*.yml` (PR-0), `aggregate.py` con `rob2(domains)`
  (algoritmo de Cochrane: *high* si algún dominio *high* o varios *some
  concerns* que bajan la confianza; *some concerns* si alguno; *low* si todos),
  `robins_i(domains)` (*critical* > *serious* > *moderate* > *low*; *no
  information* propaga), `amstar2(items, critical)` (*high* sin fallos
  críticos y ≤ 1 no crítico; *moderate* > 1 no crítico; *low* 1 crítico;
  *critically low* > 1 crítico), `nos_stars(items)` (suma; umbrales AHRQ
  opcionales en la especificación), QUADAS-2 sin global.
- `agents/rob.py`: `assess_rob(provider, *, spec, record, extraction, text)`
  con la plantilla `rob/v2.md` **parametrizada por herramienta** (dominios,
  preguntas señalizadoras y escala vienen de la especificación; texto
  delimitado, D10); la salida se valida contra la especificación (ids,
  escala); dominios ausentes ⇒ un reintento con la lista de faltantes; si
  persiste ⇒ `DeterministicCallError` (D9). `quote_status` por dominio.
  `overall_llm` se guarda; `overall_algorithm` se calcula.
- Gate (D5): `rob_payload` + `editable`, `attention`, `tool_version`,
  `overall_algorithm`; `rob_policy -> DomainPolicy`; `edit_domain`;
  `apply_domain_edits` recalcula `overall_algorithm` con los juicios finales y
  fija `overall`. Plantilla `decision.template.yml` por estudio y dominio.
- Exports: `riesgo_de_sesgo.md` por herramienta (tabla de dominios con la
  escala propia; AMSTAR-2 con los 16 ítems y los críticos marcados; NOS con
  estrellas); `robvis.csv` según `robvis_template` (RoB2/ROBINS-I/QUADAS-2
  nativos; `generic` para NOS y AMSTAR-2 con la escala mapeada y una nota).
- `config.rob_tool: GRADE` → error de preflight: «GRADE no es una herramienta
  de riesgo de sesgo por estudio; queda fuera hasta la etapa de certeza por
  desenlace». `RoBTool` gana `NewcastleOttawaCaseControl` (D5);
  `NewcastleOttawa` sigue siendo el formulario de cohortes, así que ningún
  protocolo existente cambia de significado.

**Tests:** por herramienta, un vector con los dominios oficiales (p. ej.
AMSTAR-2: 16 ítems, 7 críticos; QUADAS-2: 4 + 3); los algoritmos de agregación
con los ejemplos de los manuales (RoB 2: un *high* ⇒ *high*; AMSTAR 2: dos
fallos críticos ⇒ *critically low*); respuesta con dominio desconocido se
rechaza; dominio ausente ⇒ reintento ⇒ fallo determinista; edición por dominio
en el ledger y recálculo del global; `GRADE` → rc 2; robvis por plantilla.

## 10. PR-F · `feat/ola2-meta-benchmark` (C3-benchmark, D6, D16, D23)

### 10.1 Meta-análisis (D16)

- `meta_analysis.py`: `meta_analyze(effects, measure, *, random_method="DL")
  -> MetaAnalysisResult` v2 por desenlace; `prediction_interval` (Higgins,
  Thompson y Spiegelhalter 2009; t con k − 2 gl, k ≥ 3); `egger` solo k ≥ 10
  (Sterne 2011) con `egger_note` si no; `subgroups` por `subgroup` con Q
  entre grupos; `duplicates` (pares `(yi, vi)` idénticos a 1e-9);
  `random_method: HKSJ` opcional (IC con t y varianza ajustada).
- `_meta_analysis(run, included_ids)`: filtra, escribe `excluded_effects.json`,
  declara en `meta_analisis.md` y `metodologia.md`; con k < 2 escribe
  `meta_analysis.json: null`-equivalente (`{"outcomes": [], "excluded": n}`) y
  lo declara.
- `protocol_files.EffectsFile` v2: `outcome` obligatorio (un `effects.yml`
  sin `outcome` da rc 2 con el mensaje de migración), `multiple_per_study`,
  `random_method`.
- `interop/effects_metafor.csv` por desenlace; `forest`/`funnel` por desenlace
  (funnel solo si k ≥ 10).

### 10.2 `revisia benchmark` (D6, D23)

- CLI: `revisia benchmark <protocol_dir> --panel panel.yml [--replicas N]
  [--out benchmarks/] [--max]`; `revisia benchmark-report <benchmark_dir>…
  [--out]`.
- Requisitos del protocolo (preflight de benchmark, rc 2 si fallan): todas las
  bases son manuales con `imported/` (corpus congelado: `*.records.json`
  nativo, D23, o RIS/BibTeX) y hay `gold.yml` con ≥ 2 clases cuyos ids están
  todos en el corpus importado; `screening_ta` sin ensemble (lo fija el panel
  por celda). `manual_import.parse_records_json` (PR-B lo añade junto al
  parser BibTeX nuevo) valida `list[SearchRecord]` y conserva `record_id`.
- Ejecución: por celda × réplica, un `RunContext` bajo `runs/<celda>-r<k>/`
  con `kind: benchmark`, el protocolo instanciado con el proveedor de la celda
  (`protocol.model_copy` con `llm.screening_ta`), `run_pipeline(...,
  stop_after="screening_ta")` (parámetro nuevo; en `benchmark` no hay gates ni
  entregable) y `metrics.json`. Reanudable: una celda con `metrics.json` no se
  repite. Fallos deterministas de registros cuentan en `n_failed_records` y se
  excluyen de la matriz con nota.
- `benchmark.json`/`benchmark.md`: tabla celda × réplica y resumen por modelo
  (media y rango de recall, IC de Wilson de la agregación de réplicas).
- `benchmark-report`: toma uno o más `benchmark.json` (corpus distintos),
  construye efectos `logit(recall)` por (corpus, modelo, réplica) con
  `outcome = "recall"`, `subgroup = corpus`, agrupa por modelo con `meta_analyze`
  (PI, sin Egger bajo k = 10, duplicados), y escribe `pooled/meta_analysis.json`
  y `pooled/report.md` con la advertencia de unidad de análisis cuando un
  corpus aporta más de una réplica (se promedia por corpus antes de agregar,
  salvo `--replicas-as-effects` documentado como exploratorio).
- Auditor: una corrida `kind: benchmark` se audita con el mensaje de D23.

**Tests:** `effects.yml` de C3 (27 de 28 de un artículo) ya no carga sin
`multiple_per_study`; con él, carga y queda declarado; efecto de un no
incluido → `excluded_effects`; k = 1 tras filtrar → sin meta-análisis
declarado; PI con los valores de `metafor::predict` sobre `dat.bcg` (4
decimales); Egger `None` con k = 9; HKSJ contra `metafor(method="REML",
test="knha")` no (REML queda fuera): HKSJ sobre DL contra el cálculo manual;
benchmark con el demo importado y `ScriptedProvider` en dos celdas × 2
réplicas → `benchmark.json` válido, corridas `kind: benchmark` sin ledger;
`benchmark-report` sobre dos benchmarks sintéticos → subgrupos por corpus.

## 11. PR-G · `feat/ola2-auditor` (D2, D12, D17, D23, D26, relaciones 19–31)

### 11.1 Partición (D26)

Primer commit: mover funciones a los módulos de D26 sin cambiar una línea de
lógica; `CHECKS` no cambia; la suite entera en verde. Un test fija que ningún
módulo de `revisia/audit/` supera 900 líneas.

### 11.2 Checks nuevos y cambiados

| id | Etapa | PASS | WARN | FAIL |
|---|---|---|---|---|
| `environment` (N) | — | `run.json.environment` válido y `== manifest.environment`; versión SemVer; plantillas y especificaciones hasheadas | `git_commit` nulo; `git_dirty` | ausente (D12: «anterior a la Ola 2»); distinto del manifiesto; alguna llamada con `prompt_template` fuera de `prompt_templates` o con hash distinto (relación 19) |
| `prompts` (M) | reporte | cada llamada `ok` con `prompt_sha256`, `response_sha256`, `prompt_template`, `outcome` | intentos fallidos > 20 % de las llamadas | llamada sin `outcome`/`attempt` (esquema v1) |
| `grounding` (M) | sintesis | modo `judge`, juez ≠ redactor, afirmaciones recalculadas iguales, ninguna marcada | juez del mismo fabricante (D24); `n_uncited_quantitative > 0`; marcadas todas adjudicadas (como hoy) | modo `existence`/`embedder` (**D2**); juez == redactor; afirmaciones recalculadas ≠ `checks`; `grounded` recalculado ≠; comprobación `judge` sin su línea/llamada; lo de hoy |
| `extraction` (N) | extraccion | relaciones 24–26 verificadas; ediciones ⇔ ledger | `quote_status: not_found` en campos sin edición humana aprobados (lista) | relación rota; `status: failed` sin editar todas sus claves |
| `rob` (N) | rob | relación 27 | juicios sin `support_quote` | dominios ≠ especificación; escala violada; `overall` ≠ regla; edición sin ledger o viceversa; `GRADE` |
| `meta_analysis` (N, absorbe la parte de `arithmetic`) | sintesis | relación 29; recálculo igual | `multiple_per_study.allowed` (declararlo); duplicados detectados | relación 29 rota; efectos de no incluidos agregados; `egger` con k < 10 |
| `deposit` (N) | — | sin `deposit.json`: `N/A`-equivalente «no es copia de depósito» (PASS); con él: relación 30 | — | relación 30 rota; fichero retenido presente |
| `arithmetic` (M) | reporte | + relaciones 21, 22; `agreement.json` recalculado (26) | — | — |
| `timing` (M) | — | las heurísticas usan solo llamadas `ok`; los intentos fallidos se validan por orden (`attempt` creciente dentro de `(stage, record_id, role)`) | — | `attempt` fuera de orden |
| `response_overlap` (M) | reporte | — | + dos miembros `agent` con `model_source: config` y el mismo `model` | — |
| `manifest`, `provenance` (M) | — | `kind: benchmark` ⇒ mensaje de D23 en `provenance`, resto `N/A` sin cascada | — | — |

`derive_state` entiende `kind: benchmark` (`status: benchmark`, `reached`
hasta `screening_ta`). `publishable` sigue siendo `n_fail == 0` y es `False`
en benchmark.

### 11.3 `revisia deposit` (D17)

En `revisia/exports/deposit.py`: `make_deposit(run_dir, out_dir) ->
DepositInfo`; copia todo salvo `04_fulltext/texts/` y
`screening_ft/rescues/`, escribe `deposit.json`, y la CLI imprime los hashes
retenidos. `revisia audit <deposit_dir>` da el mismo veredicto que la corrida
original (test de frontera).

**Tests:** por check, la fixture real de `conftest.py` (que PR-C/PR-D/PR-E
amplían con edición de campo, edición de dominio, rescate con texto y juez
fake) y un síntoma a la vez: `existence` → FAIL `grounding`; juez igual al
redactor (editando `verification.json`) → FAIL; afirmación añadida a
`documento.md` sin check → FAIL; `human_value` sin `edit_field` → FAIL;
dominio renombrado → FAIL; `overall` manipulado → FAIL; efecto de no incluido
agregado → FAIL; `environment` ausente → FAIL con el mensaje de D12; corrida
0.8 real (fixture `write_run_v08`) → FAIL `environment` y el resto diagnóstico;
depósito → mismo veredicto; depósito con un texto dentro → FAIL; benchmark →
no publicable sin cascada; `agreement.json` manipulado → FAIL (recalculado).
Y la **frontera**: `test_pipeline_fake_con_humano_judge_audita_sin_fail`,
`test_pipeline_existence_no_es_publicable`,
`test_pipeline_auto_approve_no_es_publicable` (sigue), C3 (sigue, ahora por
≥ 12 checks).

## 12. PR-H · `feat/ola2-ci-tests` (M22, M24, A13, M18–M21, D25)

- `pyproject.toml`: `requires-python >= 3.11`; `target-version = "py311"`
  (ruff y black); `pytest-cov` en `dev`; `[tool.coverage.run] source =
  ["revisia"]`, `omit` solo para `cli.py:main` no; `fail_under = 80`.
  `uv lock` regenerado para 3.11.
- `.github/workflows/ci.yml`: `permissions: contents: read`; job `lint`
  (ruff, black, `uv lock --check`) y job `test` con `strategy.matrix: os
  [ubuntu-latest, windows-latest] × python [3.11, 3.12, 3.13]`,
  `fail-fast: false`, caché de `uv` (`enable-cache`), `uv sync --extra dev
  --extra search --extra meta` (+ `--extra pdf` y Pango solo en Ubuntu),
  `pytest -n auto -m "not cronometrado"` + `-m cronometrado`; cobertura con
  `--cov --cov-report=xml` en `ubuntu/3.13` y `fail_under`; job `build`:
  `uv build` y `python -m zipfile -l` del wheel (humo del empaquetado). Acciones
  fijadas por SHA.
- Tests de entrypoints (A13): `orchestration/flow.run_review` con proveedor
  fake de punta a punta; `agent_driver` con callback de prueba (y
  `auto_approve=False`); CLI `run`/`validate`/`gold-template`/`new`/`export`
  por `main([...])` en subproceso para `run` (códigos 0/2/3).
- Parsers Crossref y Semantic Scholar (M18) con fixtures JSON reales
  recortadas; ruta de fallback de texto completo (M19: Unpaywall → PDF/HTML,
  con `httpx.MockTransport`); proveedores API (M20) con transports falsos que
  verifican el `RunMeta` v2 (`*_applied`, `model_source`,
  `backend_version`).
- Pico de memoria: `_SCRIPT_MEDIDO` precalienta los imports perezosos del
  auditor (`revisia.meta_analysis`, `scipy.stats` si existe, `yaml.CSafeLoader`)
  **antes** de `tracemalloc.start()`, y la cota se documenta como «memoria del
  auditor, no de los imports». El test deja de depender de qué extras hay.
- Windows: los tests que escriben rutas largas usan `tmp_path` corto; los
  `cronometrado` tienen tolerancia ×2 en Windows (`sys.platform`).

**Criterio:** CI verde en las 6 celdas; cobertura ≥ 80 %; `uv build` limpio.

## 13. PR-I · `feat/ola2-cierre` (M16, D7, D27 y documentación)

Solo el integrador. README (verificador por juez, modo por defecto
`existence` y qué significa, procedencia aplicada, RoB por herramienta sin
GRADE, concordancia IA–IA, `revisia benchmark`, `revisia deposit`, CI
multiplataforma, nota de limitación M15 eliminada, badge de tests), AGENTS.md
(tabla del equipo: `verificador` como agente LLM con juez propio; RoB sin
GRADE; `extraccion` con corrección por campo), `docs/arquitectura.md`,
`docs/benchmark-cribado.md` **reescrito** (método y comando; sin 0,820 ni I²
90,7 % salvo en una nota histórica que remite a la auditoría),
`docs/metodologia/` (nota sobre GRADE y sobre la unidad de análisis),
`.env.example` sin `QDRANT_*`, extra `rag` eliminado, `CHANGELOG.md` con
«Cambios incompatibles» (§18.4), auditoría §11 «Ola 2 · motor cerrado» con la
tabla hallazgo→estado y la frase «pendiente: re-auditoría y corrida real
(D1)», `RELEASING.md` (matriz, `-m cronometrado`, `uv lock --check`),
`CITATION.cff` 0.9.0, bump de versión en los tres sitios.

## 14. Fase humana: re-auditoría, corrida real y 1.0.0 (D1, D8, D17, D18)

### 14.1 Re-auditoría del código

Sobre el tag `v0.9.0`, cinco agentes independientes en paralelo, solo lectura,
con el mismo reparto del 2026-09-03 (núcleo del pipeline; seguridad y cadena
de suministro; rigor metodológico y estadístico; tests, reproducibilidad y
empaquetado; capa LLM/RAG/memoria), con la auditoría original y este spec
como entrada, y la instrucción de **reproducir** cada hallazgo. Un
consolidador escribe `docs/auditoria/<fecha>-reauditoria.md` con el mismo
formato (veredicto, recuento, hallazgos con `fichero:línea` y evidencia, lo
que está bien, límites) y una tabla «hallazgo 2026-09-03 → estado». Criterio
de paso: **ningún hallazgo crítico o alto de los que esta ola declara cerrar
sigue abierto**; lo demás se lista con severidad y entra en 0.9.x (si bloquea
la corrida real) o en el backlog. Las correcciones se publican como 0.9.x
antes de la corrida real.

### 14.2 Corrida exploratoria y preparación del protocolo (D18)

El protocolo vive en `C:\revisia\protocols\prisma-ia-origen\` (git-ignorado;
pertenece a la revisión, D11 de la Ola 1). El arquitecto:

0. Actualiza el CLI `claude` a una versión ≥ `MIN_CLI_VERSION` (D11) y ejecuta
   la sonda de PR-0 si no lo hizo antes de PR-A.
1. Actualiza `protocol.yml`: `grounding: judge`; `llm.verificador` de otro
   fabricante que `sintesis` (p. ej. `sintesis: claude_code opus`,
   `verificador: zai glm`); el bloque `llm` pasa de `agent` a `claude_code`
   (la corrida se lanza por CLI, no desde una sesión); `ensemble_llm.screening_ta`
   con dos modelos distintos; `rob_tool: AMSTAR2` (es una revisión de
   revisiones) o el que corresponda al diseño de los incluidos; `fulltext.max_chars`.
   La elección de modelos es suya; el motor solo exige las reglas de D2/D24.
2. Corre `revisia run` exploratoria (puede usar `--auto-approve`; no es
   publicable) hasta el final.
3. `revisia gold-template <run>` → etiqueta `gold.yml` (recomendado: todos los
   registros tras dedup; mínimo, ≥ 20 positivos para que `recall_target 0.95`
   tenga potencia, D7 de la Ola 1).
4. Con las extracciones aprobadas de la exploratoria, escribe `effects.yml` v2
   (un efecto por estudio incluido y desenlace, `outcome`, sin repetir estudio
   salvo justificación) **o** decide que esta revisión no agrega efectos (el
   meta-análisis del artículo es el benchmark, D6) y no incluye `effects.yml`.
5. Copia `gold.yml` (y `effects.yml`) al protocolo.

### 14.3 Corrida real

`revisia run protocols/prisma-ia-origen --mailto …` con el motor 0.9.x; el
arquitecto responde los cinco gates (`screening_ta` A1 con excepciones;
`screening_ft` A0 registro a registro, con rescates y sus PDF si los tiene;
`extraccion` A0 con correcciones por campo; `rob` A0 por dominio; `reporte`
A1 con adjudicación de citas marcadas). Estimación: 6–12 horas repartidas en
días; el motor lo permite (`--resume`). `revisia audit` → **APTA**;
`revisia deposit` → carpeta de depósito; Zenodo con el DOI de la corrida
enlazado desde README y CITATION; re-auditoría de la corrida (un agente,
solo lectura, sobre la copia de depósito: coherencia, procedencia, horas).
Si la corrida destapa un defecto del motor, se corrige (0.9.x), se reanuda o
se repite lo necesario, y se documenta en §19.

### 14.4 1.0.0

Con la corrida depositada y la re-auditoría limpia: auditoría §11 «Ola 2
cerrada; veredicto revertido», README sin la sección «auditoría abierta»,
`CHANGELOG` 1.0.0 (solo documental respecto a 0.9.x), tag, release, DOI.

## 15. Topología y orden de merge

Cadena apilada como en las olas anteriores. H va primero para que todas las
pistas corran ya en la matriz; las pistas que tocan `pipeline.py` van en
secuencia (B → C → D → E → F); A, E (datos y agente), F (módulo
`meta_analysis` y CLI) y G (fase 1) se desarrollan en paralelo desde PR-0.

| PR | Rama | Se desarrolla desde | Base de la PR | Cierra | En paralelo con |
|---|---|---|---|---|---|
| 0 | `feat/ola2-contratos` | `main` | `main` | spec, contratos | — |
| H | `feat/ola2-ci-tests` | 0 | 0 | M22, M24, A13, M18–M21 | A, B, E₁, F₁, G₁ |
| A | `feat/ola2-procedencia` | 0 | H | A6, A7, A8, A10, A15, M17, D9 (prov.), D14 | H, B, E₁, F₁, G₁ |
| B | `feat/ola2-identidad-registros` | 0 | A (tras rebase) | A4, A5 | H, A, E₁, F₁, G₁ |
| C | `feat/ola2-texto-completo-extraccion` | B rebasada | B | M14, A16, D3, D4, D9 (pipeline), D20–D22 | E₁, F₁, G₁ |
| D | `feat/ola2-verificador` | C | C | C2, D2, D10, D15, D24 | E₁, F₁, G₁ |
| E | `feat/ola2-rob-por-herramienta` | 0 (E₁: datos, `aggregate.py`, agente) → D (E₂: gate y pipeline) | D | A12, D5 | — |
| F | `feat/ola2-meta-benchmark` | 0 (F₁: `meta_analysis`, esquemas, `benchmark-report`) → E (F₂: `_meta_analysis`, `revisia benchmark`, `stop_after`) | E | C3-benchmark, D6, D16, D23 | — |
| G | `feat/ola2-auditor` | 0 (G₁: partición D26, `environment`, `deposit`) → F (G₂: checks nuevos) | F | relaciones 19–31, D12, D17, D26 | — |
| I | `feat/ola2-cierre` | G | G | M16, D7, D27, docs | — |

Solapes verificados y resolución:

| Fichero | Pistas | Resolución |
|---|---|---|
| `orchestration/pipeline.py` | A (sink en `journaled`, `environment`), C, D, E₂, F₂ | A solo toca `journal.py`/`snapshot.py`; el resto en secuencia B→C→D→E→F |
| `orchestration/gates.py`, `hitl.py` | 0 (modelos), C (campos), E₂ (dominios) | Secuenciales; C define `FieldPolicy`, E₂ reutiliza el patrón |
| `llm/providers/*` | A | Solo A |
| `agents/{busqueda,open_backends,search_backends,ncbi,dspace}.py`, `ingest/*` | B | Solo B |
| `agents/extraccion.py`, `extraction_agreement.py`, `agents/fulltext.py` | C | Solo C |
| `agents/verificador.py`, `rag/*`, `prompts/verificador/` | D | Solo D |
| `agents/rob.py`, `rob/*`, `exports/interop.py` (robvis) | E | Solo E |
| `meta_analysis.py`, `schemas/effects.py`, `protocol_files.py` (efectos), `cli.py` (benchmark) | F | Solo F; `cli.py` también lo toca G (`deposit`) y A (`agent_driver` no) → funciones distintas |
| `prompts/*/v2.md` | C (extracción), D (verificador), E (rob), y D10 en screening (C) | Cada pista crea su plantilla; `PROMPT_VERSIONS` lo edita cada una en su clave |
| `exports/methods.py`, `checklist.py` | A, C, D, E, F | Secuenciales por el orden de merge; A va primero |
| `audit/*` | G | Solo G (G₁ parte desde 0; G₂ rebasa sobre F) |
| `pyproject.toml`, `ci.yml` | H (todo), I (extra `rag`), A (`pytest-cov` no) | H primero; I al final |
| `tests/conftest.py`, `hitl_helpers.py` | C, D, E (fixtures nuevas), G | Aditivo; G consume |

Cada pista en su worktree (`C:\revisia-wt\<pista>`). Los implementadores **no
tocan** `CHANGELOG.md`, `README.md`, `AGENTS.md`, `docs/auditoria/` ni este
spec: el integrador los actualiza al cerrar cada PR. Merge: lo decide el
arquitecto; con PRs apiladas **nunca** `--delete-branch` mientras otra PR use
la rama como base (merge sin borrar → `gh pr edit <n> --base main` → borrar
→ cerrar y reabrir para disparar el CI).

## 16. Método de trabajo

TDD estricto: un test rojo por hallazgo antes de cada arreglo, y los tests
reproducen la evidencia de la auditoría (la tabla de C2, el RIS de A4, el
BibTeX de A5, los hashes de A7), no una versión suavizada. Todos offline y
deterministas; ningún test invoca `claude`, APIs ni WeasyPrint real salvo el
de CI ya existente.

Cada tarea pasa por un implementador (subagente nuevo, TDD), un revisor
(subagente nuevo: primero cumplimiento del spec, después calidad) y las
correcciones; desviaciones del spec descubiertas en revisión se corrigen y se
registran en §19, no se consultan (salvo que cambien una decisión D1–D6).

Criterio de cierre de cada PR: CI verde en la matriz de D25 (6 celdas);
`uv run ruff check .`, `uv run ruff format --check .`, `uv run black --check .`,
`uv lock --check` limpios; cobertura ≥ 80 %.

Criterio de cierre del motor (0.9.0), de punta a punta con el demo y el
proveedor fake por CLI:
- `revisia run` (`grounding: judge`, `verificador` fake distinto) → pausas en
  los cinco gates → `decision.yml` con etiquetas, una edición de campo, una
  edición de dominio, un rescate con texto y una adjudicación → `--resume` →
  `revisia audit` **APTA** (con los WARN de demo);
- la misma corrida con `grounding: existence` → **NO publicable** por
  `grounding`;
- con `--auto-approve` → NO publicable (sigue);
- la reconstrucción C3 → NO publicable por ≥ 12 checks;
- una corrida 0.8 real (fixture) → NO publicable por `environment`, resto en
  diagnóstico;
- `revisia deposit` de la corrida APTA → el depósito audita APTA;
- `revisia benchmark` sobre el demo importado con dos celdas fake →
  `benchmark.json`; `benchmark-report` → `pooled/`.

Criterio de cierre de la ola (1.0.0): §14.

## 17. Fuera de alcance (Ola 3 y posteriores)

- GRADE como etapa de certeza por desenlace (requiere síntesis por desenlace).
- Edición de texto libre en la extracción; interfaz (CSV/TUI) para revisar
  miles de registros.
- Paralelismo de llamadas; presupuesto global por corrida en proveedores API
  (M17 solo en `claude_code`); reintentos con backoff en API (el transitorio se
  reanuda).
- Prefect; `rc` de `paused`; migración de corridas 0.8; firma criptográfica del
  manifiesto o encadenado del ledger.
- Hartung-Knapp como default, REML, meta-regresión, análisis de sensibilidad
  *leave-one-out*.
- Verificación de `source_quote` por embeddings; detección de inyección (solo
  se delimita, D10).
- Doble extracción humana ciega (D4).
- Living review automático a partir del benchmark.

## 18. Riesgos asumidos

1. **Horas del arquitecto (D1).** La ola no cierra sin su corrida real.
   Mitigación: todo lo autónomo va primero (D8) y la corrida es reanudable por
   gates; si las horas no llegan, 0.9.x queda publicado y la ola queda abierta
   de forma explícita en la auditoría §11.
2. **El verificador estricto marca de más (D15).** Las cifras derivadas
   («reducción del 40 %» frente a «de 100 a 60») salen `numbers_missing`. El
   humano adjudica (D8 de la Ola 1) con razón; el auditor deja WARN. Si en la
   corrida real supera el 30 % de afirmaciones marcadas, se revisa la regla
   (desviación en §19), nunca se afloja en silencio.
3. **Los flags de `claude -p` cambian (D11).** Detección por capacidad; si una
   versión retira `--safe-mode`, el preflight bloquea en vez de correr sin
   aislamiento. Sondas con la versión real antes de fijar los tests.
4. **Cambios incompatibles (0.9.0):** `grounding` default `existence` y
   publicable exige `judge`; `RoBTool` sin `GRADE`; `effects.yml` exige
   `outcome`; `RunInfo.prompt_sha256` → `environment.prompt_templates`;
   corridas 0.8 no reanudables ni publicables; `agent_driver` ya no aprueba
   solo; `requires-python >= 3.11` (amplía, no rompe); extra `rag` eliminado;
   `agreement` renombrado en la solicitud (`concordance`); `LLMProvider`
   emite metas por intento (los proveedores de terceros que implementen el
   Protocol siguen funcionando: el sink es opcional, solo pierden las metas de
   intentos). Van en el CHANGELOG bajo «Cambios incompatibles».
5. **Dominios oficiales como datos.** Un error de transcripción en un YAML de
   herramienta es un error metodológico. Mitigación: cada especificación cita
   su fuente y versión; un test por herramienta fija conteos y escalas; la
   re-auditoría (área de rigor metodológico) los contrasta.
6. **Normalizar el DOI al construir el registro cambia ids.** Corridas nuevas
   tendrán ids distintos de las 0.8 para el mismo artículo. Aceptado (D12).
7. **El texto completo multiplica tokens.** 120 000 caracteres × incluidos ×
   (extracción + RoB + juez). Con suscripción el coste es tiempo; con API,
   dinero: `max_chars` es del protocolo y `metodologia.md` lo declara.
8. **Un `effects.yml` legado deja de cargar.** El de `prisma-ia-origen`
   necesita `outcome` y `multiple_per_study` o rehacerse (D16, §14.2).
9. **Windows en CI.** WeasyPrint fuera; rutas largas; tiempos. Si una celda
   es inestable, se marca `cronometrado` o se documenta, nunca se apaga la
   plataforma.
10. **El depósito sigue siendo una copia.** `deposit.json` no es una firma:
    quien reescriba todo coherente sigue pasando (límite ya declarado en la
    Ola 1, fila 45i).
11. **La re-auditoría puede reabrir el diseño.** Si encuentra un alto que exige
    cambiar una decisión D1–D6, se vuelve al arquitecto antes de corregir.

## 19. Desviaciones durante la implementación

Registro de lo que cambie respecto a §4–§14 y a los planes, y por qué. Vacío al
redactar.

| # | Dónde | Cambio | Origen |
|---|---|---|---|
