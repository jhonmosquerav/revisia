# Integraciones con herramientas probadas (declaradas)

`revisia` integra y declara el ecosistema existente en vez de reinventarlo.
Tres niveles: **integrado** (el motor lo usa nativamente), **interoperable**
(el motor emite/lee su formato) y **complementario** (recomendado para un paso
concreto, fuera del motor).

> **Hoja de ruta:** las fuentes abiertas candidatas a futuros backends —arXiv,
> CORE, RePEc y más, priorizadas por área (economía, negocios, tecnología,
> LATAM)— están en [`fuentes-candidatas.md`](fuentes-candidatas.md).
> **Triage verificado (2026-09):** qué tiene API y qué no, fuente por fuente
> (40 bases de una guía bibliotecaria): [`fuentes-triage.md`](fuentes-triage.md).

## Integradas (nativas en el motor)

| Herramienta / servicio | Etapa | Licencia / acceso | Cómo se usa |
|---|---|---|---|
| [OpenAlex](https://openalex.org) | Búsqueda | API abierta (CC0); funciona sin key | Backend nativo (`agents/busqueda.py`), polite pool con `--mailto`; `OPENALEX_API_KEY` opcional (límites mayores, esquema de créditos 2026) |
| [Crossref](https://www.crossref.org) | Búsqueda | API abierta | Backend nativo |
| [Semantic Scholar](https://www.semanticscholar.org) | Búsqueda | API abierta (rate-limited) | Backend nativo |
| [Europe PMC](https://europepmc.org) | Búsqueda (espeja MEDLINE/PubMed) | API abierta | Backend nativo |
| [PubMed / PMC (NCBI E-utilities)](https://www.ncbi.nlm.nih.gov/books/NBK25501/) | Búsqueda | API abierta (`NCBI_API_KEY` opcional: 3→10 req/s) | Backend nativo (`agents/ncbi.py` + `search_backends.py`); alias `pubmed`/`medline` → NCBI, `pmc` opt-in |
| [BioC-PMC](https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/) | Texto completo OA | API abierta | Texto completo estructurado (JSON) del subconjunto OA por PMCID en `agents/fulltext.py`, preferente al raspado de PDF |
| [ERIC](https://eric.ed.gov) | Búsqueda (educación) | API abierta (sin key) | Backend nativo (`agents/open_backends.py`); alias `eric`; cadena Lucene (`publicationdateyear:[2020 TO 2024]`) |
| [DOAJ](https://doaj.org) | Búsqueda (revistas OA) | API abierta (metadatos CC0; 2 req/s) | Backend nativo; alias `doaj`; cadena Elasticsearch (`bibjson.year:2024`) |
| [UNESDOC](https://unesdoc.unesco.org) vía [UNESCO DataHub](https://data.unesco.org) | Búsqueda (literatura gris institucional) | API abierta (Opendatasoft) | Backend nativo; alias `unesdoc`/`unesco`; *snapshot* del catálogo, no el índice vivo |
| [BVS / LILACS](https://bvsalud.org) | Búsqueda (salud LATAM, es/pt, DeCS) | API abierta (iAHx, sin key; no documentada oficialmente) | Backend nativo; alias `bvs`/`lilacs` (portal regional) y `gim` (Global Index Medicus); año en la cadena (`year_cluster:[2020 TO 2024]`) |
| [AGROSAVIA](https://repository.agrosavia.co) · [CLACSO](https://biblioteca-repositorio.clacso.edu.ar) · [Banco Mundial OKR](https://openknowledge.worldbank.org) | Búsqueda (repositorios DSpace 7+) | API abierta (REST HAL) | Adaptador genérico `agents/dspace.py` (otro repositorio = una línea); alias `agrosavia`, `clacso`, `worldbank`/`okr`; año en la cadena (`dc.date.issued:[2020 TO 2024]`) |
| [DOAB](https://directory.doabooks.org) | Búsqueda (libros OA) | API abierta (DSpace 6 REST) | Backend nativo; alias `doab`; primer backend de libros (`extra.type = "book"`) |
| [Unpaywall](https://unpaywall.org) | Texto completo OA | API abierta | Resolución de open access en `agents/fulltext.py` |
| Import **RIS/BibTeX** | Búsqueda (Scopus/WoS/Zotero/EndNote) | Formatos estándar | `ingest/manual_import.py` — las bases de pago se exportan desde tu institución y se fusionan en la deduplicación |

## Interoperables (el motor emite su formato)

Cada corrida escribe `deliverable/interop/`:

| Herramienta | Archivo emitido | Para qué |
|---|---|---|
| [robvis](https://github.com/mcguinlu/robvis) (R/Shiny, MIT) | `robvis.csv` | Figuras semáforo/barras de riesgo de sesgo con calidad de publicación |
| [metafor](https://www.metafor-project.org) (R, GPL) | `effects_metafor.csv` | Replicar/extender el meta-análisis (`rma(yi, vi, data=dat)`): más estimadores, meta-regresión, sensibilidad |
| [PRISMA2020 flow diagram](https://estech.shinyapps.io/prisma_flowdiagram/) (paquete R + Shiny, oficial del sitio PRISMA) | `prisma2020_flow.csv` | Conteos por caja listos para transcribir a la plantilla oficial editable |
| [Zotero](https://www.zotero.org) / gestores | `referencias.bib` | Bibliografía BibTeX estándar |

El meta-análisis propio (Python puro: IV fijo/aleatorio DerSimonian-Laird,
Q/I²/τ², Egger, forest/funnel) cubre el caso base sin salir del motor; para
análisis avanzados la ruta declarada es **metafor** vía el CSV.

## Complementarias (declaradas, fuera del motor)

| Herramienta | Etapa | Licencia | Cuándo usarla en lugar del motor |
|---|---|---|---|
| [ASReview](https://asreview.nl) (Python, Apache-2.0) | Cribado T/A por active learning | Open source | Corpus muy grandes (>2.000 registros) donde prefieras cribado humano acelerado por ML clásico en vez de screening LLM; exporta su decisión final a RIS y reimpórtala con `ingest/manual_import.py` |
| [Rayyan](https://www.rayyan.ai) | Cribado colaborativo | **Comercial** (freemium) | Equipos de revisores humanos distribuidos; se declara por transparencia, no es open source |
| [PROSPERO](https://www.crd.york.ac.uk/prospero/) / [OSF](https://osf.io) | Preregistro | Registros públicos | Registra el protocolo ANTES de la búsqueda; el campo `registration:` de `protocol.yml` guarda el ID |
| [GROBID](https://github.com/kermitt2/grobid) (Apache-2.0) | PDF → texto estructurado | Open source | Extracción de texto completo de PDFs complejos, si el fallback nativo (pypdf) se queda corto |

## Regla de declaración

Toda herramienta externa usada en una revisión concreta debe quedar declarada
en el reporte (ítem trAIce M2: herramienta + versión + proveedor). El
`manifest.yml` registra automáticamente lo que pasa por el motor; lo que hagas
fuera (p. ej. cribado en ASReview) decláralo en `metodologia.md` al completar
los checklists.
