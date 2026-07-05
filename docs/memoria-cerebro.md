# Memoria de investigador · patrón "cerebro"

`prisma-loop` incluye una memoria persistente **en archivos** (markdown + JSONL)
que acumula conocimiento entre revisiones: el **cerebro de investigador**
(`prisma_loop.memory.ResearchBrain`, bandera `--brain`).

## Patrón declarado (upstream)

La estructura sigue el patrón de memoria del proyecto
[**cerebro**](https://github.com/jhonmosquerav/cerebro) (licencia MIT):
documentación agéntica como "cerebro vivo" en markdown, **sin RAG, sin
vectores y sin servidores**. `prisma-loop` implementa el subconjunto que una
revisión sistemática necesita:

| Capa cerebro (upstream) | En prisma-loop | Contenido |
|---|---|---|
| `genome/events.jsonl` | ✅ igual | log append-only: un evento por corrida (conteos, incluidos, modelos, delta) |
| `wiki/semantic/` | ✅ igual | síntesis **vigente** por revisión (se sobrescribe en cada corrida) |
| `wiki/episodic/` | ✅ igual | un episodio **inmutable** por corrida concreta |
| `raw/` | ✅ igual | estudios incluidos + extracción, capa cruda inmutable |
| `index.md` | ✅ igual | índice navegable de todas las revisiones |
| `wiki/working/`, `wiki/procedural/`, `onboard/`, `audit/` | ➖ no aplica (v1) | capas de operación empresarial del upstream |

Las páginas de `wiki/` llevan **frontmatter YAML** (compatible con
Obsidian/Dataview), como exige el patrón upstream.

## Operaciones

| Operación | Comando | Qué hace |
|---|---|---|
| Sedimentar (INGEST) | `prisma-loop run <protocolo> --brain <carpeta>` | al terminar la corrida, escribe evento + semantic + episodic + raw + index |
| Consultar (QUERY) | `prisma-loop brain <carpeta>` | lista las revisiones conocidas y sus corridas |
| Consultar un tema | `prisma-loop brain <carpeta> <slug>` | memoria vigente del slug: corridas, conteos, síntesis |
| Recall programático | `ResearchBrain(root).recall(slug)` | `BrainRecall` con síntesis previa, incluidos y última corrida |

## Living review (actualización de revisiones)

Si corres de nuevo un protocolo cuyo `slug` ya tiene memoria:

1. Al arrancar, el CLI avisa: *"Memoria previa: N corridas, última X…"*.
2. Al sedimentar, el evento y el episodio registran el **delta** respecto a la
   corrida anterior: `included_new` (estudios que entran) e
   `included_dropped` (estudios que salen).
3. El episodio narra la actualización en la sección
   *"Actualización de revisión previa (living review)"*.

Esto documenta la evolución de la evidencia entre corridas — la mecánica de una
**living systematic review** — sin tocar el juicio de elegibilidad.

## Regla anti-sesgo (no negociable)

La memoria **nunca se inyecta en las etapas de juicio** (screening, extracción,
riesgo de sesgo): un cribador —humano o IA— que "recuerda" qué se incluyó antes
ancla sus decisiones y compromete la independencia del cribado. El cerebro
informa **al investigador humano** (antes de correr) y **al reporte** (después
de correr); no alimenta prompts de decisión. Si algún flujo futuro quisiera
usarla como contexto, debe declararlo en el protocolo y reportarlo bajo
PRISMA-trAIce (ítem de supervisión humana).

## Evolución opcional (apagada por defecto)

Para recuperación semántica entre revisiones (muchos slugs), existe un enganche
local y gratuito: `FastEmbedEmbedder` (`uv add fastembed`, ONNX/CPU,
multilingüe, offline). No cambia el formato de archivos; solo añade un índice.
