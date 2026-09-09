# Auditoría completa de RevisIA · 2026-09-03

- **Objeto:** RevisIA v0.6.0, rama `feat/fuentes-abiertas-backends` (HEAD `591d290`, PR #7 abierto sobre `main`).
- **Método:** cinco auditorías independientes en paralelo (núcleo del pipeline, seguridad y cadena de suministro, rigor metodológico y estadístico, tests/reproducibilidad/empaquetado, capa LLM/RAG/memoria), solo lectura, con reproducción ejecutada de cada hallazgo relevante. Los hallazgos críticos y altos fueron re-ejecutados por el consolidador en esta máquina (Windows 11, Python 3.13) antes de incluirse aquí. Nada de lo que sigue es especulación: cada punto cita `fichero:línea` y, cuando aplica, la salida real.
- **Línea base:** 188 tests en verde (también bajo Python 3.11 y 3.12, con orden aleatorio y sin red); `ruff`, `black` y `ruff format` limpios y concordantes; `uv lock --check` OK; cobertura total 86 %.

## 1. Veredicto

RevisIA tiene una **base de ingeniería sólida**: capa de proveedores uniforme con carga perezosa, salida estructurada validada con Pydantic, suite offline rápida y determinista, ledger honesto, meta-análisis de efectos fijos/DL/Egger que reproduce metafor a cuatro decimales, y un patrón de backends de búsqueda limpio y bien probado.

Sin embargo, **tres de las promesas centrales del README no se cumplen hoy en el código**:

1. **"La decisión final es siempre humana."** No existe decisión humana por registro: `human_label` nunca se escribe, el checkpoint solo permite aprobar o rechazar la etapa en bloque, no es reanudable desde el CLI (lo que empuja a `--auto-approve`), un rechazo del reporte final se reporta como `completed`, y un `autonomy: A3` en `protocol.yml` desactiva todo el HITL sin validación.
2. **"Verificador anti-alucinación."** En el modo por defecto (`embedder`, umbral 0.12 sobre un hash de bolsa de palabras) toda afirmación pasa como fundamentada, incluidas las contradictorias y las de puras *stopwords*; solo se comprueba la primera aparición de cada cita; una síntesis sin citas queda "limpia"; y la bandera nunca bloquea el avance.
3. **"Manifiesto reproducible."** La corrida fundacional del repo es una reconstrucción (140 llamadas con timestamps en 1,3 ms, ledger fechado a mano, métricas aritméticamente imposibles, etapas ausentes) y `revisia audit` la declara APTA porque comprueba presencia de ficheros, no coherencia. El benchmark de cribado deriva de esa corrida, y su meta-análisis mezcla 27 efectos dependientes de un mismo artículo.

A esto se suman **dos vulnerabilidades reproducidas** (inyección de comandos en Windows desde `protocol.yml`; lectura arbitraria de ficheros en el export) y un **quickstart roto**: el modelo por defecto `gemini-2.0-flash` fue apagado por Google el 1 de junio de 2026.

**Conclusión:** apto como motor de investigación y prototipo; **no apto todavía para sustentar una revisión sistemática publicable** sin las remediaciones de las olas 0 y 1 (§7). Ninguna de ellas exige rediseñar la arquitectura.

## 2. Recuento

| Severidad | Hallazgos consolidados |
|---|---|
| Crítico | 4 |
| Alto | 16 |
| Medio | 24 |
| Bajo | 22 |

(Un mismo problema detectado por varias auditorías cuenta una vez.)

## 3. Hallazgos críticos

### C1 · El checkpoint humano no decide sobre registros y puede saltarse

- **Dónde:** `orchestration/pipeline.py:217,281,286,585-606`; `orchestration/hitl.py:62-96,136-160`; `cli.py:120,309-336`; `config.py:322`; `audit.py:59-60,171-193`.
- **Evidencia reproducida:**
  - `grep human_label revisia/` → solo lecturas; nada lo asigna. El payload de `screening_ft` que ve el humano es `{'n_evaluados': 2, 'n_incluidos': 2, 'n_excluidos': 0}`: sin ids, sin forma de rescatar un excluido ni resolver un `unclear`.
  - `unclear` en texto completo entra en extracción, RoB, síntesis y conteo de incluidos (`pipeline.py:286`).
  - `reporte/decision.yml` con `approved: false` → `status: completed`, exit 0, y `--brain` sedimenta la revisión rechazada.
  - `autonomy: {screening_ta: A3, extraccion: A3, rob: A3}` → corrida `completed` sin `--auto-approve`, ledger todo `auto-proceed`, cero `review_request.yml`. `config.py` no valida valores ni la regla "≤ A1".
  - Cada `revisia run` crea una carpeta nueva; el `decision.yml` que el mensaje de pausa pide crear nunca se lee. Al reanudar por API con el mismo timestamp se re-ejecuta búsqueda y cribado y se aplica la aprobación a un resultado distinto (el ledger no guarda hash del payload).
  - `decision.yml` con `approved: "false"` aprueba (`bool("false")`); YAML malformado → traceback.
  - Con `--auto-approve`, `exclusions.json` da humano = 0 y `revisia audit` emite `hitl WARN` pero veredicto **"APTA para preparar publicación"** (`publishable = n_fail == 0`).
- **Impacto:** PRISMA 2020 ítem 8 y PRISMA-trAIce M8/R1 no pueden reportarse con verdad; el diagrama trAIce siempre mostrará "excluidos por humano: 0".
- **Corrección:** `decision.yml` con `overrides: {record_id: include|exclude, reason}` aplicados a `human_label`; `revisia run --resume <run_dir>`; `request_sha256` en la decisión comparado con `review_request.yml`; `if final_gate.status != "approved": return PipelineResult(final_gate.status, …)`; `@field_validator("autonomy")` con valores A0–A3 y tope A1 en etapas de juicio; validación Pydantic estricta de `decision.yml`; en `audit.py`, `hitl` en FAIL sin actor `human:*` y `publishable` exige ausencia de `auto-approve`.

### C2 · El verificador anti-alucinación no verifica

- **Dónde:** `agents/verificador.py:30-39,50,88-92,107-115,624,703`; `rag/embed.py:35-49`; `config.py:85`; `pipeline.py:428-449,558-568`; `llm/providers/fake.py:43-44`; `tests/test_grounding.py:15`.
- **Evidencia reproducida** (fuente en inglés con "sensitivity 0.91, specificity 0.62, reduced workload 40 %"):

  | Afirmación | modo `embedder` | sim |
  |---|---|---|
  | correcta | grounded | 0.480 |
  | falsa, mismo tema ("sensitivity 0.55, increased workload") | grounded | 0.404 |
  | contradictoria ("worse than human, specificity 0.99") | grounded | 0.413 |
  | sin relación ("reduced mortality in sepsis") | grounded | 0.193 |
  | solo *stopwords* | grounded | 0.260 |

  Ningún caso activó `hallucination_flagged`. Español vs inglés sin números: sim 0.0 (100 % falsos negativos). Cita repetida `[r1]` con una segunda afirmación absurda → `n_checks = 1`. `verify_narrative("sin citas")` → `checks=[]`, flag False. `[2019]` se toma como id. Modo `agent` con `fake` → todo grounded (y el test lo consagra). En modo `agent` el juez es el mismo proveedor que redactó la síntesis. `source_quote` de extracción nunca se comprueba como subcadena del abstract (`extraccion.py:56-64`).
- **Impacto:** la alucinación típica (cifra o dirección de efecto errónea) pasa; el gate final recibe una bandera que solo se imprime.
- **Corrección:** `existence` como default honesto y `embedder` etiquetado como experimental; verificar cada ocurrencia de cita y cada oración con número; juez con proveedor distinto al de síntesis; `support_quote` literal exigido; bloquear el gate si `hallucination_flagged`; `FakeProvider` fail-closed.

### C3 · La corrida fundacional es una reconstrucción y el auditor la aprueba; el benchmark hereda el problema

- **Dónde:** `runs/prisma-ia-origen-20260706-080747/` (`manifest.yml`, `decisions_ledger.jsonl`, `03_screening/metrics.json`, `exclusions.json`, `06_synthesis/verification.json`); `audit.py:107-158,228-321`; `protocols/prisma-ia-origen/effects.yml`; `docs/benchmark-cribado.md`.
- **Evidencia reproducida:**
  - 140 `llm_calls` con `timestamp_utc` entre `08:07:47.515524` y `08:07:47.516860`; los 46 hashes de respuesta de Sonnet son subconjunto exacto de los 94 de Opus.
  - Ledger con acciones `propose`/`exclude`/`verify` que `review_gate` nunca emite, a horas redondas una semana antes.
  - `metrics.json` = `{n:47, recall:1.0, mcc:0.71, kappa:0.75}`: fuerza bruta sobre todas las matrices con n=47 y FN=0 → ninguna produce esos valores; con FN=0, κ > MCC es imposible. `excluded_human: 3` que el motor no puede generar.
  - Solo existen `03_screening/`, `06_synthesis/`, `08_meta/`, `deliverable/`; faltan `01_search`, `02_dedup`, `04`, `05`, `07` y `decisions.json`. `identified_by_source: 40/40/40` con 0 duplicados.
  - `metodologia.md` y `manifest.yml` se contradicen (4 vs 3 bases; RoB2 vs AMSTAR2; 28 vs 120 identificados).
  - `uv run revisia audit` → 9 checks, FAIL=0 → **APTA**. El auditor da PASS a `gold` con κ=0.0 (verificado con corrida `fake`), a `grounding` con cero citas y a `search_window` porque el humano tecleó una fecha.
  - `effects.yml`: 27 de 28 efectos salen de un solo artículo (9 LLM × 3 datasets); dos pares de filas idénticas (`yi 2.52306/vi 0.14403`, `yi 3.04452/vi 0.69841`); Egger sobre logit de proporciones con k artificial. Es un problema de unidad de análisis (Cochrane Handbook §23.3).
- **Impacto:** el artefacto que respalda "reproducible" y las cifras del benchmark (0,820, I² 90,7 %) no resisten una revisión externa.
- **Corrección:** re-etiquetar la corrida como reconstrucción ilustrativa o regenerarla con el pipeline real; `audit.py` debe validar esquema (`ScreeningMetrics`, `VerificationReport`), artefactos por etapa, aritmética de `counts`, plausibilidad temporal de las llamadas y umbrales del protocolo; rehacer el meta-análisis del benchmark por subgrupos dataset→modelo sin duplicados y sin Egger.

### C4 · El modelo por defecto está apagado

- **Dónde:** `llm/providers/gemini.py:27`; `protocols/_TEMPLATE/protocol.yml:64,69,99`; `README.md:84`.
- **Evidencia:** changelog oficial de la API de Gemini, entrada del 1 de junio de 2026: "The following Gemini 2.0 models are now shut down: gemini-2.0-flash, gemini-2.0-flash-001" (anunciado el 18 de febrero de 2026). Sin fallo en tests porque ningún test llama a la API.
- **Impacto:** `revisia new` + key de Gemini falla con 404 en el paso 4 del quickstart.
- **Corrección:** default a un modelo vigente; `revisia validate` con lista de modelos retirados; no fijar el modelo en docstrings.

## 4. Hallazgos altos

| # | Título | Dónde | Evidencia |
|---|---|---|---|
| A1 | **Inyección de comandos en Windows** vía shim `claude.CMD` con `--model` de `protocol.yml` (BatBadBut) | `llm/providers/claude_code.py:102-136`; `llm/registry.py:46-80` | Reproducido: `model: 'opus" & <cmd> & "'` → `INJECTED executed? True`. `ProviderConfig.model` sin validar |
| A2 | **Lectura arbitraria de ficheros en el export**: `![x](../../.env)` en `documento.md` se embebe en HTML/PDF | `exports/document.py:185-213` | Reproducido: `traversal embed: b'TOP_SECRET=abc123'` |
| A3 | `except ValueError` traga `pydantic.ValidationError`: una base con un registro inválido desaparece sin rastro ni `failures.json` | `orchestration/pipeline.py:125-127` | Backend con `year="x"` → 0 registros, 0 fallos registrados |
| A4 | Seis normalizadores de DOI incompatibles → dedup falla y `record_id` colisiona (incluidos 3, extracciones 2, bib 3) | `dedup.py:26`; `manual_import.py:19-49`; `busqueda.py:41`; `search_backends.py:49,87,128` | Reproducido con RIS `https://doi.org/10.1000/ABC` + OpenAlex `10.1000/abc` |
| A5 | Dedup fusiona registros con título placeholder; BibTeX con llaves anidadas pierde el título; acentos no normalizados | `dedup.py:20-28`; `manual_import.py:78-86` | `title = {The {IMF} and growth}` → "(sin título)"; dos así → 1 |
| A6 | `RunMeta` registra `seed`/`temperature` que `claude_code`, `anthropic` y `agent` nunca envían | `claude_code.py:104-118,188-201`; `anthropic_api.py:50-77` | `¿viajan en el cmd? False False`; el manifiesto y trAIce los publican |
| A7 | `prompt_sha256` es el hash de la plantilla renderizada, no del prompt enviado (schema inyectado + sufijo de reintento); sin `prompt_version` | `claude_code.py:223-244`; `local_openai.py:39-58`; `prompts/__init__.py:23` | `57b517…` vs `2f1666…` |
| A8 | Ensemble con `provider: agent`: el callback no sabe qué modelo vota; "Opus + Sonnet" son dos llamadas idénticas; `agent_driver` con `auto_approve=True` por defecto | `agent.py:43,128-130`; `agent_driver.py:37` | El callback recibe `<sin campo model>` ×2 |
| A9 | Sin checkpointing ni caché: `decisions.json` se escribe al final; un 429 en un miembro aborta y pierde todo el cribado | `pipeline.py:209-221`; `screening.py:73` | ~1 400 llamadas y 1,1 M tokens por 500 registros; con `claude_code` secuencial 3–8 h |
| A10 | `claude -p`: `--allowedTools ""` no desactiva herramientas (el flag es `--tools ""`); sin `--max-turns`, `--json-schema`, `--bare`; hereda `cwd` (con `.claude/settings.local.json` del repo) y todo el `os.environ` | `claude_code.py:86,104-118` | `claude --help` 2.1.126. No reproducido en vivo (401 en sesión anidada) |
| A11 | El auditor da PASS por existencia; `kappa_min`/`recall_target` no se leen en ningún sitio | `audit.py:228-299`; `config.py:62,78` | `gold PASS` con κ=0.0 |
| A12 | Riesgo de sesgo con una sola escala para seis herramientas; AMSTAR-2 con 6 "dominios" (oficial: 16 ítems); QUADAS-2 sin aplicabilidad; GRADE tratado como RoB; sin agregación algorítmica RoB2 | `schemas/rob.py:15-16`; `agents/rob.py:23-62,103-116`; `prompts/rob/v1.md` | Dominios devueltos no se validan contra `TOOL_DOMAINS` |
| A13 | Puntos de entrada reales con 0 % de cobertura (`run_review`, `agent_driver`, handlers `run`/`validate`/`gold-template`) | `orchestration/flow.py`; `agent_driver.py`; `cli.py:24-169` | `flow.py 19/19 miss`; `cli.py 58 %` |
| A14 | El sdist incluye `runs/` (corrida real, 557 KB), `.superpowers/sdd/*`, `.claude/settings.local.json`, `.coverage`; también el `dist/revisia-0.6.0.tar.gz` ya construido | `pyproject.toml` (sin `targets.sdist`) | `tar tzf` → 37 entradas sospechosas |
| A15 | `manifest.yml` no registra versión del motor (el `engine:` antiguo ya no se escribe), Python, dependencias, commit ni versión de plantilla de prompt | `run_context.py:54-70`; `pipeline.py:566-584` | `grep engine|__version__|platform` → 0 |
| A16 | Doble extracción: "PRISMA exige ≥ 20 %" es falso (MECIR C43 pide dos humanos al 100 %); el segundo extractor es otro LLM; κ de presencia degenera a 0.0; acuerdo = igualdad literal (`'240'` ≠ `'240 patients'`) | `extraction_agreement.py:1-14,61-89` | Run: "acuerdo 29 %, κ 0,343" sin bloqueo |

## 5. Hallazgos medios

| # | Título | Dónde |
|---|---|---|
| M1 | HTML crudo sin sanear en el export (`<script>`, `onerror`, `<img src=http>` pasan); WeasyPrint sin `url_fetcher` restringido | `exports/document.py:225-226,355` |
| M2 | **API keys de OpenAlex/NCBI copiadas a `01_search/failures.json` y a stdout** cuando httpx incluye la URL en el error (código del PR #7) | `pipeline.py:129,189-194`; `busqueda.py:87-89`; `ncbi.py:59-61` |
| M3 | Prompt injection: abstracts/PDF/HTML interpolados sin delimitar ni marcar como datos; el juez de grounding lee el mismo texto atacante | `prompts/*/v1.md`; `rag/grounding.py:57-64` |
| M4 | Descargas de texto completo sin límite de tamaño ni tiempo de parseo; `pypdf` importado pero no declarado (hoy el fallback PDF nunca se activa) | `agents/fulltext.py:73-84,132-143`; `pyproject.toml` |
| M5 | `hallucination_flagged` nunca bloquea (contradice la docstring de `VerificationReport`) | `schemas/verification.py:4-7`; `pipeline.py:558-568` |
| M6 | Sin fail-fast: un proveedor ausente para `screening_ft` se detecta tras gastar el cribado; `validate` devuelve 0 | `pipeline.py:260,322,379,424`; `cli.py:60-64` |
| M7 | RIS en UTF-16 aborta la corrida (fuera del `try`); abstracts multilínea truncados | `ingest/manual_import.py:56-65,113-115` |
| M8 | Emojis en stdout no UTF-8 (cp1252, redirección en Windows) → `UnicodeEncodeError`, exit 1 a mitad de corrida | `cli.py:129-146`; `pipeline.py:191` |
| M9 | `revisia new` depende del cwd y la plantilla no viaja en el wheel | `cli.py:176-178,355`; `pyproject.toml` |
| M10 | Corrección de continuidad 0,5 aplicada **siempre** en logOR (sesgo hacia el nulo +0,017); estándar es solo con celdas cero (Sweeting 2004) | `schemas/effects.py:63-73` |
| M11 | Flujo PRISMA: los no recuperados cuentan como "evaluados"; `dbr_notretrieved = 0` fijo en el CSV; sin lista 16b; razón de exclusión = primer criterio del voto IA | `exports/prisma_flow.py:93-141`; `exports/interop.py:110-112`; `pipeline.py:255-268,301-319` |
| M12 | PRISMA-S: fecha y cadenas no las registra el motor (salen de `protocol.yml` a mano); sin `01_search/log.json`; `search_strings/*.txt` no se copian al run | `pipeline.py:107-135`; `exports/checklist.py:116-136`; `audit.py:302-321` |
| M13 | Checklist trAIce: no mapea los 17 ítems; "Validación humana: checkpoints HITL registrados" es texto fijo incluso con `--auto-approve`; autonomía impresa ≠ efectiva | `exports/checklist.py:201-270` |
| M14 | Texto completo truncado a 20 000 caracteres sin registrarlo; cribado FT y RoB juzgan intro+métodos | `agents/fulltext.py:103,118,147` |
| M15 | Sin reintentos/backoff/`finish_reason` en Gemini/OpenAI/Anthropic; `max_tokens` único por etapa | `gemini.py:81-94`; `openai_api.py:76-95`; `anthropic_api.py:101-107` |
| M16 | "Qdrant opcional" anunciado (extra `rag`, `QDRANT_*`) sin código que lo use | `pyproject.toml`; `.env.example:57-62`; `rag/store.py` |
| M17 | Coste y tiempo por corrida no se estiman ni acotan (`--max-budget-usd` ausente) | `pipeline.py`; `claude_code.py` |
| M18 | Crossref y Semantic Scholar (bases por defecto) sin ningún test de parseo | `agents/search_backends.py:40-102` |
| M19 | Ruta de fallback de texto completo (Unpaywall → PDF/HTML) sin tests (55 %) | `agents/fulltext.py` |
| M20 | Proveedores API sin prueba de llamada ni de `RunMeta` (38–49 %) | `llm/providers/{gemini,openai_api,anthropic_api}.py` |
| M21 | Un test depende de la corrida real no versionada y de una ruta relativa al cwd (se salta en CI) | `tests/test_export_document.py:222-231` |
| M22 | CI solo Ubuntu; sin matriz, caché, `uv lock --check` ni cobertura; el autor desarrolla en Windows | `.github/workflows/ci.yml` |
| M23 | `.gitignore`: la negación `!runs/*/manifest.yml` es inoperante; README promete que se versionan | `.gitignore:16-18` |
| M24 | `requires-python >= 3.13` injustificado: la suite pasa en 3.11 y 3.12 | `pyproject.toml:9` |

## 6. Hallazgos bajos

`decision.yml` vacío rechaza como `human:desconocido` · YAML con raíz lista → `AttributeError` · `record_id` posicional (`crossref:<n>`) o con espacios (`pubmed:<título>`) · CLI: tracebacks sin capturar, `paused` con rc 0 · sin `--mailto`, Unpaywall e ID Converter se saltan en silencio · `run_pipeline` de 459 líneas con 5 bloques de gate casi idénticos · Brain: `prisma_flow_updated.md` fuera del manifiesto, delta del living review mezcla no determinismo · sin columna "seed aplicado" · MCC/κ devuelven 0.0 cuando son indefinidos (deberían ser `None`) · Egger desde k=3 (recomendado ≥10) · sin Hartung-Knapp ni intervalo de predicción · `p_value = 0.0` por underflow · slug/paths sin validar (traversal autoinfligido) · sdist y `dist/` con residuos `prisma_loop-0.2.0` · `SECURITY.md` con tabla 0.1.x · transitivas con avisos (pillow 12.2.0 con 14 PYSEC, cryptography 49, h2 4.3.0, pyasn1 0.6.3) · CI sin `permissions:` · conteo de tests 188/168/166/49 según el documento · `test_coverage_gaps.py` nombrado por métrica; sin `conftest.py`, tres fakes de `httpx.Client` · black y ruff format redundantes · `RELEASING.md` desactualizado · `arquitectura.md` sin la capa de fuentes abiertas · "8 backends" vs "9 opt-in"; `--max` 50 (CLI) vs 25 (API) · 3 enlaces rotos en `docs/superpowers/plans/2026-09-03-…` · `.coverage` sin ignorar; sin `.gitattributes`; `.superpowers/` no ignorado en raíz.

## 7. Lo que está bien (con evidencia)

- **Tests:** 188/188 en 3.11, 3.12 y 3.13; orden aleatorio; sockets deshabilitados; < 3 s; todos aseveran (verificado por AST). Backends nuevos al 95–97 %.
- **Estadística:** efectos fijos IV, DerSimonian-Laird, Q/I²/τ² idénticos a `metafor::dat.bcg` a cuatro decimales; Egger coincide con `scipy.stats.linregress`; MCC y κ correctos frente a la fórmula manual; `accuracy` no se expone; voto pro-recall documentado y testeado; muestreo de doble extracción determinista.
- **Seguridad que sí está:** sin `shell=True`; `.env` nunca commiteado y sin secretos en el historial; `manifest.yml` solo con hashes; `yaml.safe_load` en todas partes; expat resiste billion laughs y XXE; httpx rechaza `file://`; Actions fijadas por SHA (verificadas: `checkout` v4.3.1, `setup-uv` v5); corrida real sin PII ajena.
- **Diseño LLM:** contrato `Protocol` uniforme con carga perezosa; salida estructurada nativa (tool-use en Anthropic, `parse` en OpenAI, `response_schema` en Gemini); `deterministic=False` declarado honestamente; votos por miembro persistidos; prompts en ficheros; `claude_code` con shim Windows, 401 accionable, stdin y `clean_env`.
- **Determinismo de salidas:** `sorted()` donde importa; dedup idempotente; I/O con `encoding="utf-8"` explícito en todo el paquete.
- **Memoria `--brain`:** nunca entra en un prompt (verificado por `grep recall(`); aislamiento por slug; `raw/` inmutable.
- **Checklists:** 27 + 16 + 12 ítems correctos y ningún ítem se marca como cumplido sin evidencia.

## 8. Plan de remediación

**Ola 0 · esta semana, sin cambiar el diseño (cierra C4, A1, A2, A3, M2, y la mitad de C1):**
1. Modelo por defecto vigente + lista de modelos retirados en `validate`.
2. `ProviderConfig.model` con patrón `^[A-Za-z0-9._:/-]{1,64}$`; en Windows lanzar `claude` sin pasar por el `.CMD` o con escapado propio.
3. `_embed_md_images`: exigir `target.resolve().is_relative_to(deliverable)` y extensión de imagen; sanear HTML de `markdown` (`nh3`); `url_fetcher` que solo acepte `data:`.
4. Redactar `api_key=` en los errores antes de escribir `failures.json`; capturar solo la `ValueError` de despacho (comprobar `db_key(db) in BACKENDS` antes de llamar).
5. `if final_gate.status != "approved": return PipelineResult(final_gate.status, …)`; `@field_validator("autonomy")`; `decision.yml` validado con Pydantic.
6. `[tool.hatch.build.targets.sdist] only-include = […]`; `.gitignore` con `.coverage*`, `.superpowers/`; reconstruir `dist/`.
7. Re-etiquetar `runs/prisma-ia-origen-…` y `docs/benchmark-cribado.md` como reconstrucción ilustrativa hasta regenerarlos.
8. MCC/κ → `None` cuando indefinidos; corrección de continuidad solo con ceros.

**Ola 1 · HITL real y auditor exigente (cierra C1, C3-auditor, A9, A11, M5, M6, M11, M12, M13):**
1. `decision.yml` con `overrides` por registro y `request_sha256`; `revisia run --resume`; `decisions.jsonl` incremental; `unclear` FT → pendiente humano.
2. `audit.py`: valida esquemas, artefactos por etapa, aritmética, plausibilidad temporal, umbrales `kappa_min`/`recall_target`; `hitl` FAIL sin humano; `publishable` exige sin `auto-approve` y sin `hallucination_flagged`.
3. `01_search/log.json` por base (cadena efectiva, parámetros, timestamp, n) y copia de `search_strings/` al run; flujo PRISMA con "no recuperados" y 16b.
4. Fail-fast de proveedores al inicio; `validate` con rc ≠ 0.

**Ola 2 · rigor y honestidad de las afirmaciones (cierra C2, C3-benchmark, A4–A8, A10, A12, A15, A16):**
1. Grounding: `existence` por defecto, verificación por ocurrencia, juez con proveedor distinto, `support_quote` literal; bloqueo del gate.
2. `normalize_doi()` único; dedup sin placeholders; parser BibTeX con conteo de llaves; NFKD en títulos.
3. `RunMeta` con `seed_applied`/`temperature_applied`, hash del prompt enviado, `prompt_version`; `manifest.environment` (versión, Python, plataforma, commit, hashes de plantillas).
4. `claude -p` con `--tools ""`, `--max-turns 1`, `--json-schema`, `--bare`, `cwd` vacío, entorno mínimo, `--max-budget-usd`; `model` real en el callback de `agent`; `agent_driver` con `auto_approve=False`.
5. RoB por herramienta (escalas y dominios oficiales, agregación RoB2); extracción sobre texto completo.
6. Rehacer el meta-análisis del benchmark (subgrupos dataset→modelo, sin duplicados, sin Egger, con intervalo de predicción) y corregir la afirmación "PRISMA exige ≥ 20 %".
7. Tests de entrypoints, Crossref/S2, fulltext y proveedores; CI con matriz Windows/Linux × 3.11–3.13, caché, `uv lock --check`, cobertura ≥ 80 %; `requires-python >= 3.11`.

## 9. Límites de esta auditoría

- No se hicieron llamadas reales a proveedores LLM de pago ni a `claude -p` con sesión válida (la anidada devolvió 401): A10 se sustenta en `claude --help`, no en ejecución.
- Backends de búsqueda: auditados por código; los nueve nuevos sí se verificaron en vivo en el PR #7.
- WeasyPrint (`--format pdf`) no instalado: M1 se reprodujo solo para HTML.
- No se consultó PyPI/Zenodo para saber si el sdist con `runs/` se publicó.
- Referencias de metafor para BCG contrastadas con scipy, no con R.
- Los scripts de reproducción viven fuera del repositorio (directorio temporal de la sesión de auditoría): `repro1.py`, `repro2.py`, `grounding_repro.py`, `meta_repro.py`, `cost_est.py`, `t_bat.py`, `t_export.py`, `t_xml.py`, `t_httpx.py`. Cada hallazgo incluye la evidencia suficiente para reproducirlo sin ellos.

## 10. Contraste con los principios de diseño de RevisIA

El README declara cuatro principios. Esta auditoría los usa como criterio de veredicto: un hallazgo es crítico cuando rompe uno de ellos, no solo cuando es un bug.

| Principio (README) | Estado | Evidencia de esta auditoría |
|---|---|---|
| **Provider-agnostic** | Se cumple en el diseño; falla en el default | Contrato `Protocol` uniforme y carga perezosa (§7). Pero el modelo por defecto está retirado (C4) y con `provider: agent` el ensemble no distingue modelos (A8). |
| **Motor ↔ config** | Se cumple con una fuga | `revisia/` no contiene nada de una revisión concreta. La fuga es el sdist: empaqueta `runs/` y ficheros de proceso (A14). |
| **Reproducible** | No se cumple hoy | `RunMeta` registra parámetros que no se enviaron (A6), el hash no es del prompt enviado (A7), el manifiesto no registra el entorno (A15) y la corrida de referencia es una reconstrucción (C3). |
| **Defendible** | Parcial | Métricas y meta-análisis correctos (§7). Pero sin decisión humana por registro (C1), con un verificador que no discrimina (C2), RoB con escalas no oficiales (A12) y un auditor que aprueba por presencia de ficheros (A11), las afirmaciones PRISMA-trAIce no se sostienen ante un revisor. |

Y los tres compromisos operativos del proyecto (AGENTS.md):

| Compromiso | Estado |
|---|---|
| "`screening`, `extraccion` y `rob` nunca superan A1" | Documentado, no cableado: `autonomy: A3` en el protocolo lo desactiva (C1). |
| "La decisión final es siempre humana" | El humano aprueba etapas, no registros; `--auto-approve` produce una corrida que el auditor llama publicable (C1). |
| "El verificador bloquea la aprobación silenciosa" | La bandera se imprime, no bloquea (M5). |

## 11. Estado de remediación

Aplicado en la misma rama del PR #7 tras la auditoría:

- **A3 y M2 corregidos** (commit `261b82c`): la condición "base sin backend" se comprueba antes de llamar, cualquier excepción del backend queda en `failures.json`, y los mensajes pasan por `_http.redact_secrets` (oculta `api_key=`, `token=`, `email=`). Dos tests nuevos.
- **C3, parte documental** (commit `91954c2`): aviso de procedencia en `docs/benchmark-cribado.md` que marca las cifras del artículo fundacional como ilustrativas hasta regenerar el benchmark con el pipeline real.
- Higiene: `.coverage*`, `coverage.xml` y `htmlcov/` ignorados.

Todo lo demás sigue abierto y está ordenado en §8.
