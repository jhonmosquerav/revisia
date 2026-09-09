# Backends de fuentes abiertas (ERIC, DOAJ, UNESDOC, BVS/LILACS, DSpace 7+, DOAB) — Diseño

- **Fecha:** 2026-09-03
- **Autor:** Jhon Alexander Mosquera Vanegas (con Claude Code)
- **Estado:** propuesto; decisiones de alcance tomadas con criterio explícito
  (ver §10), reversibles antes de mezclar.
- **Insumo:** triage verificado en vivo de 40 fuentes
  ([`docs/fuentes-triage.md`](../../fuentes-triage.md)).

## 1. Contexto y motivación

RevisIA busca hoy en OpenAlex, Crossref, Semantic Scholar, PubMed/PMC y Europe PMC.
Esa línea base es fuerte en biomedicina y en todo lo que tenga DOI, y débil en
tres huecos que una revisión con perspectiva LATAM y multidisciplinar nota
enseguida:

1. **Literatura en español/portugués fuera de MEDLINE** (LILACS, repositorios
   institucionales, libros sin DOI).
2. **Literatura gris institucional** (UNESCO, Banco Mundial, ERIC "ED").
3. **Educación y libros OA**, áreas donde PRISMA-S espera fuentes específicas.

El triage muestra que ocho fuentes cubren esos huecos con API abierta, sin key y
reproducible. Este diseño las integra siguiendo el patrón existente
(`fn(query, max_results, *, mailto) -> list[SearchRecord]`) y aprovecha que
tres de ellas son DSpace 7+ para escribir **un adaptador genérico** en vez de
tres backends.

## 2. Objetivos y no-objetivos

**Objetivos**
- Ocho bases nuevas despachables por nombre desde `protocol.databases`:
  `eric`, `doaj`, `unesdoc`, `bvs` (+ `gim`), `agrosavia`, `clacso`,
  `worldbank`, `doab`.
- Adaptador **DSpace 7+ REST** reutilizable: añadir otro repositorio es una
  línea (URL base + `source_db`).
- **Degradación por base** en el pipeline: un backend que falle por red no
  tumba la corrida; se registra y se sigue con las demás.
- Cero dependencias nuevas; sin API keys; tests offline.
- Actualizar la URL del ID Converter de PMC (la antigua responde 301).

**No-objetivos**
- Cosecha OAI-PMH masiva (Redalyc, Dialnet, AGRIS, SciELO ArticleMeta): otra
  clase de integración, requiere índice local.
- Integraciones de datos (DANE, Banco Mundial Indicators, datos.gov.co, SIC).
- Configurar instancias DSpace arbitrarias desde `protocol.yml` (cambia el
  esquema del protocolo; el adaptador lo permite en código y se documenta cómo).
- Texto completo desde estas fuentes (UNESDOC/OKR traen URL de PDF en `extra`;
  el pipeline de full-text actual ya intenta `extra.oa_url`).

## 3. Arquitectura

```
protocol.databases: [OpenAlex, …, ERIC, DOAJ, BVS, CLACSO]   search_strings/<db_key>.txt
        │
        ▼
revisia/agents/search_backends.py ── BACKENDS (despacho por alias) ─────┐
        │                                                               │
        ├── busqueda.py (OpenAlex)      ├── ncbi.py (PubMed/PMC)        │
        ├── open_backends.py  (NUEVO)   ├── dspace.py  (NUEVO)          │
        │     eric_search               │     dspace7_search(base_url…) │
        │     doaj_search               │     agrosavia / clacso / okr  │
        │     unesdoc_search            │     doab_search (DSpace 6)    │
        │     bvs_search (portal|gim)   │                               │
        └────────── revisia/agents/_http.py (NUEVO: cliente httpx + strip_html)
                                                                        │
revisia/orchestration/pipeline.py ── _multi_database_search ── degradación por base
```

Tres módulos nuevos, cada uno con un propósito:

- **`agents/_http.py`** — `make_client(timeout)` y `strip_html(text)`. Extrae lo
  que hoy está duplicado entre `search_backends.py` y `ncbi.py` para que los
  módulos nuevos no importen `search_backends` (evita import circular: es
  `search_backends` quien los importa a ellos). `search_backends._client` se
  conserva como alias para no romper los tests existentes que lo parchean.
- **`agents/open_backends.py`** — cuatro backends REST JSON sin estado (ERIC,
  DOAJ, UNESDOC, BVS). Cada uno: construir params → GET → parsear → `SearchRecord`.
- **`agents/dspace.py`** — adaptador DSpace 7+ (`discover/search/objects`, HAL)
  parametrizado por URL base y nombre de fuente, tres instancias registradas
  como funciones parciales, más `doab_search` (DSpace 6 `/rest/search`, formato
  distinto pero misma familia de metadatos DC).

`search_backends.py` solo crece en el registro `BACKENDS` y en el docstring.

## 4. Contratos por backend

Firma común: `fn(query: str, max_results: int = 25, *, mailto: str | None = None) -> list[SearchRecord]`.
`record_id` prioriza el DOI normalizado (minúsculas, sin prefijo `https://doi.org/`);
si falta, `"<fuente>:<id nativo>"`. Título ausente → `"(sin título)"`. Año no
parseable → `None`. HTML en abstracts → limpiado. Todo esto es lo que hacen los
backends existentes; los nuevos no inventan convenciones.

### 4.1 ERIC (`open_backends.eric_search`)
- URL `https://api.ies.ed.gov/eric/`; params `search=<query>`, `format=json`,
  `rows=min(max_results, 2000)`, `start=0`, `fields=id,title,author,publicationdateyear,description,url,language,peerreviewed,publicationtype`.
- Parse `response.docs[]`: `id` (EJ…/ED…), `title`, `author[]`,
  `publicationdateyear` (int), `description` → abstract, `url` (si es
  `doi.org/…` se extrae el DOI), URL de respaldo `https://eric.ed.gov/?id=<id>`.
- `source_db="ERIC"`; `extra={"eric_id", "peer_reviewed", "language"}`.
- La sintaxis de la cadena (Lucene: `AND`, `campo:valor`, rangos de año) la
  escribe el investigador en `search_strings/eric.txt`.

### 4.2 DOAJ (`open_backends.doaj_search`)
- URL `https://doaj.org/api/search/articles/<query url-encoded>`; params
  `page=1`, `pageSize=min(max_results, 100)`.
- Parse `results[].bibjson`: `title`, `abstract`, `year` (str→int),
  `author[].name`, `identifier[type=doi].id`, `link[type=fulltext].url`,
  `journal.title`, `journal.language`.
- `source_db="DOAJ"`; `extra={"oa_url": link fulltext, "journal": …}`;
  `record_id` sin DOI → `doaj:<results[].id>`.
- Cortesía: DOAJ pide 2 req/s; un backend hace una petición por búsqueda.
- Tope 100 por búsqueda (una página). Si `max_results > 100` se pagina
  `page=2…` hasta alcanzar el tope o agotar `total`.

### 4.3 UNESDOC vía DataHub (`open_backends.unesdoc_search`)
- URL `https://data.unesco.org/api/explore/v2.1/catalog/datasets/doc001/records`;
  params `where=search("<query con comillas escapadas>")`, `limit=min(max_results,100)`,
  `offset=0`.
- Parse `results[]`: `title`, `description` → abstract, `year[0]` (int),
  `creator` (string con comas → lista), `url` (ark), `language[]`, `uuid`,
  `isbn`, `document_type`.
- `source_db="UNESDOC"`; sin DOI → `record_id="unesdoc:<uuid>"`;
  `extra={"language", "document_type", "isbn"}`.
- El investigador puede añadir filtros ODSQL en la cadena (p. ej.
  `AND year:"2020"`): la cadena entera se pasa como `where` **si** contiene
  `search(`; si no, se envuelve en `search("…")`. Así la cadena simple sigue
  funcionando y la avanzada también.

### 4.4 BVS / LILACS (`open_backends.bvs_search`)
- URL `https://search.bvsalud.org/<instancia>/` con `instancia="portal"`
  (BVS regional, `lilacsplus`) por defecto; alias `gim` → `"gim"` (Global
  Index Medicus, OMS). Params `output=json`, `lang=es`, `q=<query>`,
  `count=min(max_results, 500)`, `from=1`.
- Cabecera `User-Agent: revisia/<versión> (mailto:…)` explícita (verificado que
  la API responde a ese UA; un UA vacío/por defecto de algunos clientes da 403).
- Parse `diaServerResponse[0].response.docs[]`: `ti[0]`, `ab[0]`, `au[]`,
  `da` (YYYYMM → año), `aid` (DOI), `ur[0]`, `la[]`, `db[]`, `id`, `is[]`.
- `source_db="BVS"` (o `"GIM"`); sin DOI → `record_id="bvs:<id>"`;
  `extra={"lilacs_id", "language", "db", "issn"}`.
- Paginación: `from` es 1-based; `from = offset + 1`. Se pagina solo si
  `max_results > 500`.
- Año: se escribe en la cadena (`year_cluster:[2020 TO 2024]`), no como
  `filter=` (verificado que `filter=year_cluster` se corrompe en el servidor).

### 4.5 DSpace 7+ (`dspace.dspace7_search`)
- `dspace7_search(query, max_results, *, mailto, base_url, source_db)`; las
  instancias públicas son `functools.partial` con la firma estándar:
  - `agrosavia_search` → `https://repository.agrosavia.co`, `"AGROSAVIA"`
  - `clacso_search` → `https://biblioteca-repositorio.clacso.edu.ar`, `"CLACSO"`
  - `worldbank_okr_search` → `https://openknowledge.worldbank.org`, `"WorldBankOKR"`
- URL `<base>/server/api/discover/search/objects`; params `query=`,
  `dsoType=item`, `page=`, `size=min(max_results,100)`. Se pagina hasta
  `max_results` o `page.totalPages`.
- Parse HAL: `_embedded.searchResult._embedded.objects[]._embedded.indexableObject`
  → `handle`, `uuid`, `metadata` (dict campo → lista de `{value, language}`).
  Campos DC: `dc.title`, `dc.contributor.author` (+ `dc.contributor.editor`,
  `dc.contributor.corporatename` como respaldo), `dc.date.issued` (primeros 4
  dígitos → año), `dc.description.abstract`, `dc.identifier.doi`,
  `dc.identifier.uri` (respaldo `<base>/handle/<handle>`), `dc.language.iso` /
  `dc.language`, `dc.identifier.isbn`, y `okr.pdfurl` (OKR) → `extra.oa_url`.
- Título multilingüe (OKR devuelve dos): se toma el primero; los demás van a
  `extra["titles"]`.
- Sin DOI → `record_id="<source_db lower>:<handle>"`.
- Año: el investigador lo pone en la cadena (`cacao AND dc.date.issued:[2020 TO 2024]`,
  verificado 200 en AGROSAVIA); el backend no añade facetas porque su sintaxis
  varía por instancia (`f.dateIssued=[a TO b],equals` funciona en una y devuelve
  400 en otra).

### 4.6 DOAB (`dspace.doab_search`)
- URL `https://directory.doabooks.org/rest/search`; params `query=`,
  `expand=metadata`, `limit=min(max_results,100)`, `offset=`.
- Parse lista JSON de ítems: `uuid`, `handle`, `metadata[]` como lista plana
  `{key, value}` → se agrupa a dict campo → lista. Campos: `dc.title`,
  `dc.contributor.author` / `.editor`, `dc.date.issued`, `dc.description.abstract`,
  `oapen.identifier.doi`, `dc.identifier.uri`, `dc.language`, `dc.identifier.isbn`
  / `dc.identifier`.
- Sin `total`: se pagina mientras la página venga llena y falten resultados.
- `source_db="DOAB"`; sin DOI → `record_id="doab:<handle>"`;
  `extra={"type": "book", "isbn", "language"}`.

## 5. Registro de alias (`search_backends.BACKENDS`)

| Alias (`db_key`) | Backend | `source_db` |
|---|---|---|
| `eric` | `eric_search` | ERIC |
| `doaj` | `doaj_search` | DOAJ |
| `unesdoc`, `unesco`, `unesdoc_unesco` | `unesdoc_search` | UNESDOC |
| `bvs`, `lilacs`, `bvsalud` | `bvs_search` (portal) | BVS |
| `gim`, `globalindexmedicus` | `bvs_search` (gim) | GIM |
| `agrosavia` | `agrosavia_search` | AGROSAVIA |
| `clacso` | `clacso_search` | CLACSO |
| `worldbank`, `okr`, `bancomundial`, `worldbankokr` | `worldbank_okr_search` | WorldBankOKR |
| `doab` | `doab_search` | DOAB |

`MANUAL_ONLY` suma `dialnet`, `redalyc`, `scielo`, `mendeley`, `googlescholar`,
`pedro`, `dynamed`, `lens`: bases nombradas en el triage cuyo camino es import
RIS/BibTeX; el mensaje de error del despacho ya sugiere la importación manual.
Ningún alias existente cambia.

## 6. Degradación por base (pipeline)

`_multi_database_search` hoy captura solo `ValueError` (base sin backend). Con
más backends, un 5xx, timeout o JSON inválido en cualquiera tumba la corrida.
Cambio:

```python
try:
    records += search_backends.search_database(db, query, max_results, mailto=mailto)
except ValueError:
    continue                       # sin backend → imported/
except Exception as exc:           # red, 5xx, JSON: degradar, no abortar
    failures.append({"db": db, "error": f"{type(exc).__name__}: {exc}"})
    continue
```

Los fallos se devuelven junto a los registros (la función pasa a devolver
`(records, failures)`) y el pipeline los escribe en `01_search/failures.json`
para que la auditoría y PRISMA-S (ítem "fuentes consultadas / fecha") tengan
constancia de qué base no respondió. Una base caída no es silenciosa: queda en
disco y en el log.

## 7. Reproducibilidad y provenance

- Cada base nueva deja rastro por `source_db` en records, dedup, flujo PRISMA
  (`identified_by_source`) y bibliografía; nada cambia en esos módulos.
- Cadenas en `search_strings/<alias>.txt`, versionadas con el protocolo.
- Sin keys: no hay diferencia de resultados entre máquinas.
- `User-Agent` identificado (`revisia/<versión> (mailto:…)`) en todos los
  backends nuevos vía `_http.make_client(mailto=…)`: es cortesía estándar y BVS
  lo necesita.

## 8. Estrategia de tests (offline · TDD)

Nuevo `tests/test_open_backends.py` y `tests/test_dspace.py`, patrón
`_FakeClient` de `test_search_multibase.py` con payloads fijos tomados de las
respuestas reales verificadas (recortadas). Casos:

1. ERIC: parse completo; DOI extraído de `url` doi.org; sin `url` → URL eric.ed.gov;
   `record_id="eric:EJ…"` sin DOI.
2. DOAJ: parse `bibjson`; `record_id` = DOI; `oa_url` desde `link fulltext`;
   `pageSize` topado a 100.
3. UNESDOC: `where` = `search("q")` para cadena simple y pasa la cadena tal cual
   si ya contiene `search(`; `creator` → lista; año desde `year[0]`.
4. BVS: parse `diaServerResponse`; `da=202707` → 2027; `from` 1-based en la 2.ª
   página; instancia `gim` → `source_db="GIM"`; UA presente en el cliente.
5. DSpace 7: parse HAL; título multilingüe → primero + `extra.titles`; sin DOI →
   `agrosavia:<handle>`; paginación respeta `totalPages`; `okr.pdfurl` → `oa_url`.
6. DOAB: metadata plana → dict; editor como autor de respaldo; paginación sin
   `total` se detiene con página corta.
7. Registro: `available_backends()` contiene los nueve alias; `search_database("BVS", …)`
   despacha; `search_database("dialnet", …)` sugiere importación manual.
8. Pipeline: un backend que lanza `RuntimeError` no aborta; `failures` contiene la
   base y los demás registros llegan.
9. NCBI: la URL de idconv nueva sigue pasando el test existente (el router
   enruta por subcadena `idconv`).

Sin red ni keys. Los 168 tests actuales siguen en verde.

## 9. Documentación

- `docs/fuentes-triage.md` (nuevo): el triage completo (ya escrito).
- `docs/fuentes-candidatas.md`: sección "Ya integradas" actualizada; enlace al
  triage; DOAJ/RedALyC/SciELO/CLACSO/Dialnet pasan a su estado real.
- `docs/integraciones.md`: filas nuevas en "Integradas".
- `README.md`: línea de búsqueda multi-base y tabla de bases.
- `AGENTS.md`: fila `busqueda` con las bases nuevas.
- `protocols/_TEMPLATE/protocol.yml`: comentario con los alias disponibles
  (los defaults no cambian: las nuevas son opt-in por área).
- `protocols/_TEMPLATE/search_strings/`: ejemplos `eric.txt`, `doaj.txt`,
  `bvs.txt` con la sintaxis de cada motor.
- `CHANGELOG.md`: entrada en `[Unreleased]`.

## 10. Decisiones tomadas (con criterio, reversibles)

1. **Ocho backends, no diez.** E-LIS (sin paginación, nicho) y Persée (SPARQL,
   francés) quedan documentados como 🟢 pendientes: bajo retorno para el esfuerzo
   y para el perfil LATAM del proyecto.
2. **Adaptador DSpace genérico** en vez de tres backends: es el patrón dominante
   en repositorios LATAM; el coste marginal de un repositorio más es una línea.
3. **BVS con instancia `portal` por defecto** (BVS regional / LILACS+), `gim`
   como alias opt-in: `portal` es la procedencia que un revisor LATAM espera ver
   en PRISMA-S ("LILACS vía BVS").
4. **Defaults del template sin cambios.** Las bases nuevas son por área; un
   protocolo de educación añade `ERIC`, uno de salud LATAM añade `BVS`. Meter
   ocho bases por defecto multiplicaría el ruido del cribado.
5. **Redalyc/SciELO/Dialnet → `MANUAL_ONLY`** con mensaje explícito. Es la
   verdad técnica hoy (sin búsqueda por texto); su contenido con DOI ya entra
   por OpenAlex/Crossref.
6. **Degradación por base con registro en disco**, no silenciosa. Un `except
   Exception` acotado a la llamada del backend, con el fallo escrito en
   `01_search/failures.json`.
7. **`_http.py` compartido** en vez de duplicar `_client` por cuarta vez.

## 11. Fases de implementación (para el plan)

1. `_http.py` + refactor mínimo de `search_backends`/`ncbi` para usarlo (tests
   existentes en verde) + URL nueva de idconv.
2. `open_backends.py`: ERIC, DOAJ, UNESDOC, BVS + tests.
3. `dspace.py`: DSpace 7 genérico + tres instancias + DOAB + tests.
4. Registro de alias + `MANUAL_ONLY` + tests de despacho.
5. Degradación por base en el pipeline + `failures.json` + test.
6. Docs, template, CHANGELOG. Verificación final: suite completa + `ruff`.
