# Fixtures de red

Respuestas JSON **reales** de APIs públicas, recortadas a tres ítems, para probar los parsers
sin red (auditoría 2026-09-03, M18). Los metadatos bibliográficos de Crossref y Semantic Scholar
son reutilizables. No contienen correos ni claves.

## `crossref_works.json`

- Capturada el 2026-10-20 con
  `https://api.crossref.org/works?query=large+language+models+systematic+review+screening&rows=3&filter=has-abstract:true`
  (sin `mailto` en la URL guardada).
- Recorte: se conservan `status`, `message-type`, `message.total-results` y `message.items`;
  se borraron `message.facets` y `message.query` (y el resto de claves de `message`).
- Edición: en el tercer ítem se borró la clave `DOI`, para ejercitar el `record_id` de respaldo.

## `s2_paper_search.json`

- Capturada el 2026-10-20 (HTTP 200, sin clave) con
  `https://api.semanticscholar.org/graph/v1/paper/search?query=large+language+models+systematic+review+screening&limit=3&fields=title,abstract,year,externalIds,authors,url,openAccessPdf`.
  La API respondió 429 (cuota compartida sin clave) durante unos 40 minutos antes de esta captura.
- Recorte: se conservan `total`, `offset` y `data` (3 papers); se borró `next`.
- Edición: en el tercer paper se borró `externalIds.DOI`, para ejercitar el `record_id` de respaldo.
  El primer paper trae `openAccessPdf.url`.
