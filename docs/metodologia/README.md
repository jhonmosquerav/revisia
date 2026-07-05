# Base de conocimiento metodológica

Fuentes primarias que fundamentan el diseño de `prisma-loop`, extraídas a
markdown para que el sistema (y quien lo audite) trabaje **contra la norma, no
contra recuerdos de la norma**. Cada archivo lleva frontmatter con fuente,
licencia y fecha de consulta.

| Archivo | Fuente | Naturaleza | Qué aporta al sistema |
|---|---|---|---|
| [`prisma-2020-declaracion.md`](prisma-2020-declaracion.md) | Page et al., BMJ 2021;372:n71 (trad. oficial Rev Esp Cardiol, CC BY-NC-ND — contenido parafraseado) | Declaración oficial · peer-reviewed | Los 27 ítems (42 con sub-ítems) + 12 de resúmenes, novedades vs 2009, mapeo ítem→automatización |
| [`prisma-2020-recursos-oficiales.md`](prisma-2020-recursos-oficiales.md) | prisma-statement.org (CC BY 4.0) | Sitio oficial | Checklists verbatim EN + trad. ES, 4 plantillas del flow diagram con sus cajas/conteos, 20 extensiones publicadas + 11 en desarrollo, herramientas oficiales |
| [`prisma-traice.md`](prisma-traice.md) | Holst et al., JMIR AI 2025;4:e80247 · PMC12694947 (CC BY) | Extensión · peer-reviewed · **guía viva** ([repo](https://github.com/cqh4046/PRISMA-trAIce), MIT) | Los 17 ítems (T1, A1, I1, M1–M10, R1–R2, D1–D2) para reportar IA como herramienta metodológica; extracción doble-independiente convergente |
| [`panorama-ia-rs-no-revisado.md`](panorama-ia-rs-no-revisado.md) | Blog comercial (ProofreaderPro) | **No revisado por pares** — usar con cautela | Flujo de 10 pasos IA+PRISMA, gate de calibración κ≥0,7, plantillas de divulgación; afirmaciones cuantitativas marcadas como no verificadas |

## Cómo se usa esta base

- El **checklist trAIce** que emite cada corrida (`deliverable/checklist_traice.md`)
  responde a los ítems de `prisma-traice.md`; la auditoría (`prisma-loop audit`)
  verifica la evidencia de los ítems automatizables.
- Los **checklists 2020 y de resúmenes** que emite el pipeline siguen la
  numeración de `prisma-2020-declaracion.md`.
- El **diagrama de flujo** sigue la plantilla "nuevas revisiones, solo bases de
  datos" de `prisma-2020-recursos-oficiales.md` (con desglose de exclusiones
  humano/IA que exige trAIce R1).
- Las extensiones (`PRISMA-ScR`, `-DTA`, `-NMA`, …) listadas en la KB oficial son
  el catálogo de valores válidos para `prisma_extension` en `protocol.yml`.

> Nota de licencias: la traducción española de la declaración es CC BY-NC-ND,
> por eso ese archivo **parafrasea** (no reproduce) la tabla traducida; los
> materiales del sitio oficial son CC BY 4.0 y trAIce es CC BY, ambos citados
> con atribución completa.
