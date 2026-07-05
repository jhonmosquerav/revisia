# El equipo de agentes de prisma-loop

`prisma-loop` es un sistema **multiagéntico mono-tarea**: cada etapa del
pipeline PRISMA la ejecuta un agente con una sola responsabilidad, un nivel de
autonomía explícito y una verificación posterior. Ningún agente decide solo en
etapas de juicio; la decisión final es siempre humana (Cochrane/JBI 2025).

## Niveles de autonomía (A0–A3)

| Nivel | Significado | Quién decide |
|---|---|---|
| **A0** | La IA solo prepara/estructura; el humano ejecuta el juicio | Humano |
| **A1** | La IA propone; el humano aprueba/edita en un checkpoint (HITL) | Humano |
| **A2** | La IA ejecuta sola tareas deterministas/reversibles y notifica | IA (auditada) |
| **A3** | Autonomía total | **No se otorga** en etapas de juicio |

La autonomía se configura **por etapa** en `protocol.yml` (`autonomy:`) con una
regla no negociable cableada en el diseño: `screening`, `extraccion` y `rob`
**nunca superan A1**.

## El equipo (una etapa, un agente)

| Agente | Etapa | Tipo | Autonomía por defecto | Verificación |
|---|---|---|---|---|
| `protocolo` | Preregistro del protocolo | 🧑 humano + plantillas | A0 | Firma humana; PRISMA-P (`protocolo-prisma-p.md`) |
| `busqueda` | Búsqueda multi-base (OpenAlex, Crossref, Semantic Scholar, Europe PMC + import RIS/BibTeX) | ⚙️ determinista | A2 | Cadenas versionadas (PRISMA-S); conteos al ledger |
| `dedup` | Deduplicación | ⚙️ determinista | A2 | Conteo de descartes trazado |
| `screening_ta` | Cribado título/abstract | 🤖 LLM (ensemble + voto pro-recall) | A1 | Gold humano → recall/lost-evidence/MCC/WMCC/κ; checkpoint HITL |
| `screening_ft` | Cribado a texto completo | 🤖 LLM | A0 | Decisión humana registro a registro |
| `extraccion` | Extracción de datos (+ doble extracción 20% con κ) | 🤖 LLM | A0 | Acuerdo entre extracciones; revisión campo a campo |
| `rob` | Riesgo de sesgo (RoB2/ROBINS-I/NOS/AMSTAR-2/QUADAS-2/GRADE) | 🤖 LLM propone | A0 | Juicio final del experto; export robvis |
| `meta-analisis` | Síntesis cuantitativa (IV fijo/aleatorio DL, Q/I²/τ², Egger, forest/funnel) | ⚙️ determinista | A2 | Solo corre si el protocolo aporta `effects.yml`; export metafor |
| `sintesis` | Síntesis narrativa (SWiM) | 🤖 LLM | A1 | **Verificador anti-alucinación** antes del gate humano |
| `verificador` | Grounding de citas contra el corpus | 🤖/⚙️ (embedder, agente o existencia) | A2 | Marca citas sin respaldo; bloquea la aprobación silenciosa |
| `reporte` | Entregable + checklists + flow diagram | ⚙️ determinista | A1 | Checkpoint final humano |
| `auditor` | Auditoría post-corrida (`prisma-loop audit`) | ⚙️ determinista | A2 | Verifica evidencia PRISMA 2020/-S/trAIce en disco; PASS/WARN/FAIL |
| `memoria` | Cerebro de investigador (`--brain`) | ⚙️ determinista | A2 | Solo informa (living review); **nunca** alimenta el juicio |

Tipos: ⚙️ determinista (sin LLM, reproducible bit a bit) · 🤖 LLM
(provider-agnostic, con `RunMeta` por llamada) · 🧑 humano.

## Las auditorías (defensa en profundidad)

1. **Verificador por etapa** — tras cada agente de razonamiento, el grounding
   comprueba citas contra el corpus ANTES del checkpoint humano.
2. **Checkpoints HITL** — el flujo se pausa por etapa; cada aprobación/edición
   queda en `decisions_ledger.jsonl` (actor, autonomía, acción, timestamp).
3. **Gold standard escalonado** — modelos ligeros criban → un modelo fuerte
   recomienda en zona gris → el humano valida → κ/recall del sistema contra ese
   gold (nunca "accuracy").
4. **Auditor post-corrida** — `prisma-loop audit runs/<slug>-<fecha>` verifica
   manifest, prompts hash-eados, supervisión humana, exclusiones IA/humano
   separadas (trAIce R1), gold, grounding, ventana de búsqueda y registro;
   emite `audit.md` con veredicto de publicabilidad.
5. **Manifiesto reproducible** — `manifest.yml` con modelo/versión/seed/hash de
   prompt por llamada: reproducibilidad "a nivel decisión" cuando el proveedor
   no garantiza determinismo a nivel token.

## Transparencia metodológica

Cada corrida emite su propia declaración de uso de IA:
`deliverable/checklist_traice.md` (ítems PRISMA-trAIce auto-rellenados desde la
procedencia real) + `deliverable/metodologia.md` (sección de métodos lista para
el manuscrito). Los fundamentos están en [`docs/metodologia/`](docs/metodologia/).
