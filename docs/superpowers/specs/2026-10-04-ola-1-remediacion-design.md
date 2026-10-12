# Ola 1 del plan de remediación · diseño

- **Fecha:** 2026-10-04
- **Origen:** `docs/auditoria/2026-09-03-auditoria-completa.md` §8, "Ola 1 · HITL real y auditor exigente".
- **Base:** `main` @ `412d529` (v0.7.0; 330 tests recogidos por pytest, en verde).
- **Alcance declarado por la auditoría:** cierra C1 (lo que dejó la Ola 0), C3 en la parte del auditor, A9, A11, M5, M6, M11, M12 y M13. Además decide M23.
- **Spec anterior:** [`2026-09-25-ola-0-remediacion-design.md`](2026-09-25-ola-0-remediacion-design.md) (sus §8 y §5 B-4 dejan explícitamente para esta ola lo que sigue).

## 1. Por qué esta ola existe

La Ola 0 consiguió que el pipeline dejara de mentir: un rechazo final es un
rechazo, una autonomía A3 en una etapa de juicio no carga, y una corrida
reconstruida ya no audita como publicable. Lo que no consiguió, porque exigía
diseño, es que el pipeline **pueda decir la verdad**. Hoy no existe ninguna vía
por la que un humano decida sobre un registro: `human_label` no lo asigna
ningún código del paquete, de modo que el diagrama trAIce siempre dirá
"excluidos por humano: 0" y el ítem 8 de PRISMA 2020 no se puede reportar con
honestidad.

La Ola 1 resuelve las dos mitades del problema. La primera es el HITL por
registro, con una corrida reanudable que el humano retoma tras revisar. La
segunda es un auditor que comprueba la coherencia de lo que hay en disco, no
solo su existencia. Al cerrarla debe desaparecer la nota "Limitación actual
(Ola 1 del plan de remediación)" del README (`README.md:134-139`).

## 2. Estado de partida verificado

Todo lo que sigue se verificó leyendo `main` @ `412d529`. Los números de línea
que cita la auditoría están desfasados en varios ficheros; aquí van los
vigentes.

| Área | Estado real | Dónde |
|---|---|---|
| Decisión humana | `human_label` solo se lee (`final_label = human_label or ensemble_label`); los 5 gates aprueban o rechazan la etapa entera. El payload del gate FT es `{n_evaluados, n_incluidos, n_excluidos}`: sin ids. | `pipeline.py:221,285,239-307`; `hitl.py:56-115` |
| `unclear` en FT | Pasa a extracción, RoB, síntesis y `counts.included`. | `pipeline.py:290` |
| Reanudación | Cada `revisia run` genera un timestamp nuevo; `RunContext` hace `mkdir(exist_ok=True)`; el ledger abre en modo `"a"` y duplicaría entradas. | `cli.py:177`; `run_context.py:30`; `ledger.py:50` |
| Pérdida por fallo (A9) | `decisions.json` se escribe al final de cada bucle; los `RunMeta` solo llegan a disco con el manifiesto. Sin `try`, reintentos ni caché: un 429 en cualquier registro llega como traceback a `main`. | `pipeline.py:213-225,268-288`; `run_context.py:44-45` |
| Búsqueda (M12) | Los registros crudos no se guardan; `01_search/` solo existe si alguna base falla. Si falta `search_strings/<db>.txt` se usa la pregunta sin avisar; una base sin backend (o mal escrita) se salta sin avisar. Cadena, fecha, parámetros y n por base no se registran. | `pipeline.py:98-136,182-198` |
| Texto completo (M11) | Un registro sin texto recuperable se criba con el abstract y cuenta como evaluado; `dbr_notretrieved_reports` es `0` literal; no hay lista 16b. El motivo del fallo no se guarda. | `pipeline.py:270-288`; `interop.py:111`; `fulltext.py:110,126,130,138,146` |
| Proveedores (M6) | Se construyen al entrar en cada etapa: una key ausente para FT se descubre después de gastar el cribado T/A. `validate` devuelve 0 con "(sin proveedor)". | `pipeline.py:264,326,383,428`; `cli.py:92-129` |
| `.env` | `python-dotenv` es dependencia, pero ningún módulo lo importa; el README pide poner la key en `.env`. | `grep dotenv revisia/` → 0 |
| Auditor (A11, C3) | `publishable = n_fail == 0`; `hitl` nunca da FAIL; auto-approve y `hallucination_flagged` solo dan WARN; `kappa_min`/`recall_target` no se leen; ningún esquema, aritmética ni tiempo se comprueba. | `audit.py:62-63,189-222,405-427` |
| Bloqueo por alucinación (M5) | `hallucination_flagged` va al payload del gate final y se imprime; no bloquea nada. Tres docstrings dicen lo contrario. | `pipeline.py:568`; `schemas/verification.py:6`; `agents/verificador.py:7` |
| Checklist trAIce (M13) | "Validación humana: checkpoints HITL registrados" es texto fijo; imprime `dict(protocol.autonomy)` (solo lo declarado), no la autonomía efectiva. `metodologia.md` fija "A0" en extracción y RoB. | `checklist.py:230,234`; `pipeline.py:537`; `methods.py:76,94,109,116` |
| Métricas | Usan `final_label or ensemble_label`: en cuanto haya etiquetas humanas medirían humano+IA, no la IA contra el gold. | `metrics.py:130` |
| `.gitignore` (M23) | Las negaciones `!runs/*/manifest.yml` son inoperantes y así lo dice el comentario de la Ola 0. | `.gitignore:14-21` |

Seis hallazgos de la exploración condicionan el diseño:

1. **El gate final no convergería al reanudar** si solo se registraran en el diario
   cribado, extracción y RoB. La síntesis (`pipeline.py:430`) y el juez de grounding
   (`rag/grounding.py:69`, que además descarta su `_meta`) volverían a llamar al
   LLM, cambiaría la narrativa y con ella el hash del payload de `reporte`.
   Además, ese payload lleva `str(deliverable)`, una ruta absoluta (`pipeline.py:569`).
2. **`dedup._merge_extra` muta el registro conservado**, que es el mismo objeto de
   `raw_records` (`dedup.py:31,57`). La instantánea de búsqueda tiene que
   escribirse antes del dedup.
3. **Los `record_id` no son únicos tras el dedup.** Un RIS con
   `DO https://doi.org/10.1000/ABC` produce el id `10.1000/abc` (`manual_import.py:21`)
   pero conserva `doi="https://doi.org/…"`, con otra clave de dedup que el mismo
   artículo traído de OpenAlex. `pubmed:{title[:40]}` (`ncbi.py:130`) también puede
   colisionar. El diario y las etiquetas humanas usan el id como clave.
4. **`load_protocol` toma el slug del nombre de la carpeta** si el protocolo no lo
   declara (`config.py:157`). Al cargar la instantánea `00_protocol/`, el slug
   sería `"00_protocol"`.
5. **`FakeProvider` vota siempre `include`** (el primer valor del `Literal`,
   `fake.py:30`). Con él no hay exclusiones, ni gold de dos clases, ni `unclear`.
6. **Sin `httpx` (extra `search`) fallan todas las bases con backend y toda la
   recuperación de texto completo; sin `--mailto` se omiten Unpaywall y el ID
   Converter.** Con el criterio PRISMA estricto de D2, cualquiera de los dos
   convierte la mayoría de los registros en "no recuperados".

## 3. Decisiones tomadas

D1–D3 las tomó el arquitecto el 2026-10-04 entre alternativas presentadas. D4–D14
son supuestos propuestos con el diseño y aceptados con él; son revocables. A
pedido del arquitecto, D7, D8 y D13 se revisaron ese mismo día en una segunda
pasada. D7 y D8 cambiaron (umbrales según lo que mide cada métrica; las citas
marcadas se adjudican en vez de dar FAIL incondicional) y D13 se confirmó con
precisiones.

| # | Decisión | Razón |
|---|---|---|
| D1 | **Decisión humana por registro solo en cribado T/A y FT.** En T/A (A1 por defecto) el humano aprueba la propuesta IA con excepciones opcionales. En FT (A0 por defecto) etiqueta **cada** registro evaluado. A1 se admite en FT, pero todo `unclear` debe resolverlo un humano. Extracción y RoB se aprueban por etapa, con la tabla completa por estudio en la solicitud y el hash del artefacto aprobado. | Cierra C1, PRISMA 8 y trAIce R1. Los overrides de RoB por dominio se rehacerían en la Ola 2 (A12 cambia las escalas por herramienta); la corrección campo a campo de la extracción hace crecer la ola cerca de un 50 %. |
| D2 | **No recuperados: PRISMA estricto con rescate humano.** Un registro sin texto completo no se criba con IA ni cuenta como evaluado: va a la caja "informes no recuperados". En el gate FT aparece como rescatable; si el humano lo consiguió por otra vía puede asignarle `include`/`exclude` con razón obligatoria, y entonces cuenta como evaluado por humano. Sin rescate, queda como no recuperado y la etapa se puede aprobar igual. | PRISMA 2020 no contempla evaluar la elegibilidad sin el informe. La alternativa (cribar con el resumen y contarlo aparte) conservaba recall a costa de un diagrama que no es PRISMA. |
| D3 | **Reanudación con diario por registro.** Instantánea de la búsqueda y del dedup (nunca se repiten al reanudar); un `.jsonl` por etapa con LLM o red (T/A, recuperación, FT, extracción, 2.º extractor, RoB, **síntesis y verificación**); `llm_calls.jsonl` volcado en cada llamada. `revisia run --resume <run_dir>` recorre el pipeline desde el principio, carga lo existente y solo llama para lo que falta. Los gates pasan si `decision.yml` trae el `request_sha256` de la solicitud vigente. | Un mismo mecanismo cierra la pausa y el 429 (A9). Se descartó la máquina de estados por etapa (un 429 a mitad seguía perdiendo la etapa) y la caché de llamadas por hash (duplica `llm_calls` y complica la auditoría temporal). |
| D4 | `decision.yml` gana `request_sha256` (obligatorio en gates humanos) y `records: {id: {label, reason}}` (solo en cribado). Junto a cada solicitud se escribe `decision.template.yml` con `approved:` nulo (inválido hasta rellenarlo) y la propuesta IA en comentarios, con saltos de línea saneados. | Aprobar tiene que ser un acto deliberado. Un `rationale` del LLM con `\n` dentro de un comentario YAML inyectaría claves (`approved: true`). |
| D5 | `human_label` se escribe **solo** ante una etiqueta explícita. La aprobación en bloque de A1 deja la exclusión como "IA avalada" (`human_label = None`). | Si la aprobación en bloque convirtiera las exclusiones IA en humanas, el desglose trAIce R1 dejaría de significar algo. |
| D6 | Las métricas miden la **propuesta IA** (`ensemble_label`) contra el gold, siempre. El gold efectivo (fichero + `gold_labels=`) se guarda en `03_screening/gold.json`. | κ y recall evalúan el sistema, no al humano que lo corrige. Persistir el gold permite al auditor recalcular. |
| D7 | Umbrales del protocolo, tratados según lo que miden. **`recall_target`** (evidencia perdida): un recall IA por debajo del umbral es **FAIL** mientras quede alguna exclusión IA de T/A sin etiqueta humana explícita. Si el humano etiquetó todas las exclusiones IA, baja a WARN. El remedio no exige corrida nueva: se etiquetan esas exclusiones en `screening_ta/decision.yml` y se reanuda (D14). **`kappa_min`** (acuerdo humano-IA): por debajo da **WARN** "desviación del protocolo: declárala" (PRISMA 24c). **Potencia del gold:** un recall que alcanza el umbral con menos de ⌈1/(1−umbral)⌉ positivos en el gold (20 para 0,95) da WARN, no PASS, porque con tan pocos positivos un solo fallo ya baja del umbral. Un recall por debajo nunca se excusa por gold pequeño. El detalle informa siempre el intervalo de Wilson al 95 %. También WARN: umbral no medible (sin gold, κ `None`), ningún umbral declarado, clave desconocida (`kapa_min`). | La primera versión daba FAIL a cualquier métrica bajo umbral, y eso confundía dos cosas. Un recall bajo significa que la IA dejó fuera estudios relevantes, y solo amenaza la validez si nadie revisó esas exclusiones. Un κ bajo con recall alto es sobreinclusión: más trabajo en FT, ningún estudio perdido (la plantilla lo define como "acuerdo mínimo humano-IA"). El caso de A11 (κ = 0,0 con PASS) deja de pasar en limpio. |
| D8 | `auto-approve (demo)` o `auto-proceed` en un gate de juicio o en el final → **FAIL** (antes WARN). Con `hallucination_flagged`: (a) el gate final exige humano e ignora `--auto-approve` y la autonomía A2/A3 de `reporte`; (b) para **aprobar**, `reporte/decision.yml` debe adjudicar **cada** cita marcada en `flags: {<n>: {verdict: false_positive, reason}}`, con razón obligatoria. Si alguna marca es real, el camino es `approved: false`, porque no existe un veredicto "aceptar el riesgo". (c) El auditor da **FAIL** si queda alguna marca sin adjudicar por un humano y **WARN** si todas lo están ("k citas marcadas, adjudicadas como falsos positivos por <actor>: decláralo"). | Con FAIL incondicional, el humano no tenía forma de resolver un falso positivo, y hoy los hay: el patrón de citas (`verificador.py:30`) toma `[2019]` o `[1]` como ids, que salen "no está en el corpus" en cualquier modo. Así se mantiene lo que pide la auditoría §8 (nada de aprobación silenciosa con la bandera puesta) sin bloquear corridas por un defecto conocido del verificador (C2, Ola 2). Cada adjudicación queda en el ledger con actor y razón, y el auditor la expone. |
| D9 | `--auto-approve` aprueba con las etiquetas de la IA (actor no humano, como hoy), salvo que haya `unclear` en FT: entonces pausa. No exige la completitud A0. | Sigue sirviendo para demostraciones; el auditor la marca FAIL (D8). Un `unclear` en FT no tiene etiqueta IA que adoptar. |
| D10 | **Preflight sin red** (M6) antes de crear la carpeta de la corrida: proveedor conocido, SDK importable, key en el entorno, binario `claude`, `effort` solo en `claude_code`, etapa sin proveedor, base desconocida, modelo retirado, `httpx` ausente con bases con backend. Cualquier error da `rc 2` en `validate` y en `run`. `main` carga `.env` (`override=False`). `MANUAL_ONLY` se amplía para que las bases de suscripción comunes no den error. | Cierra M6 y el hueco de `.env`. Ampliar `MANUAL_ONLY` evita que el error de "base desconocida" bloquee CINAHL, Cochrane o ProQuest. |
| D11 | **M23:** las corridas no se versionan en el repo del motor. `runs/` se ignora entero, con un comentario que lo diga. | Principio motor↔config (README): una corrida pertenece a la revisión, no al motor. Se deposita en OSF/Zenodo o junto al protocolo. |
| D12 | M13 va en la pista del pipeline (PR-D): el checklist trAIce y `metodologia.md` los escribe el pipeline con hechos de la ejecución. El reductor del ledger (`summarize_gates`) es uno solo y lo usan pipeline y auditor, para que no se contradigan. | El auditor lee artefactos y no reescribe el entregable. |
| D13 | Una corrida anterior a la Ola 1 (sin `run.json`) **no se puede reanudar** (`rc 2`: "corrida anterior a la Ola 1; empieza una nueva con `revisia run <protocolo>`") y **no es publicable**: FAIL en `protocol_snapshot` con el mensaje "anterior a la Ola 1 (motor < 0.8): sin instantánea ni decisiones por registro; regenera la corrida con el motor actual". Sigue siendo **exportable** (`revisia export`, gracias al validador de `PrismaCounts` para manifiestos antiguos) y **auditable como diagnóstico** (se aplican las relaciones aritméticas v0.7). Versión: los cambios incompatibles de §13.4 suben la minor según SemVer 0.x, de **0.7.0 a 0.8.0**. El CHANGELOG los lista bajo "Cambios incompatibles", y cuándo publicar lo decide el arquitecto, igual que con la v0.7.0. | Revisado y confirmado. Reanudar sin instantánea obligaría a repetir la búsqueda, con resultados distintos de los que ya se cribaron. Auditar con las reglas v0.7 devolvería el veredicto que la auditoría declaró inválido (C1, C3). En la práctica el coste es casi nulo: la única corrida existente es la reconstrucción local, que ya audita "no publicable" desde la Ola 0. |
| D14 | Se puede reanudar después de un `reject`: la decisión efectiva de una etapa es la última del ledger y todas quedan registradas. No hay lock de concurrencia (se documenta: no reanudes la misma corrida en dos procesos). Una corrida interrumpida por error sale con `rc 3` e imprime cómo reanudar; `paused` sigue saliendo con `rc 0`. | Cambiar de opinión es legítimo si queda rastro. El lock deja ficheros huérfanos tras un `kill -9` y protege un caso raro. Cambiar el `rc` de `paused` rompería scripts y queda fuera. |

## 4. Contratos de artefactos (PR-0)

Esta sección es el contrato entre la pista del pipeline (PR-A a PR-D) y la del
auditor (PR-E). Se implementa en código en PR-0 (`revisia/schemas/artifacts.py`
y añadidos en `provenance/`), de modo que ambas pistas importan los mismos
modelos y constantes en vez de duplicarlos.

### 4.1 Convenciones

- `canonical_json(x) = json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)`.
- `canonical_sha256(x) = sha256(canonical_json(x).encode("utf-8")).hexdigest()`.
- Ambas viven en `provenance/runmeta.py`, junto a `sha256_text` y `utc_now_iso`.
- Horas en ISO-8601 UTC con zona (`utc_now_iso()`); rutas relativas con `/`; `schema_version: 1` en todo JSON nuevo.
- Hashes de ficheros de texto del protocolo: sobre el texto UTF-8 con CRLF convertido a LF (con `autocrlf` en Windows, el hash de los bytes cambiaría entre clones).
- **Ningún `record_id` se usa como nombre de fichero** (los DOI llevan `/` y los ids `:`, inválido en Windows). Donde haga falta, `sha256(record_id)[:16]`.
- En YAML que escribe el motor para el humano, las claves de registro van entre comillas dobles (`json.dumps(id)`), para que `10.1000/123` o `2019` no se lean como número.

### 4.2 Árbol del directorio de corrida

N = nuevo, M = modificado, = = sin cambios.

| Ruta | Formato | | Cuándo existe |
|---|---|---|---|
| `run.json` | `RunInfo` | N | Siempre: es lo primero que se escribe |
| `llm_calls.jsonl` | líneas `LLMCall` | N | Desde la primera llamada |
| `decisions_ledger.jsonl` | líneas `DecisionEntry` | M | Desde el primer gate |
| `00_protocol/{protocol,inclusion_exclusion,extraction_form}.yml` | copia | N | Siempre |
| `00_protocol/{effects,gold}.yml`, `00_protocol/search_strings/*.txt` | copia | N | Si existen en el protocolo |
| `01_search/records.json` | `list[SearchRecord]`, **antes** del dedup | N | Tras la búsqueda |
| `01_search/log.json` | `SearchLog` (marca de búsqueda completa) | N | Tras la búsqueda |
| `01_search/failures.json` | `list[{db, error}]` | = | Solo si hay entradas `failed` |
| `02_dedup/records.json` | `list[SearchRecord]` tras fusión y renombrado | N | Tras el dedup |
| `02_dedup/dedup.json` | `DedupReport` | N | Tras el dedup |
| `03_screening/journal.jsonl` | `JournalEntry` (`screening_ta`) | N | Desde el primer registro |
| `03_screening/decisions.json` | `list[ScreeningDecision]` | M | Al cerrar T/A; se reescribe tras el gate con `human_*`/`final_label` |
| `03_screening/gold.json` | `{record_id: bool}` (gold efectivo) | N | Si hay gold |
| `03_screening/metrics.json` | `ScreeningMetrics` (propuesta IA vs gold) | = | Si hay gold |
| `03_screening/exclusions.json` | `ExclusionBreakdown` (T/A+FT) | = | Tras el gate FT |
| `04_fulltext/retrieval.jsonl` | `JournalEntry` (`fulltext_retrieval`) | N | — |
| `04_fulltext/retrieval.json` | `list[{record_id, **RetrievalOutcome}]` | N | Al cerrar la recuperación |
| `04_fulltext/texts/<sha256(id)[:16]>.txt` | texto UTF-8 | N | Solo si se recuperó |
| `04_fulltext/journal.jsonl` | `JournalEntry` (`screening_ft`) | N | — |
| `04_fulltext/decisions.json` | `list[ScreeningDecision]`, uno por registro **buscado** | M | Al cerrar FT; se reescribe tras el gate |
| `04_fulltext/excluded.json` | `list[ExcludedReport]` (16b) | N | Tras el gate FT |
| `05_extraction/journal.jsonl`, `journal_2.jsonl` | `JournalEntry` (`extraccion`, `extraccion_2`) | N | — |
| `05_extraction/{extractions,agreement}.json` | = | = | — |
| `06_synthesis/journal.jsonl` | `JournalEntry` (`sintesis`, `record_id="sintesis"`, `output={narrative}`) | N | — |
| `06_synthesis/verification.jsonl` | `JournalEntry` (`verificacion`, `record_id="verificacion"`, `output=VerificationReport`) | N | — |
| `06_synthesis/verification.json` | = | = | — |
| `07_rob/journal.jsonl`, `07_rob/assessments.json` | N / = | | — |
| `08_meta/meta_analysis.json` | = | = | — |
| `<gate>/review_request.yml` | YAML (§4.3) | M | Cuando el gate requiere humano |
| `<gate>/decision.template.yml` | YAML con comentarios | N | Junto a la solicitud |
| `<gate>/decision.yml` | `HumanDecision` (lo escribe el humano) | M | — |
| `manifest.yml` | YAML | M | Al evaluar el gate `reporte`, **después** del gate (cualquier resultado); se reescribe en cada invocación que lo alcanza |
| `deliverable/excluidos_texto_completo.md` | 16b en Markdown | N | Con el resto del entregable |
| `deliverable/{prisma_flow,metodologia,checklist_s,checklist_traice}.md`, `deliverable/interop/prisma2020_flow.csv` | — | M | — |

`<gate>` ∈ `GATED_STAGES = ("screening_ta", "screening_ft", "extraccion", "rob", "reporte")`;
los ficheros del gate siguen en `run_dir/<gate>/`, como hoy.

### 4.3 Campos

**`RunInfo` (`run.json`).**
- Identidad: `schema_version`, `slug`, `timestamp`, `started_utc`, `engine_version` (`revisia.__version__`), `python_version`.
- Parámetros: `max_results: int`, `mailto_set: bool` (nunca el correo).
- Huellas: `protocol_sha256: dict[relpath, hex]` sobre `00_protocol/`; `prompt_sha256: dict["<agente>/v1.md", hex]` sobre `revisia/prompts/`.
- Historia: `resumes: list[utc]`, `interruptions: list[{utc, stage, error}]` (error redactado con `_http.redact_secrets`).
- Estado: `status: Literal["running","paused","rejected","completed","interrupted"]`, `stage: str | None`, `updated_utc`.

**`LLMCall` (líneas de `llm_calls.jsonl`)** = todos los campos de `RunMeta` más:
- `stage: Literal["screening_ta","screening_ft","extraccion","extraccion_2","rob","sintesis","verificacion"]`;
- `record_id: str | None` (`"sintesis"`/`"verificacion"` en las etapas globales);
- `role: str | None` (`"member:<i>"` en el ensemble T/A).

Append-only, en orden de finalización de la llamada. Una caída puede dejar
llamadas huérfanas (llamadas reales cuyo resultado no llegó al diario): son
válidas.

**`JournalEntry`**: `schema_version`, `stage`, `record_id`, `input_sha256`,
`output: dict`, `metas: list[LLMCall]`, `timestamp_utc`. La clave es
`(record_id, input_sha256)`; una entrada cuyo `input_sha256` ya no corresponde a
las entradas vigentes queda obsoleta, pero es válida. `output` por etapa:
`ScreeningDecision` (T/A y FT, sin campos humanos), `RetrievalOutcome`,
`ExtractionRecord`, `RoBAssessment`, `{narrative}`, `VerificationReport`.

**`SearchLog`**: `schema_version`, `started_utc`, `finished_utc`,
`max_results`, `mailto_set`, `entries: list[SearchLogEntry]`. Hay una entrada
por base declarada (incluidas las `manual_only`), una por fichero de
`imported/` y una `injected` si la búsqueda vino de `search_fn`.

| Campo de `SearchLogEntry` | Tipo y significado |
|---|---|
| `database` | Nombre tal cual en `protocol.yml`; `"imported/<fichero>"`; `"search_fn"` |
| `db_key` | `str` |
| `kind` | `database \| manual_import \| injected` |
| `declared` | `bool` (`false` para el OpenAlex por defecto cuando `databases: []`) |
| `backend` | nombre de la función o `null` |
| `status` | `ok \| failed \| manual_only \| unknown` |
| `source_db` | `list[str]`: valores distintos de `SearchRecord.source_db` devueltos |
| `query`, `query_origin`, `query_file`, `query_sha256` | cadena efectiva; `file \| question_fallback \| null`; `"00_protocol/search_strings/<key>.txt" \| null`; `sha256_text(query)` |
| `max_results` | `int \| null` |
| `started_utc`, `finished_utc` | `str \| null` |
| `n_returned` | `int` |
| `error` | `str \| null`, redactado |
| `file_sha256` | hash de los bytes, solo en `manual_import` |

**`DedupReport`**: `schema_version`, `n_in`, `n_out`,
`duplicates: list[{record_id, source_db, kept_record_id, key}]`,
`renamed: list[{from_id, to_id}]`.

**`RetrievalOutcome`**: `available: bool`, `source_url`, `reason:
Literal["sin_url_oa","sin_httpx","error_http","texto_vacio","no_disponible"] | None`
(nulo ⇔ `available`), `detail` (redactado), `n_chars`, `text_sha256`, `text_file`.

**`ScreeningDecision`** gana tres campos opcionales: `fulltext_status:
Literal["retrieved","not_retrieved"] | None`, `human_reason: str | None` y
`human_actor: str | None`. Un registro no recuperado tiene `votes: []` y
`ensemble_label: None`.

**`ExcludedReport`** (16b): `record_id`, `title`, `year: int | None`,
`doi: str | None`, `reason: str`, `reason_source: Literal["human","ai"]`.

**`PrismaCounts`** queda con: `identified`, `identified_by_source`,
`duplicates_removed`, `removed_automation` (0), `removed_other` (0), `screened`,
`excluded_ta`, `excluded_ta_human`, `excluded_ta_ai`, `fulltext_sought`,
`fulltext_not_retrieved`, `fulltext_rescued`, `fulltext_assessed`,
`excluded_ft`, `excluded_ft_human`, `excluded_ft_ai`, `ft_exclusion_reasons`,
`included`. PR-0 añade los campos nuevos con default 0; PR-B retira
`fulltext_abstract_only` y añade un `model_validator(mode="before")` para
manifiestos antiguos (sin `fulltext_sought` ⇒ `sought = assessed`,
`not_retrieved = 0`, que es lo que de verdad pasó: se evaluaron con el
resumen). El auditor no usa los campos para detectar una corrida antigua: usa
la ausencia de `run.json`.

**`manifest.yml`** conserva el orden de sus primeras claves (`slug`,
`created_utc`, `timestamp`, `provenance`, `protocol`, `counts`, `llm_calls`,
`models_used`, `deterministic_token_level`) y añade:
- `run: {started_utc, resumes, engine_version, python_version, status}`;
- `autonomy_effective: {gate: nivel}` para los `GATED_STAGES`;
- `final_gate: {forced_human: bool, reason: "hallucination_flagged" | null}`.

`llm_calls` son todas las líneas de `llm_calls.jsonl`, en el mismo orden.

**`review_request.yml`** = `{"request_sha256": sha, **payload}`, con
`sha = canonical_sha256(payload)`. Ningún payload lleva rutas absolutas ni
horas (el hash tiene que ser estable entre reanudaciones). Claves comunes:
`schema_version`, `stage` y `autonomy` (la efectiva; `A1` cuando está forzada).

| Gate | Claves propias |
|---|---|
| `screening_ta` | `mode: exceptions \| label_all`; `n_screened`, `n_proposed_pass`, `n_proposed_exclude`; `records[]` ordenado por id: `{record_id, title, year, doi, source_db, proposal, votes[{model, label, confidence, rationale, criteria_violated}]}`; `must_label: [ids]` (vacío en A1); `quality{recall, recall_target, kappa, kappa_min, gold_positives, recall_meets_target} \| null` (null sin gold) y `ai_excluded: [ids]` (D7: qué etiquetar para que un recall bajo no bloquee la publicación) |
| `screening_ft` | `mode`; `n_sought`, `n_retrieved`, `n_not_retrieved`; `records[]`: `{record_id, title, year, doi, fulltext, fulltext_reason, fulltext_source_url, proposal \| null, confidence \| null, rationale \| null, criteria_violated}`; `must_label` (A0: todos los recuperados; A1: solo `unclear`); `must_resolve` (los `unclear`); `rescuable` (no recuperados) |
| `extraccion` | `n_studies`; `studies[{record_id, title, fields{key: {value, source_quote, status, confidence}}}]`; `second_extraction{n_studies, n_field_pairs, value_agreement, presence_kappa} \| null`; `artifact_sha256` = `canonical_sha256` de `extractions.json` |
| `rob` | `tool`, `n_studies`; `studies[{record_id, title, overall, domains[{domain, judgment, rationale, support_quote}]}]`; `artifact_sha256` de `assessments.json` |
| `reporte` | `forced_human`, `forced_reason`; `n_included`; `included: [ids]`; `verification{mode, n_checks, n_flagged, hallucination_flagged, flagged[{index, cited_id, claim (≤ 300 car.), note}]}` (`index` = posición en `verification.json.checks`); `must_adjudicate: [index]` (todas las marcadas); `documento_sha256` = `sha256_text` de `documento.md` |

**`decision.yml`** (`HumanDecision`, `extra="allow"` como hoy):
- `request_sha256: str`, obligatorio en gates humanos;
- `approved: StrictBool`;
- `actor: str = "human:desconocido"`, `reason: str | None`;
- `records: dict[str, RecordLabel]`, solo en `screening_*`, con `RecordLabel(label: Literal["include","exclude"] | None, reason: str | None)` (`extra="forbid"`; `label: null` cuenta como "no etiquetado", para que la plantilla pueda listar todos los registros);
- `flags: dict[str, FlagReview]`, solo en `reporte`, con clave = `index` de la cita marcada (entre comillas) y `FlagReview(verdict: Literal["false_positive"] | None, reason: str | None)` (`extra="forbid"`; `verdict: null` cuenta como "sin adjudicar"). Con `approved: true`, toda cita de `must_adjudicate` necesita `verdict: false_positive` y `reason` no vacía (D8). Con `approved: false`, `flags` se ignora.

**Ledger.** El esquema de `DecisionEntry` no cambia; cambian las convenciones
de `detail` y aparece la acción `label`.
`LEDGER_ACTIONS = {"approve", "reject", "auto-proceed", "label", "flag_review"}`.

| Acción | Contenido |
|---|---|
| `label` | stage `screening_ta \| screening_ft`, `target = record_id`, actor = el de `decision.yml`, `detail{from: label \| null, to, reason, rescue: bool, request_sha256, decision_sha256}` |
| `approve` / `reject` | `detail{request_sha256, decision_sha256, n_labels, forced_human, reason?, **extras de decision.yml}` |
| `flag_review` | stage `reporte`, `target = "flag:<index>"`, actor = el de `decision.yml`, `detail{cited_id, claim, verdict, reason, request_sha256, decision_sha256}` |
| `auto-proceed` | `actor = "agent:<stage>"`, `detail{reason, request_sha256}` |
| aprobación por `--auto-approve` | `actor = "auto-approve (demo)"`, `action = approve`, `n_labels = 0` |

`decision_sha256 = canonical_sha256(decision.model_dump(mode="json"))`. Las
`label` y `flag_review` de una decisión se escriben antes de su `approve`, en
orden de id o de índice; nunca acompañan a un `reject`. La tupla `(stage, action, target,
request_sha256, decision_sha256)` es única. La **decisión efectiva** de una
etapa es su última entrada `approve`, `reject` o `auto-proceed`
(`summarize_gates`).

### 4.4 Relaciones que deben cumplirse

Las verifica el auditor (check `arithmetic` y afines) y las garantiza el
pipeline. Cada una tiene su test en el lado que la produce.

*Búsqueda y dedup*

1. `counts.identified == len(01_search/records.json) == Σ n_returned` (entradas `ok`) `== Σ identified_by_source`, e `identified_by_source == Counter(source_db)` de `records.json`.
2. Toda entrada `failed` tiene `error` y `n_returned == 0`, y aparece en `failures.json`.
3. `query_origin == "file"` ⇔ `query_file` existe y `sha256_text(contenido.strip()) == query_sha256`.
4. `dedup.n_in == identified`; `n_in − n_out == len(duplicates) == duplicates_removed`; `n_out == screened == len(02_dedup/records.json)`; ids de `02_dedup/records.json` únicos.

*Cribado T/A*

5. `03_screening/decisions.json`: uno por registro de `02_dedup/records.json`, mismo orden, `len(votes) ==` número de miembros T/A y `ensemble_label == recall_biased_label(votes)`. Con el gate aprobado: `final_label == human_label or ensemble_label`, y `human_label ≠ null` ⇔ hay una `label` con ese `target` y el `decision_sha256` de la decisión efectiva, con `to == human_label` y `reason == human_reason`.
6. `excluded_ta == #(final == exclude)`; `excluded_ta_human + excluded_ta_ai == excluded_ta`; `fulltext_sought == screened − excluded_ta == #(final ∈ {include, unclear})`.

*Texto completo*

7. `04_fulltext/decisions.json`: uno por registro buscado. `retrieved` ⇔ `retrieval.available` ⇔ `len(votes) == 1`. Tras aprobar FT: ningún `final == unclear`; un no recuperado sin etiqueta humana tiene `final == null`; un rescate tiene `human_reason`; con FT en A0 y aprobación humana, todo recuperado tiene `human_label`.
8. `fulltext_not_retrieved == #(no recuperado ∧ human == null)`; `fulltext_rescued == #(no recuperado ∧ human ≠ null)`; `fulltext_assessed == fulltext_sought − fulltext_not_retrieved == #(final ≠ null)`.
9. `excluded_ft == #(final == exclude) == len(excluded.json) == Σ ft_exclusion_reasons`; `ft_exclusion_reasons == Counter(reason)` de `excluded.json`; `reason_source == "human"` ⇔ `human_label == "exclude"`; `excluded_ft_human + excluded_ft_ai == excluded_ft`.
10. `included == fulltext_assessed − excluded_ft == #(final == include) == len(extractions.json) == len(assessments.json)`; `exclusions.total_excluded == excluded_ta + excluded_ft`.
11. CSV PRISMA2020: `dbr_sought_reports = fulltext_sought`, `dbr_notretrieved_reports = fulltext_not_retrieved`, `dbr_assessed = fulltext_assessed`, `records_excluded = excluded_ta`, `new_studies = included`.

*Diarios y llamadas*

12. Cada meta de cada línea de diario aparece idéntica en `llm_calls.jsonl`, con su `stage` y `record_id`. Metas por línea: `screening_ta` = número de miembros; `screening_ft`, `extraccion*`, `rob`, `sintesis` = 1; `fulltext_retrieval` = 0; `verificacion` = 0, o `n_checks` en modo `agent`.
13. Cada consolidado (`decisions.json`, `extractions.json`, …) coincide, sin campos humanos, con una línea del diario de su etapa para ese `record_id`.

*`run.json`, gates y manifiesto*

14. `run.json.started_utc ≤` toda marca de `llm_calls`, ledger y log de búsqueda `≤ manifest.created_utc` (tolerancia 2 s); `resumes` ascendente; `protocol_sha256 ==` huella recalculada de `00_protocol/`.
15. `request_sha256 == canonical_sha256(yaml.safe_load(review_request.yml) sin request_sha256)`, y es el que llevan la `decision.yml` y las entradas `approve`/`reject`/`label` de la decisión efectiva. `artifact_sha256`/`documento_sha256` coinciden con el disco.
16. Las `label` y `flag_review` van antes de su `approve`; no acompañan a un `reject`; la tupla de §4.3 es única.
17. `manifest.final_gate.forced_human` ⇔ `verification.hallucination_flagged`, y en ese caso la decisión efectiva de `reporte` es humana (`approve`/`reject` con `forced_human: true`), nunca `auto-approve` ni `auto-proceed`. Si es `approve`, cada índice de `must_adjudicate` tiene una `flag_review` con `verdict: false_positive`, razón, el mismo actor y el `decision_sha256` de ese `approve`.
18. `run.json.status == "completed"` ⇒ la decisión efectiva de `reporte` es `approve`.

### 4.5 Qué contiene PR-0 en código

- `revisia/schemas/artifacts.py`: `ARTIFACT_SCHEMA_VERSION`, `RunInfo`, `LLMCall`, `JournalEntry`, `SearchLog`, `SearchLogEntry`, `DedupReport`, `RetrievalOutcome`, `ExcludedReport`, `GateSummary`, `JournalStage`, `LLMStage`, `FulltextReason`, `RunStatus`, `JOURNAL_PATHS`, `GATED_STAGES`.
- `revisia/provenance/runmeta.py`: `canonical_json`, `canonical_sha256`.
- `revisia/provenance/ledger.py`: `LEDGER_ACTIONS`, `HUMAN_ACTOR_PREFIX = "human:"`, `AUTO_APPROVE_ACTOR = "auto-approve (demo)"`, `summarize_gates(entries) -> dict[str, GateSummary]` (decisión efectiva por etapa, actor, `request_sha256`, número de etiquetas y de marcas adjudicadas).
- `revisia/config.py`: `KNOWN_THRESHOLDS = {"kappa_min", "recall_target", "wmcc_fn_weight"}`.
- Campos opcionales de `ScreeningDecision` y campos nuevos de `PrismaCounts` (aditivos, sin cambiar comportamiento).
- `tests/fakes.py`: infraestructura de test compartida por todas las pistas. `ScriptedProvider` (etiqueta por palabra clave, `fail_at=k` para simular un 429, contador de llamadas; conserva `provider="fake"` y `deterministic=True`) y los `fetch_fn` de prueba (`fetch_disponible`, `fetch_no_disponible(ids)`).
- Este spec y los tres planes de implementación.

## 5. PR-A · `feat/ola1-preflight` (M6)

**Módulo nuevo `revisia/llm/preflight.py`.**

```python
@dataclass(frozen=True, slots=True)
class Requirement:
    sdk_module: str | None; extra: str | None; env_var: str | None
    binary: str | None; runtime_callback: bool = False
PROVIDER_REQUIREMENTS: dict[str, Requirement]
@dataclass(frozen=True, slots=True)
class PreflightIssue:
    level: Literal["error", "warning"]; where: str; message: str
@dataclass(frozen=True, slots=True)
class PreflightReport:
    issues: tuple[PreflightIssue, ...]   # .errors · .warnings · .ok
class PreflightError(ValueError): ...
PreflightContext = Literal["validate", "run", "resume"]
def stages_in_use(protocol) -> list[tuple[str, ProviderConfig]]
def check_provider(cfg, *, where, context, env, find_spec, which) -> list[PreflightIssue]
def check_databases(protocol, protocol_dir, *, find_spec) -> list[PreflightIssue]
def check_retired(protocol, today) -> list[PreflightIssue]
def preflight(protocol, protocol_dir, *, context: PreflightContext, mailto: str | None = None,
              env=None, find_spec=None, which=None, today=None) -> PreflightReport
```

`context` decide tres cosas: el callback de `agent` solo existe en tiempo de
corrida (`run`/`resume`: error si falta; `validate`: aviso); el aviso de
`mailto` solo tiene sentido en `run`; en `resume` la búsqueda está congelada y
se saltan las comprobaciones de bases y de búsqueda.

`PROVIDER_REQUIREMENTS`, verificado contra los proveedores y los extras de
`pyproject.toml`:

| Proveedor | SDK | Extra | Variable | Otro |
|---|---|---|---|---|
| `gemini` | `google.genai` | `gemini` | `GEMINI_API_KEY` | — |
| `openai` | `openai` | `openai` | `OPENAI_API_KEY` | — |
| `anthropic` | `anthropic` | `anthropic` | `ANTHROPIC_API_KEY` | — |
| `local_openai` | `openai` | `local` | — (no se exige) | — |
| `zai` | `openai` | `zai` | `ZAI_API_KEY` | — |
| `openrouter` | `openai` | `openrouter` | `OPENROUTER_API_KEY` | — |
| `claude_code` | — | — | — | binario `claude` |
| `agent` | — | — | — | callback registrado |
| `fake` | — | — | — | — |

`stages_in_use` devuelve los proveedores que el pipeline **de verdad** usará:
miembros T/A (`screeners_for`), FT, extracción, primer miembro de
`ensemble_llm["extraccion"]` si existe (aviso si hay más de uno: solo se usa el
primero), RoB y síntesis (que también hace de juez en `grounding: agent`).
Una etapa sin proveedor ni `default` es error.

Errores: proveedor desconocido; SDK no importable (con `uv sync --extra <extra>`
sugerido; `find_spec` envuelto en `try/except ModuleNotFoundError`, porque
`find_spec("google.genai")` lanza si falta `google`); variable de la key
ausente; `claude` no encontrado; `effort` fuera de `claude_code`; etapa sin
proveedor; base desconocida (ni en `BACKENDS` ni en `MANUAL_ONLY`); modelo
retirado (absorbe `_retired_model_problems`, `cli.py:66-89`); `agent` sin
callback en `run`/`resume`; `httpx` ausente con alguna base con backend.

Avisos: base con backend sin `search_strings/<key>.txt` o con el fichero vacío
(se usará la pregunta: PRISMA-S 8); base manual sin `imported/`;
`databases: []` (se usará OpenAlex); `agent` en `validate` (el callback solo
existe en tiempo de corrida); `httpx` ausente con solo bases manuales (todo
quedará como no recuperado); `run` sin `mailto` (sin Unpaywall ni ID Converter,
más no recuperados).

`env`, `find_spec` y `which` son inyectables: los tests no dependen del venv.
Dos tests impiden la deriva entre la tabla y el código:
`test_preflight_cubre_todos_los_proveedores_del_registro` (claves de
`PROVIDER_REQUIREMENTS` == `available_providers()`) y
`test_preflight_env_key_coincide_con_la_del_proveedor` (contra los `env_key`
de las clases y el literal de `gemini.py:43`).

**`agents/search_backends.py`.** `MANUAL_ONLY` se amplía con `cinahl`,
`cochrane`, `cochranelibrary`, `central`, `proquest`, `econlit`, `jstor`,
`ieeexplore`, `acm`, `sciencedirect`, `ebsco` y `ovid` (claves `db_key`).

**`cli.py`.**
- `_load_dotenv()` al inicio de `main` (`find_dotenv(usecwd=True)`, `override=False`). Los tests de "falta la key" la sustituyen por un no-op.
- `_cmd_validate` imprime los problemas del preflight agrupados por nivel y devuelve `2` ante cualquier error (hoy solo por modelos retirados). Deja de imprimir "Protocolo válido" si hay errores.
- `run`: el preflight corre antes de crear la carpeta (como ya hace la comprobación de modelos retirados, `cli.py:523-529`); con errores imprime la lista y sale con `2` sin crear `runs_root`.

**Tests nuevos** (todos con `env`, `find_spec` y `which` falsos):
`test_preflight_cubre_todos_los_proveedores_del_registro`,
`test_preflight_env_key_coincide_con_la_del_proveedor`,
`test_preflight_sdk_ausente_es_error_con_extra_sugerido`,
`test_preflight_paquete_padre_ausente_no_revienta`,
`test_preflight_key_ausente_es_error`,
`test_preflight_local_openai_no_exige_key`,
`test_preflight_claude_code_sin_binario_es_error`,
`test_preflight_agent_sin_callback_error_en_run_aviso_en_validate`,
`test_preflight_effort_fuera_de_claude_code_es_error`,
`test_preflight_proveedor_desconocido_es_error`,
`test_preflight_etapa_sin_proveedor_ni_default_es_error` (M6: FT sin proveedor se detecta antes de cribar),
`test_preflight_revisa_ensemble_y_segundo_extractor`,
`test_preflight_base_desconocida_es_error`,
`test_preflight_bases_de_suscripcion_son_manuales`,
`test_preflight_manual_sin_imported_avisa`,
`test_preflight_backend_sin_cadena_avisa`,
`test_preflight_httpx_ausente_es_error_con_bases_con_backend`,
`test_preflight_sin_mailto_avisa`,
`test_cli_validate_sale_2_con_error_de_preflight` (M6: hoy devuelve 0),
`test_cli_run_preflight_falla_sin_crear_runs_root`,
`test_cli_carga_dotenv_sin_sobrescribir_el_entorno`.

## 6. PR-B · `feat/ola1-flujo-prisma` (M11, M23)

**`agents/fulltext.py`.** `FullText` gana `reason: FulltextReason | None` y
`detail: str | None` (redactado). Cada rama de fallo pone su motivo: sin URL de
acceso abierto (`fulltext.py:126`, `sin_url_oa`), sin `httpx` (`:130`,
`sin_httpx`), error HTTP o de parseo (`:138`, `error_http`), texto vacío
(`:146`, `texto_vacio`). El fallback sigue llevando el abstract en `text` por
compatibilidad; el pipeline lo ignora.

**`orchestration/pipeline.py`, solo el bloque FT y los conteos.**
- Un registro con `available=False` **no se criba con IA**: se registra como `ScreeningDecision(phase="fulltext", fulltext_status="not_retrieved", votes=[], ensemble_label=None)` y no entra en `included`.
- Los recuperados se criban como hoy, con `fulltext_status="retrieved"`.
- `PrismaCounts` se rellena con `fulltext_sought = len(passed_ta)`, `fulltext_not_retrieved`, `fulltext_rescued = 0` (los rescates llegan en PR-D), `fulltext_assessed = sought − not_retrieved`, `excluded_ft_ai = excluded_ft` y `excluded_ft_human = 0` (sin etiquetas humanas todavía) e `included` = los `include`. Mientras no exista PR-D, un `unclear` de FT sigue contando como incluido; PR-D lo convierte en pendiente humano.

**`exclusions.py`.** `compute_ft_excluded(decisions, records) ->
list[ExcludedReport]`: la razón es la humana si el humano excluyó (desde PR-D);
si no, el primer `criteria_violated` de la IA o "criterio no especificado",
con `reason_source` explícito. `ft_exclusion_reasons` pasa a derivarse de esta
lista.

**`exports/prisma_flow.py`.** Se retira `fulltext_abstract_only` (con el
validador de §4.3). El diagrama Mermaid gana las cajas "Informes buscados para
recuperación", "Informes no recuperados" y "Informes evaluados para
elegibilidad" (más "rescatados por el revisor" si `fulltext_rescued > 0`), y
la caja de excluidos desglosa humano/IA. La tabla Markdown sigue las mismas
cajas. Función nueva `render_excluded_reports(list[ExcludedReport]) -> str`
para `deliverable/excluidos_texto_completo.md` (16b: título, año, DOI, razón y
su origen).

**`exports/interop.py`.** `dbr_sought_reports`, `dbr_notretrieved_reports` y
`dbr_assessed` toman los conteos reales.

**`exports/methods.py`.** La línea de conteos informa de buscados, no
recuperados y evaluados.

**`.gitignore`.** Las líneas 14-21 pasan a ser `runs/` con un comentario que
explique D11. El README deja de sugerir que `manifest.yml` y `deliverable/` se
versionan (lo hace el integrador, §10).

**Tests nuevos:**
`test_fetch_fulltext_registra_motivo` (parametrizado: sin URL, sin httpx, error HTTP, texto vacío),
`test_ft_no_recuperado_no_se_criba_con_ia` (M11: el proveedor FT no se llama para él; cuenta como no recuperado y no entra en extracción),
`test_flow_diagram_buscados_no_recuperados_evaluados`,
`test_prisma_csv_dbr_notretrieved_real` (M11: hoy vale 0 literal),
`test_counts_manifiesto_antiguo_se_lee_sin_mentir`,
`test_excluidos_16b_con_razon_y_origen`,
`test_methods_reporta_buscados_y_no_recuperados`.

## 7. PR-C · `feat/ola1-reanudacion` (A9, M12, `request_sha256`)

La PR más grande. Empieza con un **refactor puro** y sigue con un commit por
etapa con diario.

**Refactor puro de `run_pipeline` (primer commit, suite en verde, sin cambio de
comportamiento).** Un `@dataclass _Run` con el estado compartido (protocolo,
directorio de la instantánea, contexto, pregunta, criterios, formulario,
`auto_approve`, `mailto`, métricas) y dos métodos: `gate(stage, payload, *,
records=None, force_human=False) -> GateResult` y `stop(gate, stage) ->
PipelineResult | None`, que sustituye los cinco bloques de gate casi iguales
(`pipeline.py:251-258,304-307,374-380,409-412,591-601`). Funciones privadas por
etapa, de unas 60 líneas: `_search`, `_dedup`, `_screen_ta`, `_fulltext`,
`_extract`, `_assess_rob`, `_synthesize_and_verify`, `_build_counts`,
`_write_deliverables`. `run_pipeline` queda en unas 90 líneas y conserva su
firma pública; `PipelineResult` gana `stage: str | None`.

**Módulos nuevos en `revisia/orchestration/`.**

- `snapshot.py`: `SNAPSHOT_DIR = "00_protocol"`, `SNAPSHOT_FILES`, `ProtocolMismatchError(ValueError)`, `protocol_fingerprint(dir) -> dict[str, str]` (incluye `search_strings/*.txt`; texto con CRLF→LF), `prompt_fingerprint() -> dict[str, str]`, `read_run_info`/`write_run_info` (escritura atómica), `ensure_snapshot(protocol_dir, run_ctx, *, max_results, mailto) -> tuple[Path, RunInfo]`.
  - Sin `run.json`: copia el protocolo y crea `RunInfo(status="running")`.
  - Con `run.json`: verifica que `00_protocol/` sigue coincidiendo con `protocol_sha256` y que `prompt_fingerprint()` coincide con lo guardado. Si se pasó también el `protocol_dir` original, compara su huella. Cualquier diferencia lanza `ProtocolMismatchError` con la lista de ficheros distintos. Si todo coincide, añade la hora a `resumes`.
  - Devuelve `00_protocol/`, que pasa a ser **la única fuente** de criterios, formulario, efectos, gold y cadenas.
- `journal.py`: `JournalError(ValueError)`, `StageJournal(run_ctx, stage)` con `lookup(record_id, input_sha256)` y `append(...)`, y `journaled(journal, *, record_id, inputs, model, compute, run_ctx, role_of=None) -> T`.
  - Al cargar: si la última línea está truncada (caída a mitad de escritura), se recorta a la última línea completa; una línea corrupta en medio, o dos líneas con la misma clave y distinta salida, lanzan `JournalError`.
  - `append`: modo `"a"`, `flush` y `os.fsync`.
  - `journaled`: `canonical_sha256(inputs)` → `lookup` → si no hay entrada, `compute()`, después `run_ctx.record_meta(...)` por cada meta y **después** `journal.append`. Puede haber llamadas huérfanas; nunca una decisión sin sus llamadas.
- `search_stage.py`: `run_search(protocol, *, source_dir, strings_dir, question, max_results, mailto, search_fn, run_ctx) -> list[SearchRecord]` y `multi_database_search(...) -> tuple[list[SearchRecord], list[SearchLogEntry]]`.
  - Si `01_search/log.json` existe, carga `records.json` sin llamar a nada (tampoco a `search_fn`).
  - Si no, busca y escribe en orden `records.json`, `log.json` (marca de completitud) y `failures.json`, derivado del log.
  - Las cadenas se leen de `00_protocol/search_strings/`.
  - `imported/` se recorre fichero a fichero con el nuevo `manual_import.import_file(path)` dentro de un `try`: un RIS en UTF-16 queda como `failed` en el log y ya no aborta la corrida (cierra en parte M7).
  - `pipeline._multi_database_search` se conserva como envoltorio con su firma y su tupla de retorno, porque los usa `tests/test_search_multibase.py`.

**Cambios por fichero.**

| Fichero | Cambio |
|---|---|
| `orchestration/run_context.py` | `RunContext(slug, runs_root, timestamp)` lanza `RunDirExistsError` si la carpeta existe y no está vacía (con diarios, dos `run` en el mismo segundo reanudarían en silencio la corrida ajena). `RunContext.open(run_dir)` para reanudar. `metas: list[LLMCall]` cargadas de `llm_calls.jsonl`; `record_meta(meta, *, stage, record_id=None, role=None) -> LLMCall` escribe al instante. `write_json` atómico (temporal + `os.replace`). `class RunInterrupted(RuntimeError)` con `run_dir` y `stage`. `write_manifest` toma `llm_calls` del fichero y añade los bloques de §4.3. |
| `orchestration/hitl.py` | `review_gate` calcula `sha = canonical_sha256(payload)`, escribe `review_request.yml` y `decision.template.yml` y exige `request_sha256` en `decision.yml`. Un hash distinto **pausa sin aplicar nada** ("decision.yml responde a otra solicitud"). Ledger idempotente (§4.3). Sin `decision.yml`, si el ledger ya tiene una decisión efectiva con ese hash, se reutiliza (el ledger manda; `decision.yml` es solo el canal de entrada). El mensaje de pausa nombra la plantilla y la orden de reanudar. |
| `agents/dedup.py` | `deduplicate_with_report(records) -> tuple[list[SearchRecord], DedupReport]`: un id repetido entre los conservados se renombra de forma determinista a `<id>#2`, `#3`… y queda en `renamed`. `deduplicate` se conserva como envoltorio. |
| `ingest/manual_import.py` | `import_file(path) -> list[SearchRecord]`; `import_directory` la usa. |
| `config.py` | `load_protocol(protocol_dir, *, default_slug=None)`: al reanudar se pasa `run.json.slug`. |
| `rag/grounding.py` | `make_provider_judge(..., on_meta: Callable[[RunMeta], None] \| None = None)`: las llamadas del juez llegan a `llm_calls`. |
| `metrics.py` | `compute_screening_metrics` recibe el gold efectivo y el pipeline lo guarda en `03_screening/gold.json`. |
| `orchestration/flow.py` | `resume_review(run_dir, *, protocol_dir=None, auto_approve=False, mailto=None) -> PipelineResult`. `run_review` no cambia de firma. |
| `agent_driver.py` | `run_review_with_agent(..., run_dir: str \| Path \| None = None)` para reanudar. El default `auto_approve=True` se queda (A8 es Ola 2). |
| `memory/brain.py` | `has_run(slug, timestamp) -> bool`: `--brain` no sedimenta dos veces la misma corrida. |
| `exports/checklist.py` | `render_prisma_s_checklist(..., search_log=None)`: los ítems 8 y 13 salen del log (cadena por base, fecha del motor), señalando dónde se usó la pregunta como cadena y si la fecha difiere de `search_window.executed`; ídem el ítem 4 del checklist de resúmenes. |
| `exports/methods.py` | Fecha de búsqueda tomada del log; las cadenas se citan en `00_protocol/search_strings/`. |
| `cli.py` | `protocol_dir` pasa a `nargs="?"`; `--resume RUN_DIR`; `--max` con default `None` (50 en corrida nueva; al reanudar manda `run.json`, con aviso si se pasa otro). `RunInterrupted` → `rc 3` con la orden de reanudar; `ProtocolMismatchError`, `JournalError`, `RunDirExistsError` y `PreflightError` → `rc 2`; `KeyboardInterrupt` → `130`. La pausa imprime `Reanuda con: revisia run --resume <run_dir>`. `has_run` antes de sedimentar. |

**Diario por etapa (un commit cada una, en este orden).** T/A → recuperación
con caché de texto → FT → extracción y 2.º extractor → RoB → síntesis y
verificación. Las entradas de `input_sha256`:

| Etapa | `inputs` |
|---|---|
| T/A | `{title, abstract, question, criteria, miembros[(model_name, temperature, seed)]}` |
| recuperación | `{record_id, doi, extra relevantes, mailto_set}` |
| FT | lo de T/A con el proveedor FT + `text_sha256` |
| extracción | `{record_id, text_sha256, form_fields, proveedor}` |
| RoB | lo anterior + `canonical_sha256(extracción)` + `tool` |
| síntesis | `[(id, title)]` de los incluidos + hash de las extracciones + proveedor |
| verificación | `sha256(narrativa)` + hash de las fuentes + modo |

`run_pipeline` corre el preflight al empezar, con `context="resume"` si ya
existe `01_search/log.json` y `"run"` si no; un error lanza `PreflightError`.
Toda excepción que no sea de configuración
se registra en `run.json.interruptions`, pone `status="interrupted"` y se
relanza como `RunInterrupted(...) from exc`.

**Helpers de test** (`tests/hitl_helpers.py`, los usan PR-D y PR-E):

```python
def responder_gate(run_dir: Path, stage: str, *, approved=True, actor="human:revisora",
                   reason=None, records: dict[str, dict] | None = None) -> Path
def correr_hasta(protocol, protocol_dir, ctx, *, search_fn, fetch_fn=None,
                 etiquetar: Callable[[str, dict], dict | None] | None = None,
                 parar_en: str | None = None, max_vueltas: int = 10) -> PipelineResult
```

`responder_gate` lee el `request_sha256` de la solicitud vigente y escribe
`decision.yml`.

**Tests nuevos:**
`test_journal_recupera_ultima_linea_truncada`,
`test_journal_linea_corrupta_intermedia_es_error`,
`test_journal_entrada_obsoleta_por_input_sha_se_recalcula`,
`test_run_context_vuelca_llm_calls_al_registrar`,
`test_run_context_nuevo_no_reutiliza_carpeta_existente`,
`test_snapshot_y_run_json`,
`test_resume_con_protocolo_modificado_sale_2`,
`test_resume_con_prompt_modificado_falla`,
`test_resume_toma_el_slug_de_run_json` (el demo no declara `slug`),
`test_resume_de_corrida_anterior_a_la_ola_1_sale_2` (D13),
`test_search_log_por_base` (fichero o pregunta, hash, n, fallo redactado, `manual_only`, importación con hash),
`test_import_ris_utf16_no_aborta` (M7),
`test_search_no_se_repite_al_reanudar` (`search_fn` que lanza si se llama dos veces),
`test_records_json_previo_a_fusion_de_dedup`,
`test_dedup_ids_repetidos_se_desambiguan` (RIS con prefijo `doi.org` más OpenAlex),
`test_429_a_mitad_del_cribado_conserva_diario_y_reanuda` (A9: falla en la llamada k; al reanudar cada registro se criba una sola vez),
`test_reanudar_no_repite_llamadas_llm` (contador: 0 llamadas en la segunda pasada),
`test_gate_exige_request_sha256`,
`test_decision_obsoleta_pausa_sin_aplicar`,
`test_ledger_idempotente_al_reanudar`,
`test_ledger_reconstruye_decision_sin_decision_yml`,
`test_gate_final_converge_tras_reanudar`,
`test_payloads_estables_entre_reanudaciones_y_sin_rutas_absolutas` (los cinco gates),
`test_request_sha256_recomputable_desde_yaml`,
`test_gold_efectivo_persistido`,
`test_cli_run_resume_reanuda_la_misma_carpeta`,
`test_cli_interrupcion_rc_3_con_instrucciones`,
`test_brain_no_sedimenta_dos_veces`,
`test_llamadas_del_juez_quedan_en_llm_calls`,
`test_prisma_s_desde_el_log_de_busqueda`.

## 8. PR-D · `feat/ola1-hitl-por-registro` (C1, M5, M13)

**Módulo nuevo `revisia/orchestration/gates.py`** (funciones puras):
`ta_payload`, `ta_policy`, `ft_payload`, `ft_policy`, `extraction_payload`,
`rob_payload`, `report_payload` (claves de §4.3) y
`apply_labels(decisions, labels, actor) -> list[ScreeningDecision]`.

**`orchestration/hitl.py`.**

```python
class RecordLabel(BaseModel): ...            # §4.3, extra="forbid"
class FlagReview(BaseModel): ...             # §4.3, extra="forbid"
class HumanDecision(BaseModel):              # + request_sha256, records, flags
@dataclass(frozen=True, slots=True)
class RecordPolicy:
    hints: tuple[RecordHint, ...]; must_label: frozenset[str]; must_resolve: frozenset[str]
    rescue_ids: frozenset[str]; reason_on_exclude: bool
@dataclass(frozen=True, slots=True)
class FlagPolicy:
    flagged: tuple[FlaggedClaim, ...]       # index, cited_id, claim, note
@dataclass(slots=True)
class GateResult:
    status: GateStatus; message: str; request_sha256: str | None = None
    actor: str | None = None; labels: dict[str, RecordLabel] = field(default_factory=dict)
    flag_reviews: dict[str, FlagReview] = field(default_factory=dict)
def review_gate(*, stage, autonomy, run_ctx, review_payload, auto_approve,
                records: RecordPolicy | None = None, flags: FlagPolicy | None = None,
                force_human: bool = False) -> GateResult
def render_decision_template(*, stage, autonomy, request_sha256, records, flags) -> str
```

Validación de `decision.yml` cuando su hash coincide:
- `records` en un gate sin `RecordPolicy`, o `flags` en un gate sin `FlagPolicy` → `DecisionFileError`;
- id o índice que no está en la solicitud → error que lo nombra;
- `exclude` sin `reason` cuando `reason_on_exclude` (FT) → error;
- etiqueta sobre un id de `rescue_ids` sin `reason` → error;
- con `approved: true`: ids de `must_label` o de `must_resolve` sin etiqueta, o índices de `must_adjudicate` sin `verdict: false_positive` y razón → un único error que lista hasta 20 y el total (D8);
- con `approved: false`, `flags` se ignora: rechazar no exige adjudicar.

La plantilla del gate `reporte` lista cada cita marcada como
`"<index>": {verdict: null, reason: null}`, con la afirmación y el motivo de
la marca en comentarios saneados. Su cabecera dice que, si alguna marca es
una alucinación real, hay que rechazar.

Con `--auto-approve` y sin `decision.yml`: si `must_resolve` no está vacío,
pausa (D9); si no, decisión sintética `auto-approve (demo)`. Con
`force_human=True`, `--auto-approve` y A2/A3 se ignoran.

**`orchestration/pipeline.py`.**
- Tras cada gate de cribado aprobado, `apply_labels` escribe `human_label`, `human_reason`, `human_actor` y `final_label` en `decisions.json` (D5: solo las etiquetas explícitas).
- FT: un `unclear` nunca pasa sin etiqueta humana; un rescate entra como evaluado por humano; `excluded_ft_human`/`excluded_ft_ai` y la razón humana llegan a 16b y a `ft_exclusion_reasons`.
- Métricas: siempre sobre `ensemble_label` (D6); `metrics.py:130` deja de usar `final_label`.
- M5: si `verification.hallucination_flagged`, el gate `reporte` se llama con `force_human=True` y con `FlagPolicy` (las citas marcadas de `verification.json`). El ledger recibe una `flag_review` por adjudicación antes del `approve`, y el manifiesto registra `final_gate.forced_human`.
- D7: el pipeline no aplica umbrales (lo hace el auditor), pero `screening_ta/review_request.yml` incluye `recall_target`, el recall medido y la lista de exclusiones IA. Así el revisor sabe, antes de aprobar, si para que la corrida sea publicable tiene que etiquetar esas exclusiones.

**M13: `exports/checklist.py` y `exports/methods.py`.**
`render_traice_checklist(..., gates: dict[str, GateSummary], autonomy_effective,
forced_human)` imprime la autonomía efectiva de los `GATED_STAGES` y, por gate,
quién decidió de verdad (humano, `auto-approve`, `auto-proceed`, pendiente).
Desaparece el texto fijo de `checklist.py:230`. `render_methods` recibe lo
mismo y sustituye las afirmaciones fijas (`methods.py:76,94,109,116`) por lo
que pasó; si algún gate de juicio no lo resolvió un humano, lo dice. El
checklist se escribe antes del gate final, así que ese gate figura como
"pendiente de la decisión final".

**Tests nuevos:**
`test_decision_records_id_desconocido_es_error`,
`test_records_en_gate_sin_registros_es_error`,
`test_records_en_extraccion_es_error`,
`test_ft_exclude_sin_reason_es_error`,
`test_ft_a0_aprobar_sin_etiquetar_todo_es_error`,
`test_ft_unclear_sin_resolver_impide_aprobar` (C1: hoy entra en extracción),
`test_auto_approve_no_resuelve_unclear_ft`,
`test_ta_a1_excepcion_humana_rescata_registro`,
`test_ta_a1_sin_tocar_conserva_human_label_none` (D5),
`test_ft_a0_exclusion_humana_en_todos`,
`test_rescate_de_no_recuperado_cuenta_como_evaluado`,
`test_no_recuperado_sin_rescate_permite_aprobar`,
`test_16b_razon_humana`,
`test_metricas_miden_la_propuesta_ia` (D6),
`test_template_invalido_hasta_rellenarlo`,
`test_template_sanea_saltos_de_linea_del_llm` (inyección YAML),
`test_review_request_ta_lista_votos_por_miembro`,
`test_extraccion_y_rob_payload_con_tabla_y_hash_del_artefacto`,
`test_gate_final_forzado_a_humano_si_hallucination_flagged` (M5: `reporte` en A2 y `--auto-approve` → pausa),
`test_aprobar_con_citas_marcadas_exige_adjudicar_cada_una` (D8: lista los índices sin adjudicar),
`test_adjudicacion_sin_razon_es_error`,
`test_rechazar_con_citas_marcadas_no_exige_adjudicar`,
`test_flags_en_gate_sin_marcas_es_error`,
`test_flag_review_en_el_ledger_antes_del_approve`,
`test_review_request_ta_informa_recall_y_exclusiones_ia` (D7),
`test_traice_autonomia_efectiva_y_actores_reales` (M13),
`test_methods_sin_texto_fijo_de_validacion_humana` (M13).

## 9. PR-E · `feat/ola1-auditor` (C3-auditor, A11, M5 en el auditor)

Se desarrolla en dos fases. La **fase 1** arranca en paralelo tras PR-0 y
trabaja con los artefactos que ya existen. La **fase 2** se rebasa sobre PR-D
y añade lo que consume los artefactos nuevos. Se abre una sola PR al terminar
la fase 2.

### 9.1 Estructura

`revisia/audit.py` pasa a ser el paquete `revisia/audit/`. La API pública
(`run_audit`, `render_audit_md`, `AuditReport`, `AuditCheck`) no cambia; el
primer commit es la partición sin cambio de comportamiento, con los 23 tests
actuales en verde.

| Módulo | Contenido |
|---|---|
| `__init__.py` | reexporta la API; `run_audit`; registro ordenado de checks (`CheckSpec(check_id, item_ref, stage, fn)`) y `_run_one` |
| `model.py` | `AuditCheck`; `AuditReport` (+ `state: RunState \| None`); `Status = PASS \| WARN \| FAIL \| N/A` |
| `artifacts.py` | `Loaded[T](path, present, value, error)`; `read_json`/`read_yaml`/`read_jsonl` que **nunca lanzan**; `RunArtifacts` y `load_run(run_dir)`; `AuditContext` con derivados cacheados |
| `state.py` | `RunState(status, reached, pending_stage)` y `derive_state()` |
| `checks_provenance.py` | `manifest`, `provenance`, `schemas`, `protocol_snapshot`, `prompts` |
| `checks_timing.py` | `timing`, `response_overlap` |
| `checks_hitl.py` | `ledger`, `hitl`, `request_hash`, `final_gate` |
| `checks_flow.py` | `stage_artifacts`, `arithmetic`, `exclusions`, `deliverable` |
| `checks_quality.py` | `gold`, `thresholds`, `grounding` |
| `checks_search.py` | `search_log`, `search_window`, `registration` |
| `render.py` | `render_audit_md`; `_md_cell` escapa `\|` y convierte saltos de línea en `<br>` |

Reglas:
- **Una fila por check, siempre:** la forma del informe es estable y comparable entre corridas.
- **Fail-closed:** `_run_one` envuelve cada check; si revienta, la fila es FAIL ("error interno del auditor (Tipo): … — la corrida no se considera verificada") y el resto sigue.
- **Carga robusta:** los loaders capturan `OSError`, `UnicodeDecodeError`, `JSONDecodeError`, `YAMLError`, `ValidationError` y `RecursionError`, y comprueban que la raíz sea mapa o lista según corresponda (hoy `_load_manifest`, `audit.py:66`, no lo hace). Usan `yaml.CSafeLoader` si está disponible: un manifiesto con miles de `llm_calls` tarda segundos con el loader puro.
- **Constantes importadas, no duplicadas:** `STAGES`, `JUDGMENT_STAGES`, `KNOWN_THRESHOLDS`, `GATED_STAGES`, `LEDGER_ACTIONS`, `summarize_gates`, `recall_biased_label`, `compute_exclusion_breakdown` y las funciones de `metrics.py` (con dos públicas nuevas: `kappa_from_matrix` y `wilson_interval(k, n, z=1.96)` para el detalle de `thresholds`).
- **CLI:** `_cmd_audit` (`cli.py:306-326`) solo gana el icono de `N/A` (➖) y el ancho de columna. Los códigos 0/1/2 se mantienen.

### 9.2 Estado de la corrida y `N/A`

`derive_state` usa `run.json` (si existe), el ledger validado y la presencia de
`<gate>/review_request.yml`:

- `rejected`: la decisión efectiva de algún gate es `reject`.
- `completed`: hay decisión efectiva `approve` en `reporte` (el actor lo juzga `final_gate`).
- `paused`: un gate sin decisión, con solicitud; `pending_stage` es ese gate.
- `interrupted`: `run.json.status == "interrupted"`, o un gate sin decisión y sin solicitud.
- `unknown`: ledger ilegible o vacío y sin `run.json`. Se exige todo.

Si la corrida está en `paused`, `interrupted` o `rejected` y la etapa de un
check no se alcanzó, la fila sale `N/A` ("no aplica: corrida en pausa en
`screening_ft`; se verificará al reanudar"). También sale `N/A`, en vez de
omitirse, un check cuya raíz ya dio FAIL (manifiesto ausente para
`provenance`). **Invariante, comprobado con un helper en todos los tests:**
si hay algún `N/A`, hay al menos un FAIL. Una pausa siempre deja `final_gate`
en FAIL, así que `N/A` no puede ocultar nada en una corrida publicable.
`publishable` sigue siendo `n_fail == 0`.

### 9.3 Checks

La columna "Etapa" es la que gobierna el `N/A` (— = siempre aplica). F1/F2 = fase.

| # | id | item_ref | Etapa | PASS | WARN | FAIL | F |
|---|---|---|---|---|---|---|---|
| 1 | `manifest` | PRISMA 27 / trAIce M2 | reporte | válido, con llamadas y modelos | 0 llamadas; algún `provider: fake` ("corrida de demostración, no evidencia") | ausente, YAML inválido o raíz no mapa | 1 |
| 2 | `provenance` | PRISMA 27 / trAIce M2 | reporte | `pipeline` | — | distinta o ausente | 1 |
| 3 | `schemas` | PRISMA 27 / trAIce M5 | — | k artefactos válidos | — | algún artefacto presente no carga o no valida su modelo (hasta 5 errores `ruta: loc: msg`) | 1 |
| 4 | `protocol_snapshot` | PRISMA 24b / trAIce M1 | protocolo | hashes coinciden; la instantánea coincide con `manifest.protocol` | ficheros en `00_protocol/` fuera de la lista de hashes | sin `run.json` ("anterior a la Ola 1", D13); hash distinto; fichero de la lista ausente; instantánea distinta de `manifest.protocol` | 2 |
| 5 | `prompts` | trAIce M6 | reporte | todas con `prompt_sha256` y `response_sha256` | sin llamadas | — (lo cubre `schemas`) | 1 |
| 6 | `timing` | PRISMA 27 / trAIce M2 | — | marcas dentro de límites; mediana entre llamadas | heurísticas (abajo); límite inferior no verificable | marca sin zona o no parseable; fuera de [`started_utc`, `created_utc`] ±2 s; ledger que retrocede > 2 s; `finished < started` en el log; `deterministic: true` con proveedor no fake | 1 |
| 7 | `ledger` | trAIce M8 / PRISMA 8 | — | N entradas | — | ausente o vacío; línea que no es JSON o no valida `DecisionEntry` (con número de línea; hoy se descarta en silencio, `audit.py:85-86`); `stage ∉ STAGES`; `action ∉ LEDGER_ACTIONS` (las `propose`/`exclude`/`verify` de C3); gates fuera del orden de `STAGES`; autonomía distinta de la efectiva | 1 |
| 8 | `hitl` | trAIce M8/R1 / PRISMA 8 | por etapa | humano en todas las etapas de juicio alcanzadas; recuento de etiquetas | actor `human:desconocido` | ver abajo | 1+2 |
| 9 | `request_hash` | trAIce M8 | por gate humano | k decisiones atadas a su solicitud | — | relación 15 rota; actor de `decision.yml` ≠ ledger; ids etiquetados fuera de la solicitud; ids de la solicitud ≠ ids de `decisions.json` | 2 |
| 10 | `final_gate` | trAIce M8 | — | `approve` humano | — | pausa ("en pausa en `X`"); interrumpida; `reject`; **`auto-approve`/`auto-proceed`** (antes WARN, D8); acción desconocida; relación 17 rota | 1 |
| 11 | `stage_artifacts` | PRISMA 16/27 | por etapa | todas las etapas alcanzadas con sus artefactos (§4.2) | — | falta un artefacto obligatorio de una etapa alcanzada | 1+2 |
| 12 | `arithmetic` | PRISMA 16 / trAIce R1 | reporte | k relaciones verificadas | alguna no verificable | alguna relación de §4.4 rota, con nombre y valores (más las de abajo) | 1+2 |
| 13 | `exclusions` | trAIce R1 | screening_ft | coincide con el recálculo | — | ausente o inválido en etapa alcanzada; distinto de `compute_exclusion_breakdown(TA+FT)`; `excluded_ta_human/ai` distintos del recálculo solo T/A | 1 |
| 14 | `deliverable` | PRISMA 16/16b/17/18/27 | reporte | completo | — | falta o está vacío alguno: los 8 de hoy + `checklist_s.md` + `checklist_abstracts.md` + `excluidos_texto_completo.md` (F2) + `meta_analisis.md` si hubo meta-análisis + `interop/prisma2020_flow.csv` | 1+2 |
| 15 | `gold` | trAIce M9/R2 | screening_ta | como hoy, sobre `ScreeningMetrics` validado | sin gold; κ o MCC `None`; gold o IA de una sola clase | — (la matriz ilegible la da `schemas`) | 1 |
| 16 | `thresholds` | trAIce M9/R2 / PRISMA 8, 24c | screening_ta | "recall 0.97 [IC95 0.90–0.99] ≥ 0.95 con 34 positivos; κ 0.71 ≥ 0.60" | κ bajo `kappa_min` (desviación a declarar); recall bajo umbral con **todas** las exclusiones IA de T/A etiquetadas por humano; recall que alcanza el umbral con menos de ⌈1/(1−umbral)⌉ positivos; umbral no medible; clave desconocida; ningún umbral declarado | recall bajo `recall_target` con alguna exclusión IA de T/A sin etiqueta humana (D7; el detalle lista cuántas y cómo remediarlo) | 1+2 |
| 17 | `grounding` | trAIce M8/M9 | sintesis | k citas, ninguna marcada; n/m incluidos citados | `checks: []` con incluidos > 0; citas marcadas, **todas** adjudicadas como falso positivo por un humano ("k citas marcadas, adjudicadas por <actor>: decláralo") | cita marcada sin `flag_review` humana en la decisión efectiva de `reporte` (D8); bandera distinta de recalcularla (`recompute_flag`); `exists_in_corpus: true` para un id que no está entre los incluidos | 1+2 |
| 18 | `search_log` | PRISMA-S 1/8/13/15 | busqueda | una entrada `ok` por base con cadena coincidente | `failed`; `question_fallback`; `n_returned == max_results` (resultados truncados); `manual_only` sin registros importados; `injected` | `log.json` ausente; base declarada sin entrada; `status: unknown`; relaciones 1-3 rotas; cadena distinta de `00_protocol/search_strings/<key>.txt` | 2 |
| 19 | `search_window` | PRISMA-S 9/13 | busqueda | fecha del motor (mínimo `started_utc` del log) y `from`/`to` declarados | `from`/`to` ausentes; `executed` tecleada distinta de la del motor; sin log, "fecha tecleada, no registrada por el motor" | — | 1+2 |
| 20 | `registration` | PRISMA 24a | — | como hoy, leyendo la instantánea si existe | como hoy | — | 1 |
| 21 | `response_overlap` | trAIce M2 | reporte | — | dos modelos distintos, no fake, con ≥ 10 llamadas cada uno, comparten ≥ 50 % de `response_sha256` (C3: los 46 hashes de Sonnet dentro de los de Opus; también delata A8) | — | 1 |

**`hitl` en detalle.** Fase 1: FAIL si la decisión efectiva de un gate de
juicio alcanzado no es de un actor `human:`; FAIL si hay cualquier actor
`auto-approve` en el ledger (D8); FAIL si se saltó un gate (etapa de juicio sin
decisión y otra posterior con decisión); FAIL si `exclusions.excluded_human`
supera el número de `label` con `to: exclude` (la vía independiente contra el
`excluded_human: 3` de C3, que funciona aunque falte `decisions.json`). Fase 2,
para T/A y FT, con L = `{target: to}` de las `label`, H = `{id: human_label}`
de `decisions.json` y D = `records` de `decision.yml`: FAIL si L ≠ H, si L ≠ D,
si dos etiquetas chocan, si `from` ≠ `ensemble_label`, si el actor de una
`label` ≠ el del `approve`, si en FT A0 hay un recuperado sin `human_label`, si
queda un `unclear` en FT, si una exclusión humana en FT no tiene razón o si un
no recuperado tiene `final_label` sin rescate.

**`arithmetic`, además de §4.4.** `len(votes)` igual al número de screeners y
cada `vote.model` entre ellos; claves de extracciones y evaluaciones iguales a
los incluidos y a su `study_id`; `assessment.tool == protocol.rob_tool`;
`extraction_agreement.n_studies` igual al subconjunto de doble extracción; cota
inferior de llamadas `len(llm_calls) ≥ screened·|ensemble T/A| +
fulltext_assessed_por_IA + 2·included (+ doble extracción) + 1` (decisiones sin
las llamadas que las produjeron delatan fabricación; es cota y no igualdad para
tolerar huérfanas); `models_used` y `deterministic_token_level` coherentes con
`llm_calls`; `n == tp+fp+fn+tn` y recall, lost evidence, precision, MCC, WMCC y
κ recalculados desde la matriz (`math.isclose(abs_tol=1e-9)`);
`wmcc_fn_weight` igual al del protocolo; las copias del manifiesto
(`exclusions`, `screening_metrics`, `verification`, `risk_of_bias`,
`extraction_agreement`, `meta_analysis`) iguales a sus ficheros; fase 2:
métricas recalculadas desde `decisions.json` y `gold.json` con
`ensemble_label`. Sin `run.json` se aplican las relaciones v0.7 (embudo
`excluded_ta + fulltext_assessed == screened`, `included` con `unclear`): la
corrida ya es no publicable por D13, pero el diagnóstico sigue siendo útil.

**`timing`, heurísticas.**
- WARN si hay ≥ 20 llamadas no fake y la **mediana de separación** entre marcas ordenadas es **< 5 ms**. C3 está unas 500 veces por debajo (140 llamadas en 1,3 ms). Una llamada real tarda ≥ 300 ms por API y ≥ 1 s con `claude -p`; incluso con 16 en paralelo la mediana quedaría por encima de 18 ms. La mediana no se mueve con pausas humanas de días. El mensaje menciona el caso de una API por lotes.
- WARN si hay ≥ 4 marcas del ledger y ≥ 50 % sin fracción de segundo: `isoformat()` solo omite los microsegundos si valen exactamente 0, así que eso huele a horas tecleadas (como en C3).
- La exención de las heurísticas exige `provider == "fake" and deterministic`; `deterministic: true` con otro proveedor es FAIL, porque todos los proveedores reales ponen `False`.
- Sin `run.json`, el límite inferior sale de `manifest.timestamp` si cumple `%Y%m%d-%H%M%S` (es UTC, `cli.py:177`); si no se puede parsear ("TEST"), WARN "límite inferior no verificable".

### 9.4 Fixtures y tests

**Fixture principal: una corrida real del pipeline**, no una fabricada a mano.
`_make_run` (`tests/test_audit.py:12-87`) se elimina: construye una corrida
incoherente (llamadas sin `temperature` ni `response_sha256`, métricas sin
matriz, `counts {identified: 10, included: 2}`) que el auditor nuevo rechazaría
por `schemas` y `arithmetic`. En `tests/conftest.py`, una fixture de sesión
genera la corrida una vez con `ScriptedProvider` (de `tests/fakes.py`; vota
`exclude` ante "irrelevante", así hay exclusiones IA y un gold de dos clases) y
la copia con `copytree` a `tmp_path` en cada test. En la fase 1 los
`decision.yml` humanos se escriben antes de correr (funciona con el pipeline de
hoy, como en `test_pipeline_fake.py:151-157`); en la fase 2 la fixture usa
`correr_hasta` y `responder_gate` de `tests/hitl_helpers.py`.

`tests/audit_fixtures.py` contiene solo lo que el pipeline no puede producir:
`write_c3_reconstruction(tmp_path, provenance="pipeline")` (la reconstrucción
de C3 con la procedencia falsificada), `write_legacy_v07(tmp_path)` y helpers
de edición (`edit_json`, `edit_yaml`, `edit_ledger`).

**Tests existentes que cambian de expectativa:**

| Test | Cambio |
|---|---|
| `test_audit_corrida_completa_es_publicable` | Usa la fixture real; `manifest` pasa a WARN (fake). |
| `test_audit_sin_decisiones_humanas_advierte_hitl` | Ahora FAIL y no publicable; se renombra `…_falla_hitl`. |
| `test_audit_gate_final_auto_approve_no_es_humano_advierte`, `…_auto_proceed_advierte` | Ahora FAIL (D8). |
| `…no_duplica_fail_de_procedencia` y los dos `…no_duplica_fail_de_final_gate` | Pasan de "id ausente" a `status == "N/A"`. |
| Los seis tests de `gold` | Escriben un `ScreeningMetrics` válido; los de matriz `null` o ausente afirman además `schemas == FAIL`. |
| `test_cli_audit_escribe_informe` | Usa la fixture real. |
| `test_pipeline_fake.py::test_paused_run_final_gate_falla_en_auditoria` | Fase 2: bucle de reanudación; afirma "en pausa en `reporte`". |

**Tests nuevos.** Por familia (nombres completos en el plan):

- *Robustez:* manifiesto con raíz lista; JSON inválido por artefacto (parametrizado); UTF-16 o binario; línea de ledger corrupta → FAIL; error interno de un check → FAIL y el resto sigue; invariante `N/A ⇒ FAIL`.
- *`schemas`:* métricas sin matriz; llamada sin `response_sha256`; verificación sin `stage`; herramienta RoB distinta.
- *`ledger`:* acciones que el motor no emite; etapa desconocida; etapas desordenadas; autonomía distinta de la efectiva.
- *`timing`:* llamadas en 1,3 ms → solo WARN; fake exento; determinista no fake → FAIL; ledger anterior al inicio; llamada posterior al manifiesto; marca sin zona; pausa de días sin aviso; horas redondas → WARN.
- *`arithmetic`:* cada relación rota (parametrizado); κ/MCC manipulados; voto de un modelo no configurado; menos llamadas que decisiones; copia del manifiesto distinta; `models_used` incoherente; `wmcc_fn_weight` distinto.
- *`hitl`/`exclusions`:* auto-approve en cada uno de los 5 gates; `excluded_human` sin etiquetas (C3); exclusiones distintas del recálculo; actor desconocido → WARN; fase 2: `human_label` sin `label`, `from` distinto de la IA, `decision.yml` vs ledger, FT sin etiquetar, `unclear` sin resolver, no recuperado cribado por IA, corrida v0.7 sin etiquetas.
- *`request_hash` (F2):* solicitud editada; decisión de otra solicitud; etiqueta fuera de la solicitud; artefacto aprobado modificado.
- *Estado:* pausa en `screening_ft` (`final_gate` FAIL "en pausa en `screening_ft`", `hitl` PASS en T/A, posteriores en `N/A`); interrumpida.
- *`thresholds`:* recall bajo umbral con exclusiones IA sin revisar → FAIL; el mismo recall con todas las exclusiones IA etiquetadas → WARN (F2); **κ 0.0 bajo `kappa_min` → WARN, nunca PASS** (el caso exacto de A11); recall igual al umbral con gold suficiente → PASS; recall 1.0 con 5 positivos → WARN (gold sin potencia); recall bajo con gold pequeño → sigue FAIL; el detalle incluye el intervalo de Wilson; declarado sin gold; clave desconocida; sin umbrales.
- *`grounding`:* marca sin adjudicar → FAIL; todas adjudicadas por humano → WARN (F2); adjudicación de un actor no humano → FAIL; sin citas → WARN; bandera inconsistente; `exists_in_corpus` falso positivo del fichero (id fuera de los incluidos marcado como existente) → FAIL.
- *`search_*` (F2):* log ausente; base sin entrada; cadena distinta de la instantánea; `query_sha256` falso; tope de `max_results`; base caída; fallback a la pregunta; búsqueda inyectada; fecha tecleada distinta.
- *`protocol_snapshot` (F2):* hash alterado; instantánea distinta del manifiesto.
- *`deliverable`:* exige `checklist_s.md` y `checklist_abstracts.md`; exige 16b (F2); exige `meta_analisis.md` si hubo efectos.
- *Render:* escapa `|` y saltos sin cambiar el número de filas; el CLI muestra `N/A`.
- **C3:** `test_audit_c3_reconstruccion_no_es_publicable_por_varias_vias` (con la procedencia falsificada a `pipeline`: afirma `{schemas, ledger, timing, hitl, stage_artifacts, arithmetic, final_gate} ⊆ FAIL`) y `test_audit_c3_cada_sintoma_basta_solo[...]` (sobre la fixture coherente, un síntoma cada vez: acción desconocida, métricas sin matriz, falta `04_fulltext/`, `excluded_human: 3`, ledger fechado una semana antes, `identified_by_source` 40/40/40 frente a 28; cada uno basta para hacerla no publicable; "1,3 ms" solo da WARN y el test lo afirma).
- **Frontera del contrato** (`tests/test_pipeline_fake.py`, F2): `test_pipeline_fake_con_humano_audita_sin_fail` y `test_pipeline_auto_approve_no_es_publicable`.

## 10. Topología y orden de merge

Las PRs forman una cadena apilada `0 → A → B → C → D → E`, como en la Ola 0.
A, B y la fase 1 de E se desarrollan en paralelo desde PR-0; el integrador
rebasa B sobre A antes de empezar C, y E sobre D antes de su fase 2.

| PR | Rama | Se desarrolla desde | Base de la PR | Cierra | En paralelo con |
|---|---|---|---|---|---|
| 0 | `feat/ola1-contratos` | `main` | `main` | spec, planes, contratos | — |
| A | `feat/ola1-preflight` | 0 | 0 | M6 | B, E (fase 1) |
| B | `feat/ola1-flujo-prisma` | 0 | A (tras rebase) | M11, M23 | A, E (fase 1) |
| C | `feat/ola1-reanudacion` | B rebasada | B | A9, M12, `request_sha256` | E (fase 1) |
| D | `feat/ola1-hitl-por-registro` | C | C | C1, M5, M13 | E (fase 1) |
| E | `feat/ola1-auditor` | 0 (fase 1) → D (fase 2) | D | C3-auditor, A11, M5 auditor | — |

Solapes verificados y cómo se resuelven:

| Fichero | Pistas | Resolución |
|---|---|---|
| `cli.py` | A (`main`, `_cmd_validate`, arranque de `run`), C (`--resume`, excepciones), E (`_cmd_audit`) | A y E tocan funciones distintas; C se apila sobre A |
| `orchestration/pipeline.py` | B (bloque FT y conteos), C (refactor), D | Secuenciales: B → C → D |
| `orchestration/hitl.py` | C (hash, idempotencia), D (registros) | Secuenciales |
| `exports/checklist.py`, `exports/methods.py` | B, C, D | Secuenciales |
| `exports/prisma_flow.py` | 0 (campos), B (cajas) | Secuenciales |
| `tests/test_pipeline_fake.py` | B, C, D, E (F2) | E no lo toca en la fase 1 |

Cada pista corre en su worktree (`C:\revisia-wt\<pista>`). Cada tarea pasa por
un implementador (subagente nuevo, TDD), un revisor (subagente nuevo: primero
cumplimiento del spec, después calidad) y las correcciones. **Los
implementadores no tocan `CHANGELOG.md`, `README.md` ni este spec**: el
integrador los actualiza al cerrar cada PR, para evitar conflictos entre
pistas. El cierre de la ola (README sin la nota de limitación, `AGENTS.md`,
auditoría §11 "Ola 1 cerrada") va en la última PR que se mergea (E).

Merge: lo decide el arquitecto. Con PRs apiladas **nunca** se usa
`--delete-branch` mientras otra PR use esa rama como base (GitHub cierra la
dependiente en vez de re-apuntarla): merge sin borrar → `gh pr edit <n> --base
main` → borrar la rama → cerrar y reabrir la PR para disparar el CI.

## 11. Método de trabajo

TDD estricto: un test rojo por hallazgo antes de cada arreglo, y los tests
reproducen la evidencia de la auditoría, no una versión suavizada. Todos
offline, sin red y deterministas; ningún test invoca `claude`, WeasyPrint real
ni APIs.

Criterio de cierre de cada PR:
- `uv run pytest -p no:cacheprovider` en verde (línea base: 330 recogidos);
- la misma suite en 3.11 y 3.12 con un venv desechable (`requires-python >= 3.13` impide `uv run --python 3.11`; M24 es Ola 2), como en la Ola 0;
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run black --check .` y `uv lock --check` limpios.

Criterio de cierre de la ola, de punta a punta con el demo y el proveedor fake:
`revisia run` → pausa en `screening_ta` → `decision.yml` con el hash →
`revisia run --resume` → … → `revisia audit` **APTA**; la misma corrida con
`--auto-approve` → **NO publicable**; la reconstrucción C3 (con procedencia
falsificada) → **NO publicable** por al menos siete checks independientes.

## 12. Fuera de alcance (Ola 2 y posteriores)

- Ids estables entre corridas y `normalize_doi()` único (A4, A5): aquí solo se desambiguan colisiones dentro de una corrida.
- `seed`/`temperature` realmente aplicados, hash del prompt enviado, modelo en el callback de `agent`, `agent_driver` con `auto_approve=False` (A6-A8).
- Latencia en `RunMeta` (la heurística temporal trabaja sin ella).
- Grounding real (C2): aquí la verificación solo entra en el diario y el juez registra sus llamadas.
- Extracción campo a campo por el humano y overrides de RoB (D1); extracción sobre texto completo; truncado a 20 000 caracteres sin registrar (M14).
- Reintentos y backoff (M15): el 429 se resuelve reanudando. Presupuesto por corrida (M17); llamadas en paralelo.
- `rc` de `paused`; reanudación desde el envoltorio de Prefect; migrar corridas anteriores a la Ola 1; CSV o TUI para revisar miles de registros.
- Firma criptográfica del manifiesto o encadenado del ledger: el auditor encarece una reconstrucción, no la hace imposible.

## 13. Riesgos asumidos

1. **Gates que no convergen.** Cualquier no determinismo en un payload deja la corrida pausada para siempre. Mitigación: `test_payloads_estables_entre_reanudaciones_y_sin_rutas_absolutas` sobre los cinco gates; solo `documento.md` entra en el hash de `reporte`.
2. **Código que cambia entre pausa y reanudación.** Se verifican las plantillas de prompt; parsers y resto del código, no. `engine_version` y `resumes` quedan registrados.
3. **El demo cambia de comportamiento.** Sin texto completo en abierto, un registro ya no llega a extracción (D2). Los tests inyectan `fetch_fn`; CHANGELOG y README lo explican.
4. **Cambios incompatibles (0.8.0):**
   - `decision.yml` exige `request_sha256`;
   - desaparece `PrismaCounts.fulltext_abstract_only`;
   - `RunContext` sobre una carpeta existente da error;
   - `revisia validate` y `run` salen con `2` ante problemas de preflight que antes se descubrían a mitad de corrida;
   - los no recuperados ya no llegan a extracción (D2);
   - el auditor es más estricto: auto-approve, recall bajo umbral sin revisión y citas marcadas sin adjudicar pasan de WARN a FAIL;
   - las corridas anteriores no se reanudan ni son publicables (D13).

   El tipo `float | None` de las métricas y el resto de la API de la Ola 0 no cambian.
5. **Preflight más estricto.** Puede bloquear protocolos con bases fuera de las listas; se mitiga ampliando `MANUAL_ONLY` y con un mensaje que dice cómo declararla como manual.
6. **Falsos positivos de `timing`.** Tolerancia de 2 s; las heurísticas solo dan WARN. Si un día el pipeline lanza más de 50 llamadas concurrentes, hay que revisar el umbral de 5 ms.
7. **Adjudicación de citas marcadas con el verificador aún roto (C2).** El patrón de citas (`verificador.py:30`) toma `[2019]` o `[1]` como ids, que salen marcados en cualquier modo. D8 le da al humano una salida: adjudicarlos uno a uno como falsos positivos con razón, que el auditor deja en WARN. El riesgo pasa a ser el contrario, que el humano adjudique sin leer. Se mitiga con la razón obligatoria por cita, el actor en el ledger y el WARN visible en `audit.md`. En el otro sentido, el modo `embedder` por defecto casi nunca marca nada (C2), así que una síntesis sin marcas **no** prueba que esté fundamentada: lo resuelve la Ola 2.
8. **Usabilidad.** Las razones humanas libres multiplican las cajas "Reason n" del diagrama; la plantilla sugiere los criterios de `inclusion_exclusion.yml`. Un `review_request.yml` de miles de registros pesa.
9. **Inmutabilidad del protocolo.** Añadir `gold.yml` o `effects.yml` a mitad de corrida exige una corrida nueva. Es intencional (reproducible) y se documenta.
10. **El auditor no es una firma.** Quien replique toda la lógica puede fabricar una corrida coherente.

## 14. Desviaciones durante la implementación

Registro de lo que cambie respecto a §4-§9 y a los planes, y por qué. Vacío al
redactar.

| # | Dónde | Cambio | Origen |
|---|---|---|---|
| 1 | §4.5 `artifacts.py` | Además de los nombres de §4.5: `RunInterruption`, `DedupDuplicate` y `DedupRename` (tipan las listas que §4.3 describe como `{…}`), los alias `SearchEntryKind`, `SearchEntryStatus`, `QueryOrigin`, `ReasonSource` y `GateAction`, y `LLMCall.from_meta(meta, *, stage, record_id=None, role=None)` | Plan PR-0 |
| 2 | §4.5 `GateSummary` | Campos: `stage`, `action`, `actor`, `autonomy`, `request_sha256`, `decision_sha256`, `n_labels`, `n_flag_reviews`, `forced_human`, `timestamp_utc`. `n_labels` y `n_flag_reviews` se cuentan en el ledger (misma etapa y mismo `decision_sha256`), no se leen del `detail`, para que el auditor pueda contrastarlos | Plan PR-0 |
| 3 | §4.5 `ledger.py` | `GATE_DECISION_ACTIONS = {approve, reject, auto-proceed}` además de `LEDGER_ACTIONS`; ambas `frozenset`, y un test las ata a `GateAction` | Plan PR-0 + revisión |
| 4 | §4.5 `tests/fakes.py` | `ScriptedProvider` registra además `prompts` y admite `palabras` y `criterio_exclusion`; `fail_at` cuenta desde 1, solo falla esa llamada y rechaza valores `< 1`; `fetch_no_disponible` rechaza una cadena suelta (exige una colección de ids) | Plan PR-0 + revisión |
| 5 | §5 `PreflightError` | `PreflightError(report)` guarda el informe en `.report`; su mensaje lista los errores | Plan PR-A |
| 6 | §5 `preflight()` | Los problemas idénticos de varias etapas se unen en uno (`where` combinado: "falta GEMINI_API_KEY" sale una vez). `stages_in_use` omite las etapas sin proveedor; el error lo emite `preflight`. Puntos de inyección `_default_find_spec`/`_default_which` para los tests del CLI | Plan PR-A |
| 7 | §5 tests existentes | Además de `tests/test_cli_validate.py:35,44,72`, cambian `tests/test_cli_errores.py:50,77` (`run` del demo): el venv de desarrollo no instala `httpx` y el demo usa OpenAlex, así que necesitan `find_spec` falso | Código real |
| 8 | §5 `context="resume"` | Se salta también la comprobación de `httpx`, que va con "bases y búsqueda". Si al reanudar queda recuperación de texto completo pendiente y falta `httpx`, esos registros quedarán como no recuperados con motivo `sin_httpx`; PR-C decide si lo convierte en aviso | Literal del spec |
| 8a | §5 preflight de bases | La lectura de `search_strings/<key>.txt` está protegida (`OSError`, `UnicodeDecodeError`) y da un **error** accionable en vez de un traceback, para toda base declarada (el pipeline lee la cadena de cualquier base antes de mirar si tiene backend); `imported/` solo cuenta ficheros | Revisión Tarea 7 (Important) |
| 8b | §5 base desconocida | El consejo pide corregir la errata o importar por RIS/BibTeX y añadir la clave a `MANUAL_ONLY`; ya no sugiere quitarla de `databases` (la borraría del informe PRISMA-S) ni declararla con el nombre de otra base | Revisión Tarea 7 |
| 9 | §6 pipeline | PR-B ya escribe `04_fulltext/retrieval.json` (formato de §4.2, con `text_file: null` hasta la caché de PR-C) y `04_fulltext/excluded.json`; M11 pide guardar el motivo del fallo y la lista 16b ya existe | Plan PR-B |
| 10 | §6 pipeline | El payload del gate FT gana `n_buscados` y `n_no_recuperados`; `n_evaluados` pasa a ser los evaluados (antes, los buscados). PR-D lo sustituye por `ft_payload` | Plan PR-B |
| 11 | §4.3 validador de `PrismaCounts` | Para un manifiesto sin `fulltext_sought` también fija `excluded_ft_human = 0` y `excluded_ft_ai = excluded_ft` (en v0.7 ningún código ponía `human_label`): sin esto, el diagrama de una corrida antigua diría "por humano 0 · por IA 0" con exclusiones | Plan PR-B |
| 12 | §6 conteos | `excluded_ft_human`/`excluded_ft_ai` se cuentan por `reason_source` de la lista 16b. Hoy equivale a `0`/`excluded_ft`, y sigue siendo correcto cuando PR-D añada etiquetas humanas | Plan PR-B |
| 13 | §6 `exports/checklist.py` | El ítem 16 del checklist PRISMA 2020 cita `excluidos_texto_completo.md` (16b) | §10 lista `checklist.py` en B |
| 13a | §6 `compute_ft_excluded` | La razón IA ignora criterios vacíos o en blanco (`""`, `"  "`, salida plausible de un LLM) y se recorta; un test fija la precedencia humano > IA | Revisión Tarea 11 |
| 14 | §7 refactor | `run_pipeline` queda en preflight + instantánea + `try/except`, y la cadena de etapas en `_run_stages`; además de las funciones del spec hay `_load_gold` y `_meta_analysis`. `_Run.gate(stage, payload)` no recibe `records`/`force_human` hasta PR-D, que añade también `flags` (lo necesita M5). `_Run` gana `stage`, `finish()` e `interrupted()` | Plan PR-C |
| 15 | §7 `RunContext` | `LegacyRunError(ValueError)` para D13 al abrir sin `run.json` (el CLI la mapea a rc 2); `RunContext.open` da `FileNotFoundError` si la carpeta no existe; `write_text` también es atómico; `write_manifest(..., autonomy_effective=None, final_gate=None, extra=None)` con defaults para no romper a los llamadores existentes | Plan PR-C |
| 16 | §7 `journal.py` | `read_jsonl`/`append_jsonl` públicos (`RunContext` los usa para `llm_calls.jsonl`, con la misma tolerancia a la última línea truncada); `StageJournal.append(entry: JournalEntry)`; `TypeVar` + `# noqa: UP047` en vez de PEP 695 por la matriz 3.11/3.12 | Plan PR-C |
| 17 | §7 `snapshot.py` | `PROMPTS_DIR` y `SEARCH_STRINGS_DIR` a nivel de módulo; `ProtocolMismatchError(message, files)`; `ensure_snapshot` escribe `run.json` antes de copiar (§4.2: "lo primero que se escribe"; la huella se calcula sobre el original, idéntico byte a byte a la copia) | Plan PR-C |
| 18 | §7 preflight en `run_pipeline` | Con `search_fn` inyectado también se usa `context="resume"`: no hay bases que comprobar, y con `"run"` el demo (OpenAlex) daría error de `httpx` en el venv de desarrollo. El pipeline no imprime los avisos (los imprime el CLI). Fila 8: sin `httpx` al reanudar, lo pendiente de recuperar queda `sin_httpx`; no se convierte en aviso | Plan PR-C |
| 19 | §7 `search_stage.py` | `multi_database_search(protocol, *, strings_dir, imported_dir, question, max_results, mailto)`; `backend = "<módulo>.<función>"`; las entradas de `imported/` llevan `db_key="imported"` y `declared=true`; una base manual registra su cadena si hay fichero; la inyectada es `database = db_key = "search_fn"` con `query_origin = null`; `failures.json` incluye los ficheros importados que fallan. Sin `log.json` y sin la carpeta del protocolo (reanudar sin ella) da `ProtocolMismatchError`: `imported/` no está en la instantánea | Plan PR-C |
| 20 | §7 gates y ledger | `review_gate` añade él mismo las claves comunes (`schema_version`, `stage`, `autonomy`); el `detail` de `approve`/`reject` ya lleva `n_labels: 0` y `forced_human: false` en PR-C; volver a una decisión idéntica a una anterior ya reemplazada da `DecisionFileError` (la tupla de §4.3 es única); `GateResult` gana `request_sha256` y `actor`; `render_decision_template(*, stage, autonomy, request_sha256)` en PR-C (PR-D añade `records` y `flags`); payload de `reporte` en PR-C = `{included, hallucination_flagged, documento_sha256}` | Plan PR-C |
| 21 | §7 `inputs` de los diarios | T/A: `miembros` como listas `[modelo, temperature, seed]`; recuperación: `extra` con `fulltext_url`, `oa_url`, `pmcid`, `pmid`; extracción y RoB: `proveedor` como lista, RoB con `extraction_sha256` y `tool`; síntesis: `incluidos`, `extracciones_sha256`, `proveedor`; verificación: `narrativa_sha256`, `fuentes_sha256`, `modo`. La caché de texto se escribe y se lee en bytes UTF-8 y se verifica contra `text_sha256` (`JournalError` si no coincide) | Plan PR-C |
| 22 | §7 CLI | `_run_guarded` mapea también `LegacyRunError` y `FileNotFoundError` (carpeta inexistente) a rc 2; aviso al reanudar sin `--mailto` si la corrida empezó con él (`mailto_set` entra en la huella de cada recuperación); un `KeyboardInterrupt` también queda en `run.json.interruptions` | Plan PR-C |
| 23 | §7 tests existentes | Cambian ya en PR-C (no en PR-D ni PR-E): `tests/test_hitl.py` (decisiones con `request_sha256`, `detail ==` → subconjunto) y `tests/test_pipeline_fake.py::test_rejected_final_gate_is_not_completed` y `::test_paused_run_final_gate_falla_en_auditoria` (pasan a `correr_hasta`), porque con el hash obligatorio ninguna `decision.yml` se puede escribir antes de correr | Código real |
| 24 | §7 helpers y dobles de test | `hitl_helpers` gana `leer_solicitud(run_dir, stage)`; `etiquetar` devuelve los kwargs de `responder_gate`; `correr_hasta` reabre la carpeta con `RunContext.open` en cada vuelta. `ScriptedProvider(sintesis=...)` (aditivo) para tener citas que verificar. `engine_search_date(log)` es pública; `render_prisma_abstracts_checklist` y `render_methods` también reciben `search_log` | Plan PR-C |
| 24a | §7 recuperación | Los motivos transitorios (`error_http`, `sin_httpx`) no se escriben en el diario y se reintentan al reanudar (A9: un fallo transitorio se resuelve reanudando). Consecuencias: reanudar una corrida `completed` con un transitorio persistido la devuelve a `paused` si el texto aparece (cambia el `request_sha256` del gate FT); `error_http` mezcla 4xx deterministas con caídas de red, y ambos se reintentan en cada reanudación | Controlador (revisión de la Tarea 12) |
| 24b | §7 `inputs` de extracción y RoB | Además de registro, texto, formulario y proveedor llevan `title` y `abstract`, que es lo que `extract_record` manda a la IA: con solo `text_sha256`, un registro con otro resumen devolvía la extracción vieja | Controlador (revisión de la Tarea 14) |
| 24c | §4 relación 12 | Las llamadas esperadas de `verificacion` son 0 o el número de comprobaciones con `exists_in_corpus` y fuente: el juez solo se llama para citas que existen en el corpus | Controlador (revisión de la Tarea 16) |
| 24d | §7 checklist PRISMA-S y métodos | Al renderizar, la cadena se colapsa a una línea (`log.json` conserva la exacta): una cadena multilínea rompía el Markdown del Anexo E. Una base fallida lleva `(falló: <error>)`; la fecha del motor solo toma búsquedas que ejecutó el motor (no importaciones, que salen como "importado el <fecha>"); `metodologia.md` cita `00_protocol/search_strings/` solo si alguna base usó su fichero | Controlador (revisión de la Tarea 18) |
| 24e | §7 robustez al reanudar | Una salida del diario que ya no valida o un texto en caché ausente o ilegible dan `JournalError` (rc 2) en vez de un bucle de rc 3; un `protocol.yml` que no es un mapa da rc 2 en `validate`, `run` y `--resume`; los lectores JSONL del ledger y del cerebro parten por `\n` (U+2028/U+0085 dentro de una cadena partían la entrada) | Controlador (pulido de la pista C) |
| 25 | §8 `gates.py` | Además de las siete funciones del spec, `report_policy(verification) -> FlagPolicy \| None`. Todas con argumentos por nombre; `ta_payload(..., metrics=None, thresholds=None)` para `quality` (D7); el payload de FT ordena `records` por id, como el de T/A | Plan PR-D |
| 26 | §8 `hitl.py` | `RecordHint(record_id, title, proposal, note="")` y `FlaggedClaim(index, cited_id, claim, note=None)`; `RecordPolicy` con defaults; las claves de `records`/`flags` se convierten a texto; la validación de contenido (ids, razones, completitud) solo se hace al aprobar (con `approved: false` nada se aplica) y la estructural (`records`/`flags` en un gate que no los admite) siempre; la decisión sintética de `--auto-approve` no se valida (D9: no exige la completitud A0); `force_human` con `--auto-approve` pausa con su propio mensaje; sin `decision.yml`, la reconstrucción desde el ledger devuelve también etiquetas y adjudicaciones | Plan PR-D |
| 27 | §8 ledger y payloads | `claim` de las citas marcadas recortado a 300 caracteres también en la `FlagPolicy` y en el `detail` de `flag_review`; un `label` lleva `from: null` en un no recuperado | Plan PR-D |
| 28 | §8 M13 | `render_traice_checklist(run_metas, autonomy_effective, *, gates=None, forced_human=False, metrics, exclusions, search_window)`: el segundo posicional pasa a ser la autonomía efectiva; `describe_gate(stage, summary)` y `human_validation_summary(gates)` públicas en `exports/checklist.py`, las usa también `methods.py`. Autonomía efectiva calculada por `pipeline._autonomy_effective` | Plan PR-D |
| 29 | §8 helpers de test | `responder_gate(..., flags=None)` (aditivo) y `aceptar_lo_obligatorio(stage, solicitud)`: `correr_hasta` responde con ella cuando `etiquetar` falta o devuelve `None` (con FT en A0 aprobar exige etiquetar cada recuperado). El test unitario `test_ft_a0_aprobar_sin_etiquetar_todo_es_error` va en `tests/test_hitl_registros.py` y su versión de pipeline se llama `test_ft_a0_pipeline_exige_etiquetar_los_recuperados` | Plan PR-D |
| 30 | §8 tests nuevos | Además de los del spec: `test_rescate_sin_razon_es_error`, `test_etiquetas_en_el_ledger_antes_del_approve`, `test_rechazo_no_lleva_etiquetas`, `test_etiquetas_se_reconstruyen_desde_el_ledger`, `test_auto_approve_pausa_con_registros_por_resolver`, `test_auto_approve_no_exige_la_completitud_a0`, `test_force_human_ignora_auto_approve_y_a2`, `test_review_request_ta_sin_gold_no_informa_calidad`, `test_reporte_con_citas_adjudicadas_se_completa`, `test_traice_reporte_forzado_figura_en_a1` | Plan PR-D |
| 31 | README | PR-D deja la nota "Limitación actual" reducida al auditor (`--auto-approve` aún solo da WARN); la quita PR-E, como dice §10 | Plan PR-D |
| 31a | §8 `decision_sha256` | El hash de la decisión incluye `records: {}` y `flags: {}` aunque vengan vacíos: la misma decisión de PR-C da otro `decision_sha256` (solo afecta a una corrida a medias de la rama sin publicar); la cola del mensaje de decisión incompleta se reescribió conservando el prefijo literal | Controlador (revisión de la Tarea 20) |
| 31b | §8 plantilla (D4) | Claves de `records`/`flags` con `json.dumps(ensure_ascii=False)` más escapes YAML de lo no imprimible; una clave de más de 1 000 caracteres usa la forma explícita `? "<id>"`; el comentario de cada registro pone primero propuesta, votos y marcas, y acota cada texto libre por separado (`_MAX_NOTA` 500, línea ≤ 800); los ids de modelo se acortan a 40 caracteres | Controlador (revisiones de las Tareas 21-23) |
| 31c | §8 `force_human` | Con el gate forzado, un `decision.yml` cuyo actor no empieza por `human:` (o es `human:` sin nombre) da `DecisionFileError`, y del ledger solo se reutiliza una decisión humana. La regla A2/A3 → A1 vive en un único helper, `hitl.effective_autonomy`, que usan el gate y el manifiesto; `forced` sale de `recompute_flag()`, que se aplica al escribir `verification.json` | Controlador (revisiones de las Tareas 20, 21, 26 y 27) |
| 31d | §8 T/A `quality` y §5 config | Un umbral no finito no entra en la solicitud (`None`); además `ReviewProtocol` valida que los umbrales sean finitos, `recall_target` en [0, 1], `kappa_min` en [-1, 1] y `wmcc_fn_weight` > 0 (rc 2 en `validate`/`run`) | Controlador (revisiones de la Tarea 23 y del pulido) |
| 31e | §8 FT y contratos | `TRANSIENT_FULLTEXT_REASONS: frozenset[FulltextReason]` pasa a `schemas/artifacts.py` (no estaba en §4.5): `gates.py` no puede importar el pipeline. Un no recuperado por motivo transitorio sigue siendo rescatable, con una nota que avisa de que se reintenta; si al reanudar aparece el texto, la solicitud cambia y el rescate anterior no se aplica. Un transitorio que cambia de motivo (`error_http` → `sin_httpx`) también cambia el hash de FT y, en A0, obliga a volver a etiquetar | Controlador (revisión de la Tarea 24) |
| 31f | §8 extracción y RoB | `gates.dump_artifact` construye el dict que se escribe en `extractions.json`/`assessments.json` y el que se hashea en `artifact_sha256` (`model_dump(mode="json")` en ambos) | Controlador (revisión de la Tarea 25) |
| 31g | §8 M13 | El entregable se escribe antes del gate final, así que `reporte` figura "pendiente de la decisión final" (o "auto-proceed previsto" si es A2/A3 sin forzar) y no arrastra un rechazo anterior de D14. `metodologia.md` declara que la IA extrae solo de título y abstract en todos los estudios (M14 queda para la Ola 2), que el cribado a texto completo es de un solo modelo, que la `source_quote` se solicita pero no se verifica, y que un informe rescatado llegó a RoB y verificación sin texto completo | Controlador (revisiones de las Tareas 23, 24 y 27) |
