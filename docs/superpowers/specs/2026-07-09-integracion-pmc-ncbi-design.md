# Integración PMC/NCBI en RevisIA — Diseño

- **Fecha:** 2026-07-09
- **Autor:** Jhon Alexander Mosquera Vanegas (con Claude Code)
- **Estado:** aprobado para plan de implementación
- **Alcance decidido:** ambas capacidades — línea de búsqueda NCBI E-utilities
  + adquisición de texto completo OA vía BioC-PMC.

## 1. Contexto y motivación

RevisIA ya integra **Europe PMC**, que espeja MEDLINE/PubMed + PubMed Central +
preprints ([`search_backends.py`](../../../revisia/agents/search_backends.py)).
Sumar NCBI directo aporta dos cosas que Europe PMC no da:

1. **Procedencia PRISMA-S citable.** El flujo PRISMA pinta una línea por
   `source_db` en la caja de identificación (`identified_by_source`,
   [`prisma_flow.py`](../../../revisia/exports/prisma_flow.py)). Una línea
   rotulada **"PubMed"** con su cadena y su conteo es lo que un revisor/revista
   espera de una RS biomédica; un agregador no siempre se acepta como
   equivalente. La cobertura solapa con Europe PMC — el **dedup por DOI absorbe
   el solape**; el valor es la procedencia canónica, no más resultados.

2. **Texto completo estructurado (hueco real).** Hoy la adquisición de texto
   completo ([`fulltext.py`](../../../revisia/agents/fulltext.py)) depende de
   raspar URLs OA / Unpaywall y parsear PDFs. **BioC-PMC** entrega el texto
   completo del subconjunto OA como JSON limpio por *passages*, sin parsear PDF
   — mejora directamente la calidad del cribado full-text y la extracción.

## 2. Objetivos y no-objetivos

**Objetivos**
- Backend de búsqueda **PubMed** (`db=pubmed`) vía E-utilities, con `source_db="PubMed"`.
- Backend de búsqueda **PMC** (`db=pmc`) disponible como *opt-in* (no default).
- Adquisición de **texto completo OA estructurado** vía BioC-PMC, integrada como
  fuente preferente en el pipeline actual de full-text.
- **Cero dependencias nuevas**: `json` + `xml.etree` de stdlib; `httpx` ya es el
  extra `search`.
- **Tests offline** (mantener las 144 verdes + añadir cobertura del backend).
- Cortesía NCBI y `NCBI_API_KEY` **opcional** (funciona sin key).

**No-objetivos (fuera de alcance)**
- Cosecha masiva OAI-PMH / FTP / AWS Open Data (corpus locales de millones de
  artículos; desalineado con el flujo focalizado de una RS y con "clonar y correr").
- Búsqueda o texto completo tras *paywall* (se sigue cubriendo con import RIS/BibTeX).
- Expansión automática de MeSH o traducción de cadenas de búsqueda (la cadena la
  escribe el investigador en `search_strings/pubmed.txt`, como el resto de bases).

## 3. Arquitectura

Enfoque **A**: un cliente NCBI compartido + dos puntos de integración.

```
protocol.databases: [..., PubMed]        search_strings/pubmed.txt
        │                                         │
        ▼                                         ▼
revisia/agents/search_backends.py ── pubmed_search / pmc_search
        │                                         │
        └──────────────►  revisia/agents/ncbi.py  ◄─────────────┐
                          (cliente E-utilities + BioC + idconv)   │
        ┌──────────────►  (rate-limit, tool/email, api_key)      │
        │                                                        │
revisia/agents/fulltext.py ── fetch_fulltext ── BioC preferente ─┘
```

- **Módulo nuevo `revisia/agents/ncbi.py`** concentra TODA la lógica NCBI
  (rate-limit, key opcional, endpoints, parsing). Un solo lugar para la cortesía
  y el manejo de PMCID.
- **`search_backends.py`** registra los backends nuevos y reasigna alias.
- **`fulltext.py`** usa BioC como fuente estructurada preferente.

Cada archivo mantiene un propósito único; espeja la convención del repo
(un módulo por *concern* bajo `agents/`).

## 4. Componentes y contratos

### 4.1 `revisia/agents/ncbi.py` (nuevo)

Endpoints (documentados por el usuario):
- **esearch:** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi`
- **efetch:** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi`
- **ID Converter:** `https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/`
- **BioC-PMC:** `https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{PMCID}/unicode`

Cortesía / autenticación (aplicada a toda petición E-utilities):
- Params comunes: `tool=revisia`, `email=<mailto>` (si se pasa), `api_key=<NCBI_API_KEY>` (si está en entorno).
- **Rate-limit** con throttle: ≤ **3 req/s** sin key, ≤ **10 req/s** con key.
  Implementado en el cliente (espaciado mínimo entre llamadas); reutiliza el
  patrón `_client()` de `search_backends.py` (httpx, timeout 60s, follow_redirects).
- Sin key funciona igual, solo más lento. La key es opcional en `.env`.

Firmas (contratos):

```python
def esearch(db: str, term: str, retmax: int, *, mailto: str | None = None) -> list[str]:
    """Devuelve la lista de IDs (PMIDs para db=pubmed, PMCIDs para db=pmc)."""

def efetch_pubmed(pmids: list[str], *, mailto: str | None = None) -> list[SearchRecord]:
    """efetch db=pubmed retmode=xml → SearchRecord[] (parse con xml.etree)."""

def bioc_fulltext(pmcid: str, *, mailto: str | None = None) -> str | None:
    """BioC JSON → texto limpio concatenando passages. None si no está en OA."""

def idconv(ids: list[str], *, mailto: str | None = None) -> dict[str, str]:
    """DOI/PMID → PMCID vía ID Converter (para registros de otras bases)."""
```

Parsing de efetch (`PubmedArticleSet/PubmedArticle`), campos mínimos:
- título `.//ArticleTitle`; abstract `.//Abstract/AbstractText` (concatena
  secciones etiquetadas); autores `.//Author` (`LastName` + `ForeName`);
  año `.//PubDate/Year` (fallback `MedlineDate`); DOI
  `.//ArticleId[@IdType='doi']` o `.//ELocationID[@EIdType='doi']`;
  **PMID** `.//PMID`; **PMCID** `.//ArticleId[@IdType='pmc']`.
- `record_id` prioriza DOI normalizado (estable entre bases, idempotente en
  dedup); si falta, cae a `pubmed:<pmid>`.
- Guarda `extra["pmid"]` y `extra["pmcid"]` cuando estén (habilita texto
  completo directo sin idconv).

### 4.2 `revisia/agents/search_backends.py`

Dos backends nuevos con la firma estándar `fn(query, max_results, *, mailto) -> list[SearchRecord]`:

```python
def pubmed_search(query, max_results=25, *, mailto=None) -> list[SearchRecord]:
    # esearch(db=pubmed) → efetch_pubmed → source_db="PubMed"

def pmc_search(query, max_results=25, *, mailto=None) -> list[SearchRecord]:
    # esearch(db=pmc) → esummary(db=pmc) → source_db="PMC"  (opt-in)
```

`pmc_search` usa **esummary** (metadata ligera: título, autores, año, DOI, PMCID);
el abstract puede faltar para registros solo-PMC — es un tradeoff aceptable de una
base *opt-in* cuyo valor es surfacer OA que luego rinde texto completo por BioC.

**Reasignación de alias (decisión aprobada).** El alias `pubmed`/`medline` pasa a
apuntar a NCBI (canónico); Europe PMC conserva sus alias propios. Nuevo mapa:

| Alias | Antes | Después |
|---|---|---|
| `pubmed`, `medline` | Europe PMC | **NCBI `pubmed_search`** |
| `ncbi`, `entrez` | — | **NCBI `pubmed_search`** (sinónimos de la búsqueda canónica) |
| `pmc` | — | **NCBI `pmc_search`** (db=pmc, opt-in) |
| `europepmc`, `europe_pmc`, `epmc` | Europe PMC | Europe PMC (sin cambio) |

Justificación: para PRISMA-S una línea rotulada "pubmed" debe *ser* PubMed de
NCBI, no un agregador. Impacto: cambio con efecto en protocolos que hoy escriben
`pubmed` esperando Europe PMC (en v0.5.0, prácticamente solo los del autor). Se
documenta en CHANGELOG como *breaking* menor.

`MANUAL_ONLY` no cambia. `available_backends()` incluirá los nuevos nombres.

### 4.3 `revisia/agents/fulltext.py`

BioC-PMC como fuente estructurada **preferente**, antes del raspado OA/PDF:

- En `fetch_fulltext` (o un helper que consuma antes de `resolve_oa_url`): si el
  registro tiene PMCID (en `extra["pmcid"]`, o resoluble por DOI/PMID vía
  `idconv`), llamar `bioc_fulltext(pmcid)`. Si devuelve texto → `FullText(text,
  available=True, source_url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC…")`.
- Si no hay PMCID, BioC devuelve `None`, o el artículo no está en el subconjunto
  OA → **fallback intacto** al camino actual (`resolve_oa_url` → descarga →
  strip HTML / pypdf).
- Orden de prioridad: **BioC (estructurado) > `extra.fulltext_url` > `extra.oa_url`
  > Unpaywall**.
- Beneficia a *cualquier* registro con PMCID resoluble, venga de PubMed,
  OpenAlex o Europe PMC — sube `fulltext_assessed` y baja `fulltext_abstract_only`
  en el flujo PRISMA.

La resolución de PMCID vía `idconv` para registros de otras bases se hace **una
vez por registro y solo si no hay PMCID en `extra`** (respeta el rate-limit).

## 5. Flujo de datos end-to-end

**Búsqueda.** `protocol.databases` incluye `PubMed` → el pipeline lee
`search_strings/pubmed.txt` (cadena con sintaxis PubMed: `[tiab]`, `[mesh]`, …)
→ `search_database("pubmed", …)` → `pubmed_search` → esearch + efetch →
`SearchRecord[]` con `source_db="PubMed"`, `extra.pmcid/pmid` → **dedup por DOI**
fusiona con OpenAlex/Crossref/Europe PMC → PRISMA muestra "PubMed (n = …)" en
identificación.

**Texto completo.** En screening full-text y extracción, `fetch_fulltext` ve
`extra.pmcid` → BioC JSON → texto estructurado → mejor material para el juicio y
la extracción; los conteos PRISMA de "informes evaluados" reflejan la mejora.

## 6. Manejo de errores y degradación

- Sin red / 429 / 404 / artículo no-OA → **degradación** como el resto de
  backends: `search_database` ya captura `ValueError`/errores de red por base;
  `fetch_fulltext` cae al abstract (`available=False`). Ningún fallo NCBI rompe
  la corrida.
- Throttle respeta la cortesía NCBI aun en corridas grandes (N artículos BioC).
- Timeout 60s uniforme.

## 7. Reproducibilidad y provenance

- La cadena PubMed vive en `search_strings/pubmed.txt` (versionada con el protocolo).
- `source_db="PubMed"` deja rastro en records, dedup, PRISMA y bibliografía.
- `NCBI_API_KEY` solo afecta velocidad, no resultados (reproducibilidad intacta
  con o sin key).

## 8. Estrategia de tests (offline · TDD)

Mismo patrón que [`test_search_multibase.py`](../../../tests/test_search_multibase.py):
monkeypatch del cliente NCBI con payloads **fijos** (XML de efetch, JSON de
esearch/idconv/BioC). Casos:

1. `esearch` parsea `idlist`; `efetch_pubmed` → `SearchRecord` con
   título/abstract/autores/año/DOI/PMID/PMCID correctos.
2. `record_id` cae a `pubmed:<pmid>` cuando no hay DOI.
3. `bioc_fulltext` concatena passages → texto; `None` si el artículo no está en OA.
4. `idconv` mapea DOI/PMID → PMCID.
5. **Reasignación de alias**: `search_database("pubmed", …)` despacha a NCBI, no a
   Europe PMC; `available_backends()` incluye `pubmed`, `pmc`, `ncbi`, `entrez`.
6. `fetch_fulltext` prefiere BioC cuando hay PMCID; hace fallback sin PMCID.
7. Degradación: error de red en cualquier llamada NCBI no rompe (search sigue,
   fulltext cae al abstract).
8. Throttle: no introduce fallos (se puede mockear el temporizador para no dormir
   en tests).

Sin API key ni red reales; sin dependencias nuevas.

## 9. Cambios en documentación

- `docs/integraciones.md` — filas nuevas: **PubMed/PMC (E-utilities)** en Búsqueda
  y **BioC-PMC** en Texto completo.
- `README.md` — línea "búsqueda multi-base" y tabla de defaults (aclarar PubMed
  vía NCBI vs Europe PMC).
- `CHANGELOG.md` — entrada con la nota *breaking* menor del alias.
- `protocols/_TEMPLATE/protocol.yml` — comentario + `PubMed` en `databases` (junto
  a Europe PMC: procedencias distintas, dedup une); ejemplo
  `search_strings/pubmed.txt`.
- `.env.example` — `NCBI_API_KEY=` opcional con comentario (3→10 req/s).

## 10. Decisiones tomadas

1. **Enfoque A** (cliente NCBI compartido + dos integraciones). ✅
2. **Alias `pubmed`/`medline` → NCBI**; Europe PMC conserva los suyos. ✅
3. **PMC como búsqueda opt-in** (disponible, no en el default del template). ✅
4. **PubMed sí en el default del template**, conviviendo con Europe PMC. ✅
5. Cosecha masiva (OAI/FTP/AWS) **fuera de alcance**. ✅

## 11. Fases de implementación (para el plan)

1. **Cliente NCBI** (`ncbi.py`): esearch/efetch/idconv/bioc + cortesía + tests.
2. **Búsqueda** (`search_backends.py`): `pubmed_search`/`pmc_search` + reasignación
   de alias + tests.
3. **Texto completo** (`fulltext.py`): BioC preferente + fallback + tests.
4. **Docs + template + `.env.example` + CHANGELOG.**

Cada fase deja los tests verdes antes de la siguiente.
