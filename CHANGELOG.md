# Changelog

Todos los cambios notables de `RevisIA` (antes `prisma-loop`) se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [0.6.0] · 2026-07-12

### Added
- **Backend NCBI E-utilities** (`revisia/agents/ncbi.py`): búsqueda PubMed
  (`esearch`+`efetch`) y PMC opt-in (`esummary`), con cortesía NCBI y
  `NCBI_API_KEY` opcional. PubMed queda como línea de búsqueda canónica y
  citable para PRISMA-S.
- **Texto completo OA estructurado vía BioC-PMC**: `agents/fulltext.py` prioriza
  el texto BioC (JSON, sin parsear PDF) cuando hay PMCID (directo o resuelto por
  ID Converter), mejorando el cribado full-text, la evaluación de riesgo de sesgo
  y el grounding de citas (la extracción sigue basada en abstract hasta H3).

### Changed (breaking menor)
- Los alias `pubmed` y `medline` ahora apuntan a **NCBI** (antes a Europe PMC).
  Europe PMC conserva sus alias propios: `europepmc` / `europe_pmc` / `epmc`.
  Protocolos que usaban `pubmed` esperando Europe PMC deben cambiarlo a `europepmc`.

### Fixed
- **Dedup conserva los identificadores de los duplicados**: el registro
  conservado hereda las claves de `extra` (p. ej. el PMCID de PubMed) que aporten
  los duplicados, sin pisar las suyas; antes se perdían según el orden de bases.
- **Cadenas de búsqueda de bases multi-palabra**: `db_key` normaliza el nombre de
  base igual para el dispatch y para el fichero `search_strings/<base>.txt`, así
  «Europe PMC» y «Semantic Scholar» ya encuentran su cadena curada (antes caían a
  la pregunta cruda).

## [0.5.0] · 2026-07-06

### Added

- **`revisia export <run_dir> [--format html|pdf] [--out <ruta>]`** —
  exportador nativo del entregable a **documento único**:
  - **HTML autocontenido** (default · cero dependencias del sistema): portada
    desde el `manifest.yml`, artículo, flujo PRISMA, metaanálisis con figuras,
    metodología, checklists, tabla de extracción, riesgo de sesgo y BibTeX en
    un solo `.html` con CSS académico inline. **Figuras embebidas como
    data-URI** y **bloques Mermaid sustituidos por la tabla estática oficial**
    (`render_flow_markdown`): sin JavaScript ni recursos externos, se abre
    igual movido a cualquier carpeta o máquina.
  - **PDF con WeasyPrint** (extra opcional `pdf`) — multiplataforma; sin
    Word/COM, sin LaTeX, sin pandoc, sin Chromium. Sin el extra, el error es
    accionable (cómo instalarlo o imprimir desde el navegador). Jubila el
    flujo externo Windows-only Markdown→Word COM, que rompía la promesa
    multiplataforma.
- **Proveedores `zai` (familia GLM vía Z.ai) y `openrouter`** (gateways
  OpenAI-compatibles; API key obligatoria con error accionable): paneles
  multi-modelo sin tocar código del motor. Diseño del **benchmark de
  sensibilidad del cribado** en `docs/benchmark-cribado.md` y credenciales
  nuevas en `.env.example` (`ZAI_API_KEY`, `OPENROUTER_API_KEY`).

### Changed

- Nueva dependencia del núcleo: `markdown` (pura-Python, sin dependencias
  transitivas) para la conversión MD→HTML del exportador; el HTML
  autocontenido funciona sin instalar ningún extra.

## [0.4.0] · 2026-07-05

### Changed

- **Rebrand: `prisma-loop` → `RevisIA`** (paquete `revisia`, CLI `revisia`,
  repo `github.com/jhonmosquerav/revisia`). Verificado sin colisiones en
  software/GitHub/PyPI. El nombre no incorpora "PRISMA" para no sugerir aval
  del PRISMA Group: la relación es de cumplimiento, no de marca. GitHub
  redirige las URLs del nombre anterior. Las entradas históricas de este
  changelog conservan el nombre antiguo.
- **Repositorio público** (antes privado durante la incubación).

### Added

- **`interop/prisma2020_flow.csv` en formato NATIVO del paquete R
  `PRISMA2020`** (ESHackathon/Haddaway, MIT): la plantilla oficial del paquete
  (vendorizada en `revisia/exports/data/`) se rellena con los conteos reales —
  desglose por base, razones de exclusión (`"Razón, n; Razón, n"`) y
  meta-análisis (box17). El archivo se importa tal cual en la Shiny app oficial
  o con `PRISMA2020::PRISMA_data(read.csv(...))`.

## [0.3.0] · 2026-07-05

Revisión exhaustiva del ecosistema oficial PRISMA (sitio, plantillas,
herramientas) volcada al motor.

### Added

- **Flow diagram con la estructura de las plantillas oficiales** — `PrismaCounts`
  ampliado y render fiel a la plantilla v1 (CC BY 4.0): desglose de identificados
  **por base** (nota *), cajas de eliminados pre-cribado (duplicados /
  automatización / otros), exclusiones T/A **separadas humano vs IA** (nota **
  oficial = trAIce R1), informes sin texto completo recuperable (declarado), y
  **razones de exclusión** en elegibilidad (cajas "Reason 1..n") agregadas de los
  criterios violados reales del cribado.
- **Flow diagram de revisiones actualizadas (plantilla v3)** —
  `render_flow_updated`: con `--brain` y memoria previa, la corrida emite
  `prisma_flow_updated.md` con estudios de la versión anterior, nuevos incluidos,
  retirados y total consolidado (**living review** de primera clase).
- **Checklist PRISMA-S** (16 ítems; Rethlefsen et al. 2021, CC BY) —
  `deliverable/checklist_s.md` pre-rellenado: bases, cadenas versionadas,
  ventana/límites, fechas de ejecución, totales por base y método de
  deduplicación.
- **`prisma-loop new <slug>`** — scaffold de una revisión completa desde
  `_TEMPLATE` (protocol.yml renombrado + PRISMA-P + gold + cadenas) con los
  siguientes pasos impresos.
- **`prisma-loop check <manuscrito>`** — pre-chequeo de adherencia de un
  manuscrito a los 27 ítems PRISMA 2020 con cualquier proveedor
  (`--provider/--model`): estado ✅/🟡/❌ por ítem con evidencia textual, informe
  `<manuscrito>.prisma-check.md`. En la línea de PRISMA-Check (la herramienta
  oficial anunciada "en desarrollo"), con `RunMeta` para declararlo bajo trAIce.
- `docs/arquitectura.md` — esquema de funcionamiento completo (tres planos:
  pipeline, defensa en profundidad, memoria).

## [0.2.0] · 2026-07-05

Primera versión como **repositorio independiente** (hasta ahora el desarrollo
vivía en el mono-repo privado del autor; el historial anterior se resume en
[0.1.0]).

### Added

- **Auditor post-corrida** — nuevo módulo `prisma_loop/audit.py` y comando
  `prisma-loop audit <run_dir>`: verifica con evidencia en disco los ítems
  automatizables de PRISMA 2020, PRISMA-S y PRISMA-trAIce (manifiesto y modelos,
  prompts hash-eados, supervisión humana en etapas de juicio, entregables
  completos, exclusiones humano/IA separadas, gold/κ, grounding, ventana de
  búsqueda, registro). Emite `audit.md` con PASS/WARN/FAIL y veredicto de
  publicabilidad; exit code 1 si hay FAIL.
- **Memoria con recall y living review** — `ResearchBrain.recall(slug)` y
  `summary()`: la memoria ahora se **lee**, no solo se escribe. Si un slug ya
  tiene corridas, la nueva se registra como actualización con delta de
  incluidos (`included_new`/`included_dropped`) en evento y episodio. Nuevo
  subcomando `prisma-loop brain <dir> [slug]`; aviso de memoria previa al
  arrancar `run --brain`; frontmatter YAML en las páginas wiki (patrón
  [cerebro](https://github.com/jhonmosquerav/cerebro), declarado en `NOTICE` y
  `docs/memoria-cerebro.md`). Regla anti-sesgo documentada: la memoria nunca
  alimenta el juicio de screening/extracción/RoB.
- **Checklist PRISMA 2020 de resúmenes** (12 ítems) —
  `render_prisma_abstracts_checklist()` emite `deliverable/checklist_abstracts.md`
  pre-rellenando fuentes/ventana, conteo de incluidos y registro.
- **Exports de interoperabilidad OSS** — nuevo `prisma_loop/exports/interop.py`
  y carpeta `deliverable/interop/`: `robvis.csv` (figuras de riesgo de sesgo),
  `effects_metafor.csv` (replicar el meta-análisis en R con `metafor::rma`),
  `prisma2020_flow.csv` (conteos para la plantilla oficial del flow diagram).
  Ecosistema declarado en `docs/integraciones.md` (integradas / interoperables /
  complementarias, con licencias).
- **Plantilla de preregistro PRISMA-P** —
  `protocols/_TEMPLATE/protocolo-prisma-p.md` con los 17 ítems (PRISMA-P 2015)
  mapeados a los archivos ejecutables del protocolo, incluida la declaración
  anticipada de uso de IA.
- **`AGENTS.md`** — el equipo declarado: un agente mono-tarea por etapa, tipos
  (determinista/LLM/humano), autonomías A0–A3 por defecto y las cinco capas de
  auditoría del sistema.
- **Base de conocimiento metodológica** (`docs/metodologia/`) — fuentes
  primarias extraídas a markdown con licencias y atribución: declaración PRISMA
  2020 (BMJ n71 + traducción oficial, parafraseada por CC BY-NC-ND), checklists
  y las 4 plantillas del flow diagram del sitio oficial (CC BY 4.0), catálogo de
  20 extensiones publicadas + 11 en desarrollo, y la extensión **PRISMA-trAIce**
  (17 ítems, extracción doble-independiente convergente) que fundamenta el
  `checklist_traice.md` del sistema.

### Changed

- `README.md`: quickstart con URL real del repo, secciones nuevas (equipo de
  agentes, auditoría, KB metodológica), salida ampliada.
- `RELEASING.md` reescrito: este repositorio es la fuente canónica (ya no un
  espejo); flujo de release + DOI Zenodo.
- `.env.example`: eliminadas variables muertas de embeddings; `.gitignore`
  ignora `cerebro/` (la memoria del investigador es personal, no del repo).

## [0.1.0] · 2026-07-05 (histórico consolidado)

### Added

- **Backend Europe PMC** (`prisma_loop/agents/search_backends.py`) — base abierta sin
  API key que espeja **MEDLINE/PubMed + PubMed Central + preprints**. Registrada con
  alias `europepmc`/`pubmed`/`medline`. Sube la cobertura por defecto a **4 bases
  libres** (OpenAlex + Crossref + Semantic Scholar + Europe PMC) sin tocar la
  suscripción de ninguna universidad. Scopus/WoS siguen por import RIS/BibTeX.
- **Plantilla `_TEMPLATE` endurecida** — defaults de buenas prácticas para que toda
  RS nazca robusta: 4 bases, `search_window` (PRISMA-S), campo `grounding`
  documentado, cadenas de búsqueda de ejemplo EN/ES/PT y un `gold.yml` plantilla.
- **Guardrails en `validate`** — advertencias accionables cuando una corrida
  arrancaría débil: <3 bases, `screening_ta` sin ensemble, sin `gold.yml`, o
  `grounding=embedder` (recordando que no cruza idiomas). Default de `--max` subido
  de 25 a 50 por base.
- **Comando `prisma-loop gold-template <run_dir>`** — genera un `gold.yml` con los
  ids cribados (comentados) para etiquetado humano; al rellenarlo se activan
  kappa/recall/lost-evidence. Acerca el doble cribado/gold a un paso.
- **Grounding por agente (sin vectores)** — modo `grounding: agent` en `protocol.yml`:
  el verificador anti-alucinación le pide a un proveedor LLM que **juzgue** si la
  fuente respalda cada afirmación citada (con cita textual de soporte), en vez de
  medir similitud por embeddings. Cruza idiomas (síntesis en español vs. fuentes en
  inglés) y es de **costo cero** con `provider: agent` (sin API key ni descarga de
  modelos). Modos disponibles: `embedder` (default, coseno portátil), `agent`,
  `existence`. Nuevo módulo `prisma_loop/rag/grounding.py`.
- **Cerebro de investigador (memoria persistente en markdown + JSONL)** — nuevo
  `prisma_loop.memory.ResearchBrain` y bandera `--brain <carpeta>` en `run`:
  sedimenta cada revisión en archivos portátiles (`genome/events.jsonl`,
  `wiki/semantic/`, `wiki/episodic/`, `raw/`, `index.md`), inspirado en el patrón
  `cerebro`. Sin vectores ni servidores; el conocimiento se acumula entre corridas
  y cualquier agente lo recupera leyendo archivos. `record_from_run()` sedimenta
  también corridas pasadas desde sus artefactos.
- **Embedder local `FastEmbedEmbedder` (opt-in, apagado)** — enganche para
  embeddings semánticos locales vía `fastembed` (ONNX/CPU, multilingüe, offline tras
  descarga única, sin API). No se usa por defecto; habilita el futuro índice
  vectorial local del cerebro sin servicios de pago.
- **Proveedor `agent`** — razonamiento delegado al agente que conduce prisma-loop
  **en proceso** (p. ej. una sesión de Claude Code). El agente *es* el modelo vía
  un callback inyectado (`set_agent_callback`/`use_agent_callback`); sin API key y
  sin `claude -p` headless. Pensado para cuando la auth Max no es delegable a un
  subproceso (token gestionado en memoria por el host). Entrypoint de conveniencia
  `prisma_loop.agent_driver.run_review_with_agent`.
- **Auth Max headless en `claude_code`** — el proveedor pasa el entorno explícito
  al subproceso, propagando `CLAUDE_CODE_OAUTH_TOKEN` (token de larga duración de
  `claude setup-token`) para operar con la suscripción Max/Pro sin API key.
  Flag `PRISMA_LOOP_CLAUDE_CODE_CLEAN_ENV` (o `clean_env=True`) para limpiar
  overrides de endpoint heredados (`ANTHROPIC_BASE_URL`/`USE_STAGING_OAUTH`) que,
  con un token propio, podrían provocar un 401. Documentado en `.env.example` y
  README.

### Fixed

- **`claude_code` en Windows**: el CLI `claude` es un shim `.cmd` que
  `CreateProcess` no resuelve por nombre pelado (`FileNotFoundError`); ahora se
  resuelve con `shutil.which` (ruta con extensión), válido también en POSIX.
- **`claude_code` error 401 accionable**: un fallo de autenticación headless ya
  no se reporta con el mensaje genérico de código de salida; se explica que la
  sesión Max no es delegable a un subproceso y se proponen remedios
  (`claude setup-token`, otro proveedor, o el proveedor `agent`).

### Added (continuación)

- **Driver Claude Code (H5)** — nuevo proveedor `claude_code` de primera clase
  (opción destacada; el default de la plantilla sigue siendo Gemini, arrancable
  por cualquiera). Razona con Claude Code en modo headless
  (`claude -p --output-format json`, prompt por stdin, sin herramientas),
  consumiendo la suscripción Max sin API key. `structured` se resuelve inyectando
  el JSON Schema y validando con Pydantic con reintentos (el CLI no fuerza
  *tool-use*). Sin dependencias nuevas (usa `subprocess`); reproducibilidad a
  nivel decisión (`deterministic=False`).
- **Proveedor Anthropic** (API directa): `complete` vía Messages API y
  `structured` vía *tool use* forzado. Completa la promesa provider-agnostic
  (Gemini / OpenAI / Anthropic / local / `fake`).
- **Bibliografía BibTeX** (`referencias.bib`) de los estudios incluidos como
  entregable.
- **Tabla de características de los estudios incluidos** (`tabla_extraccion.md`)
  como entregable, con marca de los campos `needs_review`.
- **Búsqueda multi-base**: backends Crossref y Semantic Scholar (sin API key)
  además de OpenAlex, con despacho por nombre de base; importación manual
  RIS/BibTeX (`protocols/<slug>/imported/`) para Scopus/WoS/EMBASE.
- **Meta-análisis cuantitativo** (§8.1): efectos fijos (inverse-variance) y
  aleatorios (DerSimonian-Laird), heterogeneidad Q/I²/τ², test de Egger y forest
  plot Markdown; gráficos PNG forest/funnel y p-valores exactos con el extra
  `meta` (matplotlib + scipy). Entrada vía `effects.yml` (logOR/MD/SMD o yi/vi).
- **`metodologia.md`**: generador determinista de la sección de métodos PRISMA +
  PRISMA-trAIce desde el manifiesto.
- **Doble extracción** (≥20%, §6): segundo extractor independiente + acuerdo de
  valor y Cohen's kappa de presencia (`extraction_agreement`).
- **Exclusiones humano vs IA** y **ventana temporal de búsqueda**: desglose
  automático en el checklist PRISMA-trAIce y en `metodologia.md`.

## [0.1.0] — 2026-06-26

Primera versión pública. Sistema multiagéntico provider-agnostic para generar
borradores de revisiones sistemáticas bajo PRISMA 2020 + PRISMA-S + PRISMA-trAIce.

### Added

- **Pipeline PRISMA end-to-end** (H0–H1): búsqueda (OpenAlex) → deduplicación →
  screening título/abstract → full-text → extracción → riesgo de sesgo → síntesis
  narrativa → verificador, con **checkpoint humano (HITL)** en cada etapa.
- **Capa LLM provider-agnostic** (H2): proveedores Gemini, OpenAI, local
  (endpoint OpenAI-compatible: Ollama/vLLM/LM Studio) y `fake` determinista para
  correr y testear offline sin credenciales.
- **Screening defendible** (H2): ensemble multi-modelo con voto sesgado a recall
  y métricas correctas (Recall/Lost-Evidence, MCC, WMCC, Cohen's kappa — nunca
  "accuracy").
- **Rigor PRISMA completo** (H3): cribado a texto completo (full-text OA vía
  Unpaywall), riesgo de sesgo configurable (RoB2/ROBINS-I/GRADE…), gates HITL en
  todas las etapas y verificador anti-alucinación con grounding semántico.
- **Reproducibilidad**: `manifest.yml` con modelo, seed, temperatura y *hash* del
  prompt por llamada; ledger append-only de decisiones humanas con timestamp;
  checklists PRISMA 2020 (27 ítems) y PRISMA-trAIce.
- **Apertura** (H4): licencia Apache-2.0, `CITATION.cff`, `.zenodo.json`,
  archivos de comunidad (CONTRIBUTING / CODE_OF_CONDUCT / SECURITY), CI y
  plantillas de GitHub.

### Notes

- v1 cubre **revisión sistemática narrativa**. El meta-análisis cuantitativo
  (PyMARE / R `metafor`) está reservado para v1.1.
- El driver de referencia de Claude Code (subagentes `.md`) llega en una versión
  posterior; el núcleo no lo requiere.

[Unreleased]: https://github.com/jhonmosquerav/prisma-loop/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jhonmosquerav/prisma-loop/releases/tag/v0.1.0
