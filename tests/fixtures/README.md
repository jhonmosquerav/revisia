# Fixtures de red

Respuestas JSON **reales** de APIs públicas, recortadas a tres ítems, para probar los parsers
sin red (auditoría 2026-09-03, M18). Los metadatos bibliográficos (títulos, autores, DOI, años) son
hechos y se reutilizan; los **abstracts no son CC0**: solo se conservan completos los de ítems con licencia abierta, y los demás
van recortados. No contienen correos ni claves.

## `crossref_works.json`

- Capturada el 2026-10-20 con
  `https://api.crossref.org/works?query=large+language+models+systematic+review+screening&rows=3&filter=has-abstract:true`
  (sin `mailto` en la URL guardada).
- Recorte: se conservan `status`, `message-type`, `message.total-results` y `message.items`;
  se borraron `message.facets` y `message.query` (y el resto de claves de `message`).
- Edición: en el tercer ítem se borró la clave `DOI`, para ejercitar el `record_id` de respaldo.
  Se quitó `reference` de los tres ítems (el parser no la usa).
- Licencias: `10.20944/preprints202503.0981.v1` CC-BY 4.0; ítem sin DOI (tercero) CC-BY 4.0;
  `10.1101/2024.06.03.24308405` (medRxiv) sin licencia abierta: abstract recortado a 1-2 frases
  (conserva `<jats:title>` y `<jats:p>`).

## `s2_paper_search.json`

- Capturada el 2026-10-20 (HTTP 200, sin clave) con
  `https://api.semanticscholar.org/graph/v1/paper/search?query=large+language+models+systematic+review+screening&limit=3&fields=title,abstract,year,externalIds,authors,url,openAccessPdf`.
  La API respondió 429 (cuota compartida sin clave) durante unos 40 minutos antes de esta captura.
- Recorte: se conservan `total`, `offset` y `data` (3 papers); se borró `next`.
- Edición: en el tercer paper se borró `externalIds.DOI`, para ejercitar el `record_id` de respaldo.
  El primer paper trae `openAccessPdf.url`.
- Licencias: paper 1 (`10.3390/info16050378`) CC-BY (`openAccessPdf.license: CCBY`);
  paper 2 (`10.1007/978-3-031-56027-9_25`, capítulo de Springer) sin licencia abierta: abstract
  recortado; paper 3 (arXiv `2510.16091`) sin licencia declarada en la respuesta: abstract recortado.
