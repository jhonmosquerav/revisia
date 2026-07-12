# Fuentes abiertas candidatas (hoja de ruta de backends)

La regla de RevisIA para automatizar una fuente es **API abierta + sin credenciales
de pago + corrida reproducible por cualquiera**. Las bases tras suscripción no se
automatizan (rompen la reproducibilidad y a menudo su licencia lo prohíbe): se
incorporan por **import RIS/BibTeX** (`revisia/ingest/manual_import.py`).

Este documento lista fuentes **candidatas a futuros backends**, priorizadas por
área, para orientar las próximas integraciones. Complementa
[`integraciones.md`](integraciones.md) (lo que el motor **ya** usa).

**Leyenda:** 🟢 API abierta (sin key o con key gratis) · 🟡 freemium/restringida ·
🔴 de pago → solo import RIS/BibTeX.

## Ya integradas (línea base)

OpenAlex · Crossref · Semantic Scholar · **PubMed/PMC (NCBI)** · Europe PMC ·
Unpaywall (texto completo) · **BioC-PMC** (texto completo estructurado) · import
RIS/BibTeX. Ver [`integraciones.md`](integraciones.md).

## Generales / multidisciplinares (cubren todas las áreas)

| Fuente | Estado | Aporte | Nota |
|---|---|---|---|
| [CORE](https://core.ac.uk) | 🟢 (key gratis) | ~300M+ docs OA **con texto completo** | Mejor candidata para full-text fuera de PMC |
| [BASE](https://www.base-search.net) | 🟢 (token) | ~400M docs OA agregados | Amplia cobertura de repositorios |
| [DOAJ](https://doaj.org) | 🟢 | Artículos de revistas 100% OA | API sencilla |
| [OpenAIRE](https://www.openaire.eu) | 🟢 | Agregador OA (fuerte en proyectos EU) | OAI + REST |
| [Lens.org](https://www.lens.org) | 🟡 | Scholarly + **patentes** | API de pago (trial 14 días) |

## Economía

| Fuente | Estado | Aporte |
|---|---|---|
| [RePEc / IDEAS / EconPapers](https://ideas.repec.org) | 🟢 (API desde 2015) | **La base de economía por excelencia**: 5.4M ítems, 4.8M a texto completo |
| [EconStor](https://www.econstor.eu) (ZBW) | 🟢 (OAI-PMH) | Repositorio OA de economía; ya alimenta RePEc |
| [NBER](https://www.nber.org) | 🟢 | Working papers; metadata abierta, actualizada semanal |
| [arXiv](https://arxiv.org) — `econ.*`, `q-fin` | 🟢 (sin key) | Preprints de economía y finanzas cuantitativas |
| [SSRN](https://www.ssrn.com) | 🔴 | Enorme en working papers econ/negocios/derecho; de Elsevier, sin API abierta → import |

## Administración / negocios / management

Las bases fuertes del área son **de pago y sin API abierta** → ruta import:
🔴 **Business Source (EBSCO)** · **ABI/INFORM (ProQuest)** · **Scopus** ·
**Web of Science**. Lo abierto que cubre management: OpenAlex/Crossref/Semantic
Scholar (indexan las revistas del área) + SSRN (por import) + RePEc (economía de
la empresa).

## Tecnología / Ciencias de la Computación

| Fuente | Estado | Aporte |
|---|---|---|
| [arXiv](https://arxiv.org) — `cs.*` | 🟢 (sin key) | 2.5M+ preprints; estándar en CS/IA |
| [DBLP](https://dblp.org) | 🟢 (dumps + API) | 6.3M+ publicaciones de CS (metadata, sin abstract) |
| Semantic Scholar | 🟢 *(ya integrada)* | Cobertura muy fuerte en CS |
| [IEEE Xplore](https://ieeexplore.ieee.org) / [ACM DL](https://dl.acm.org) | 🔴 | De pago → import |

## LATAM (perspectiva regional)

| Fuente | Estado | Aporte |
|---|---|---|
| [RedALyC](https://www.redalyc.org) | 🟢 (OAI/API) | **Domina ciencias sociales, economía y administración** en la región |
| [SciELO](https://scielo.org) | 🟢 (OAI + [ArticleMeta API](https://articlemeta.scielo.org)) | Salud y ciencias exactas + algo de social; LATAM + España/Portugal |
| [La Referencia](https://www.lareferencia.info) | 🟢 (OAI) | Agregador OA regional (nodos nacionales) |
| [CLACSO](https://www.clacso.org) | 🟢 (repositorio/OAI) | Ciencias sociales de LATAM |
| [Dialnet](https://dialnet.unirioja.es) | 🟡 | Producción en español; **no todo es OA** y su API es limitada |

## Bases de pago → ruta import RIS/BibTeX

Scopus, Web of Science, Embase, Business Source (EBSCO), ABI/INFORM (ProQuest) y
SSRN viven tras suscripción. **Scopus sí tiene API** ([Elsevier Developer
Portal](https://dev.elsevier.com)), pero **no es abierta**: exige key + suscripción
institucional (+ InstToken), cuotas semanales y prohíbe uso comercial/redistribución.
Por reproducibilidad y licencia, la ruta soportada es exportar RIS/BibTeX desde su
web y dejarlo en `imported/` (se fusiona en la deduplicación y se declara en PRISMA-S).

## Datos ≠ literatura (otra clase de integración)

Estas dan **indicadores/estadísticas**, no estudios — serían una funcionalidad
distinta a la búsqueda bibliográfica. Útiles para un análisis económico, no para el
corpus de una RS: 🟢 Banco Mundial · FMI · FRED · OECD (SDMX) · Eurostat · UN
Comtrade · **CEPALSTAT** · **DANE** · **Banco de la República**.

## Prioridad recomendada

De mayor a menor retorno para cobertura abierta sin licencias:

1. **Actualizar OpenAlex** al esquema con key (mejor fuente multidisciplinar; ver nota).
2. **arXiv** — integración casi trivial (API abierta, sin key); trae `econ`, `q-fin`, `cs`.
3. **CORE** — texto completo OA más allá de PMC.
4. **RePEc** — la línea citable de economía (como PubMed lo es de biomedicina).
5. **RedALyC + SciELO** — diferencial LATAM que casi ningún tool anglosajón integra.

## Excluidas y notas

- **Google Scholar**: sin API oficial; el scraping viola sus términos → no es una
  fuente "abierta" en el sentido que RevisIA necesita.
- **OpenAlex — API key (feb-2026):** OpenAlex pasó a requerir una API key (gratis,
  con crédito diario). El backend actual usa el *polite pool* con `--mailto`;
  **pendiente verificar** si sigue operando sin key o requiere ajuste de código.

## Fuentes

- [Elsevier Developer Portal (Scopus/ScienceDirect)](https://dev.elsevier.com) ·
  [Overview of Elsevier APIs](https://www.elsevier.support/dataasaservice/answer/overview-of-elsevier-apis)
- [IDEAS/RePEc](https://ideas.repec.org) · [The RePEc Blog — API](https://blog.repec.org/2015/09/28/repec-offers-now-an-api/) ·
  [NBER Working Papers Metadata](https://www.nber.org/research/data/nber-working-papers-and-chapters-metadata)
- [arXiv API User's Manual](https://info.arxiv.org/help/api/user-manual.html) · [DBLP](https://dblp.org)
- [Lista de APIs de metadatos académicos — SMU](https://researchguides.smu.edu.sg/api-list/scholarly-metadata-api)
- LATAM: [SciELO/Dialnet/Redalyc — comparativa](https://tesify.es/scielo-dialnet-redalyc-comparativa) · [RedALyC](https://www.redalyc.org)
