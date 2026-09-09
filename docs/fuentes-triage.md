# Triage de fuentes: APIs y formas de conexión (verificado en vivo · 2026-09-03)

Este documento responde a una pregunta concreta: **de una lista de 40 fuentes de
una guía bibliotecaria universitaria, ¿cuáles pueden convertirse en backend de
búsqueda de RevisIA, cuáles no, y por qué?** Cada fila fue verificada con
peticiones HTTP reales (código de estado y forma de la respuesta), no de
memoria. Complementa [`fuentes-candidatas.md`](fuentes-candidatas.md) (hoja de
ruta por área) e [`integraciones.md`](integraciones.md) (lo que el motor ya usa).

La regla no cambia: **API abierta + sin credenciales de pago + corrida
reproducible por cualquiera**. Lo que no cumpla va por import RIS/BibTeX o queda
fuera.

**Leyenda:** 🟢 backend viable · 🟡 viable con limitaciones · 🔵 datos/normativa
con API (otra clase de integración, no corpus bibliográfico) · 🔴 de pago → solo
import · ❌ sin API o no es fuente bibliográfica · ✅ ya integrada.

## 1. Backends nuevos (🟢 implementados en esta iteración)

| Fuente | Área | Protocolo verificado | Auth | Alias en `protocol.yml` | Nota |
|---|---|---|---|---|---|
| [ERIC](https://eric.ed.gov) | Educación | REST JSON `api.ies.ed.gov/eric/?search=…&format=json&rows=&start=` (máx 2 000/página, sintaxis Lucene, 2,1 M registros) | ninguna | `eric` | Obligatoria en RS de educación; ~50 % son documentos grises (ED) que no están en Crossref |
| [DOAJ](https://doaj.org) | Multidisciplinar | REST JSON `doaj.org/api/search/articles/<q>?page=&pageSize=` (máx 100; 2 req/s; metadatos CC0; ~10 M artículos) | ninguna | `doaj` | Revistas OA "doradas", muchas LATAM sin DOI; abstract en texto plano |
| [UNESDOC](https://unesdoc.unesco.org) vía [UNESCO DataHub](https://data.unesco.org) | Educación, cultura, políticas | REST JSON Opendatasoft `data.unesco.org/api/explore/v2.1/catalog/datasets/doc001/records?where=search("q")&limit=&offset=` | ninguna | `unesdoc`, `unesco` | Literatura gris institucional ausente de OpenAlex. Es un *snapshot* del catálogo (corte 2025-01), no el índice vivo |
| [BVS / LILACS](https://bvsalud.org) | Salud LATAM | REST JSON iAHx `search.bvsalud.org/portal/?output=json&q=&count=&from=` (`from` 1-based; máx 500/petición; año en la query `year_cluster:[2020 TO 2024]`) | ninguna | `bvs`, `lilacs`, `bvsalud`; `gim` (Global Index Medicus) | LILACS **no está en PubMed ni Europe PMC**: es el diferencial en español/portugués + DeCS. API no documentada oficialmente (riesgo de cambio) |
| [AGROSAVIA](https://repository.agrosavia.co) | Agropecuario CO | DSpace 9.1 REST `…/server/api/discover/search/objects?query=&dsoType=item&page=&size=` (HAL+JSON; 18 k ítems; DOI 10.21930) | ninguna | `agrosavia` | Piloto del adaptador **DSpace 7+ genérico** |
| [CLACSO](https://biblioteca-repositorio.clacso.edu.ar) | Sociales LATAM | DSpace 10 REST (misma forma) · ~30 k libros/capítulos, casi sin DOI | ninguna | `clacso` | Cobertura que OpenAlex no tiene (libros sin DOI). El Greenstone antiguo (`biblioteca.clacso.edu.ar`) está caído (526) |
| [Banco Mundial · OKR](https://openknowledge.worldbank.org) | Desarrollo, economía | DSpace 7 REST (misma forma) · 41,5 k ítems, DOI 10.1596, CC BY 3.0 IGO, PDF/TXT | ninguna | `worldbank`, `okr`, `bancomundial` | Literatura gris institucional con DOI (dedup con Crossref) |
| [DOAB](https://directory.doabooks.org) | Libros OA | DSpace 6 REST `…/rest/search?query=&expand=metadata&limit=&offset=` (sin `total`; 108 k libros) + OAI-PMH | ninguna | `doab` | Primer backend de **libros**; metadatos como lista plana key/value |

Todos: **cero dependencias nuevas**, sin API key, `httpx` (extra `search`).

## 2. 🟢 viables, no implementados aún

| Fuente | Por qué espera |
|---|---|
| [E-LIS](https://eprints.rclis.org) (EPrints, 27 k) | Export JSON sin auth (`/cgi/search/simple?q=&_action_export=1&output=JSON`) pero **sin paginación** (devuelve todo). Nicho: solo ciencia de la información |
| [Persée](https://www.persee.fr) (900 k, francés) | SPARQL con texto libre (`data.persee.fr/sparql`, `bif:contains`) + OAI-PMH; DOI 10.3406 → Crossref. Pertinencia LATAM baja; requiere modelar vocabulario RDF |

## 3. 🟡 viables con limitaciones (no cumplen el patrón "query → registros")

| Fuente | Qué hay | Limitación | Ruta hoy |
|---|---|---|---|
| [AGRIS](https://agris.fao.org) (FAO, 16,6 M) | Open Data Set: XML DCAT/DC por proveedor (1 236 ficheros, CC BY 4.0) | Sin API de búsqueda; web tras Cloudflare; OAI 404 | Índice local del ODS (pipeline offline) · pendiente |
| [Dialnet](https://dialnet.unirioja.es) | OAI-PMH `oai/OAIHandler` (solo `oai_dc`, sin DOI) | Solo cosecha por fecha/set; `robots.txt` veta `/buscar`; licencia de metadatos en zona gris | **Import RIS** (la web exporta) |
| [Redalyc](https://www.redalyc.org) | OAI-PMH en `http://148.215.1.70/redalyc/oai` (IP sin TLS), sets por ISSN | Sin búsqueda; `oai_dc` sin abstract ni DOI; `/api` 404 | OpenAlex/Crossref ya indexan sus DOIs; import RIS para el resto |
| [SciELO](https://scielo.org) | ArticleMeta `articlemeta.scielo.org/api/v1/article/…` (JSON, por PID/colección/fecha) | ArticleMeta **no busca por texto**; `search.scielo.org?output=rss` funciona solo en navegador (WAF bunny-shield → 403) | OpenAlex/Crossref (SciELO deposita DOIs) · cosecha ArticleMeta pendiente |
| [Biblioteca Nacional de Colombia](https://catalogoenlinea.bibliotecanacional.gov.co) | Atom SirsiDynix `client/rss/hitlist/bnc/qu=<q>` | 300 resultados fijos, sin paginar ni filtrar; sin abstract; no documentada | Manual |
| [Biblioteca Virtual Miguel de Cervantes](https://data.cervantesvirtual.com) | SPARQL (Virtuoso) | Obras literarias/dominio público, sin abstract ni DOI; fuera del perfil de una RS | Solo humanidades |
| [Biblioteca Jurídica Virtual UNAM](https://biblio.juridicas.unam.mx/bjv) | La BJV no tiene API; el ecosistema IIJ sí: OJS OAI (`revistas.juridicas.unam.mx/index.php/index/oai`, DOI 10.22201) y DSpace 6 (`ru.juridicas.unam.mx/rest`) | Búsqueda por texto solo en el DSpace 6 (no probado) | Crossref/OpenAlex para las revistas; adaptador DSpace 6 pendiente |
| [Biblioteca Digital Mundial](https://www.wdl.org) → [loc.gov](https://www.loc.gov/collections/world-digital-library/) | WDL cerró en 2021; loc.gov JSON API (`?fo=json&q=`) documentada, 20 req/min | Cloudflare/Turnstile bloqueó la verificación en vivo; patrimonio, no literatura científica | Pendiente |
| [BioMed Central](https://www.biomedcentral.com) | Springer Nature OA/Meta API (`api.springernature.com`) | Requiere key gratuita (500 hits/día) y es **100 % redundante**: todo BMC está en Europe PMC/PubMed, Crossref (10.1186) y DOAJ | Ya cubierta |

## 4. 🔵 Datos / normativa / patentes con API (otra clase de integración)

No son corpus de una revisión sistemática; sirven para contexto, *evidence maps*
o scoping reviews. Se documentan por si RevisIA incorpora una etapa de "datos de
contexto" en el futuro.

| Fuente | API verificada | Auth |
|---|---|---|
| [DANE · ANDA](https://microdatos.dane.gov.co) | NADA REST `index.php/api/catalog/search?sk=&from=&to=&ps=` (570 estudios) | ninguna |
| [Banco Mundial · Indicators](https://api.worldbank.org) | `v2/country/COL/indicator/<id>?format=json` (29 544 series, CC BY 4.0) | ninguna |
| [datos.gov.co](https://www.datos.gov.co) | Socrata Discovery `api.us.socrata.com/api/catalog/v1?domains=www.datos.gov.co&q=` + SODA por dataset (8 385 datasets, CC BY) | ninguna (app token opcional) |
| [DNP](https://www.dnp.gov.co) | Solo vía Socrata (183 datasets). Documentos CONPES: PDFs públicos sin índice programático (SharePoint search → 500; CDT → 401) | ninguna |
| [Banco de Patentes · SIC](https://www.sic.gov.co/banco-de-patentes) | Dataset Socrata `w8hf-jz4a` (24 103 patentes concedidas CO). SIPI sin API. Internacional: EPO OPS (key gratuita, 403 sin token), Lens (de pago), Google Patents (XHR no oficial), PatentsView (migró a USPTO ODP con key) | ninguna / key |

## 5. 🔴 De pago o con credenciales por usuario → import RIS/BibTeX

| Fuente | Motivo |
|---|---|
| [DynaMed](https://www.dynamed.com) (EBSCO) | MedsAPI OAuth2 bajo suscripción; además es síntesis clínica, no registros |
| [Mendeley](https://www.mendeley.com) (Elsevier) | Catálogo vía OAuth con app registrada por usuario (401 sin auth); catálogo *crowd-sourced*, no reproducible. Mendeley Desktop exporta RIS/BibTeX |
| [Lens.org](https://www.lens.org) | API por plan de pago (401) |

## 6. ❌ Sin API o fuera del alcance bibliográfico

| Fuente | Evidencia |
|---|---|
| AGORA (FAO/Research4Life) | Pasarela de acceso institucional a editoriales comerciales; `agora.research4life.org` 403 Cloudflare; login por elegibilidad de país |
| Bioline International | Migrada a UTSC (Islandora); OAI 403; anti-bot Anubis; TLS del dominio original revocado. OpenAlex ya la indexa como *source* (19,9 k works) |
| BVS Legislación en Salud | Normativa; servidor `legislacion.bvsalud.org` sin respuesta (timeout / ECONNREFUSED) |
| PEDro | Solo HTML (Laravel + CSRF), sin export. Valor único (puntaje PEDro) → búsqueda manual |
| Vesalius | Dominio sin DNS (última captura Wayback 2024-02); recurso educativo, no bibliográfico |
| E-Book Directory | Directorio de enlaces; RSS roto |
| El Libro Total | Biblioteca de lectura; JSP internos sin contrato |
| Latindex | Directorio de **revistas**, no artículos; export JSON/CSV → 403. Para validar revistas OA iberoamericanas usar DOAJ (`/api/search/journals/issn:…`) |
| Google Scholar | Sin API; `robots.txt` veta `/scholar`; resultados no reproducibles. OpenAlex + Semantic Scholar cubren lo indexable |
| SCImago SJR | Ranking de revistas; CSV bloqueado por Cloudflare (403). Alternativa abierta: `sources` de OpenAlex (h-index, `is_in_doaj`) |
| ASTREA (Normograma Medellín) | HTML estático |
| Diario Oficial / SUIN-Juriscol | JSF con sesión; SUIN cierra la conexión TLS a clientes no navegador |
| ProColombia | RSS de noticias + sitemap (238 publicaciones); JSON:API de Drupal roto (PHP fatal) |
| Comisión de la Verdad | Archivo (no DSpace); REST privado del frontend sin contrato; fuentes primarias, no literatura científica |
| Artehistoria | Portal divulgativo Drupal sin API |

## 7. ✅ Ya integrada, con una novedad

**PubMed Central.** Sigue vía E-utilities. El **PMC OA Web Service (`oa.fcgi`) fue
descontinuado en 2026** (404). RevisIA no lo usaba. El ID Converter antiguo
(`www.ncbi.nlm.nih.gov/pmc/utils/idconv`) responde con **301** a
`pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/`; el backend actualiza la URL.

## 8. Patrones que emergen

1. **DSpace 7+ es el estándar de facto en repositorios LATAM e institucionales.**
   Un solo adaptador (`agents/dspace.py`) sirve AGROSAVIA, CLACSO y el OKR del
   Banco Mundial, y cualquier otro repositorio con `/server/api/discover`.
   Añadir uno nuevo es una línea (URL base + nombre).
2. **Las fuentes iberoamericanas "grandes" (Redalyc, SciELO, Dialnet) no ofrecen
   búsqueda por texto.** Ofrecen cosecha OAI-PMH. Su contenido con DOI ya llega
   por OpenAlex/Crossref; el resto exige un índice local (fuera del patrón
   "clonar y correr") o import RIS.
3. **Muchos portales bloquean clientes no navegador** (Cloudflare, bunny-shield,
   Anubis). No se hace scraping: rompe la reproducibilidad y suele violar términos.
4. **Datos ≠ literatura.** DANE, Banco Mundial (indicadores), datos.gov.co y SIC
   tienen APIs abiertas excelentes, pero son otra funcionalidad.

## Método

Verificación el 2026-09-03 con `curl` (User-Agent identificado) y el navegador
integrado cuando un WAF bloqueaba clientes HTTP. Se reporta el código HTTP real y
la forma de la respuesta; lo que no pudo verificarse está marcado como tal
(loc.gov, SUIN-Juriscol, BVS Legislación, licencia de metadatos de DOAB, cuota de
ERIC). Los endpoints de los backends implementados se re-verificaron por segunda
vez antes de codificar (paginación de BVS, forma HAL de las tres instancias
DSpace, filtros de año).
