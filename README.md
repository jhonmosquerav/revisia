# prisma-loop

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-125%20passing-brightgreen.svg)](tests/)
[![PRISMA 2020](https://img.shields.io/badge/PRISMA-2020%20%2B%20S%20%2B%20trAIce-8A2BE2.svg)](#fundamento-metodológico)

**Sistema multiagéntico, provider-agnostic y reproducible para generar
borradores de revisiones sistemáticas bajo PRISMA 2020 + PRISMA-S +
PRISMA-trAIce.** Diseñado para que *cualquier* investigador lo clone, lo
configure con su propio proveedor de IA y produzca una revisión sistemática
trazable, auditable y abierta. Arranca con cualquier proveedor (Gemini por
defecto); incluye además un **driver de Claude Code** de primera clase que
razona con tu suscripción Max sin API key (ver
[Usar Claude Code](#usar-claude-code-driver-headless)).

> **La IA es un acelerador, no un reemplazo.** Siguiendo la posición de la
> comunidad de síntesis de evidencia (Cochrane/JBI 2025), `prisma-loop`
> mantiene **revisión humana obligatoria** (HITL) en cada etapa crítica:
> screening, extracción, riesgo de sesgo y síntesis. La decisión final es
> siempre humana. El sistema acelera y documenta; no decide solo.

## Qué hace

Automatiza, etapa por etapa, el proceso de una revisión sistemática:

```
protocolo →[✋]→ búsqueda multi-base → dedup → screening T/A (ensemble+voto) → verificador
  →[✋]→ screening full-text → verificador →[✋]→ extracción (+doble 20%) → verificador
  →[✋]→ riesgo de sesgo →[✋]→ meta-análisis (si hay efectos) + síntesis (SWiM)
  → verificador →[✋]→ reporte →[✋]→ export
```

- `[✋]` = **checkpoint humano** (HITL): el flujo se pausa y espera tu aprobación.
- `verificador` = paso de **auto-verificación anti-alucinación**: cada cita se
  comprueba contra el corpus recuperado antes de pedir tu revisión.

**Salida** (todo en `runs/<slug>-<fecha>/deliverable/`):

- `metodologia.md` · sección de métodos PRISMA + trAIce auto-rellenada
- `documento.md` · borrador de síntesis narrativa (SWiM)
- `meta_analisis.md` + `assets/forest.png`, `funnel.png` · síntesis cuantitativa
  (efectos fijos/aleatorios, I²/τ², Egger) **si el protocolo aporta `effects.yml`**
- `prisma_flow.md` · diagrama de flujo con la estructura de la **plantilla
  oficial** PRISMA 2020: desglose por base, exclusiones **humano vs IA**
  (nota ** oficial · trAIce R1) y **razones de exclusión** en elegibilidad;
  con `--brain` y memoria previa se emite además `prisma_flow_updated.md`
  (plantilla v3 · living review)
- `tabla_extraccion.md` · características de los estudios incluidos
- `risk_of_bias.md` · tabla de riesgo de sesgo
- `referencias.bib` · bibliografía BibTeX
- `checklist_2020.md` + `checklist_s.md` + `checklist_abstracts.md` +
  `checklist_traice.md` · checklists (27 ítems + PRISMA-S 16 ítems de
  búsqueda + 12 de resúmenes + uso de IA), pre-rellenados con la evidencia
  de la corrida
- `interop/` · exports para herramientas del ecosistema: `robvis.csv`,
  `effects_metafor.csv`, `prisma2020_flow.csv` (ver [`docs/integraciones.md`](docs/integraciones.md))

…todo con un **manifiesto reproducible** (modelo, versión, seed, prompts
hash-eados, exclusiones humano/IA, acuerdo de extracción, decisiones con timestamp).

Y al terminar, **audita la corrida** antes de usarla:

```bash
uv run prisma-loop audit runs/mi-revision-<fecha>
# ✅/⚠️/❌ por verificación (manifest, prompts, HITL, gold, grounding, registro…)
# → escribe runs/.../audit.md con el veredicto de publicabilidad
```

## Principios de diseño

| Principio | Cómo se implementa |
|---|---|
| **Provider-agnostic** | Capa LLM intercambiable por etapa en `protocol.yml`: Gemini (default), OpenAI, Anthropic, modelo local, o el driver de **Claude Code** (`claude -p` headless, suscripción Max, sin API key). El núcleo no depende de ningún proveedor concreto y arranca sin Claude Code instalado. |
| **Motor ↔ config** | El código (`prisma_loop/`) nunca contiene nada de una revisión concreta. Cada revisión vive en `protocols/<slug>/` y produce `runs/<slug>-<fecha>/`. |
| **Reproducible** | Cada llamada al LLM registra `RunMeta` (modelo, seed, temperatura, hash del prompt). El manifiesto permite que otro investigador reproduzca la cadena exacta. |
| **Defendible** | Métricas correctas (Recall/Lost-Evidence, MCC, WMCC — nunca "accuracy"); doble revisor; grounding de citas; PRISMA-trAIce nativo. |

## Quickstart (5 pasos)

```bash
# 1. Clonar e instalar (requiere Python 3.13+ y uv)
git clone https://github.com/jhonmosquerav/prisma-loop.git && cd prisma-loop
uv sync --extra demo

# 2. Configurar credenciales (solo tu proveedor)
cp .env.example .env   # edita .env y pon tu API key (default: Gemini, tier gratis)
#    ¿Usas Claude Code? No necesitas API key: ver "Usar Claude Code" más abajo.

# 3. Crear tu revisión (scaffold completo: protocol.yml + PRISMA-P + gold + cadenas)
uv run prisma-loop new mi-revision
#     edita protocols/mi-revision/protocol.yml y preregistra (PRISMA-P)

# 4. Ejecutar el pipeline (se pausa en cada checkpoint humano)
uv run prisma-loop run protocols/mi-revision --brain cerebro

# 5. Auditar la corrida antes de usarla (PASS/WARN/FAIL + publicabilidad)
uv run prisma-loop audit runs/mi-revision-<fecha>
```

Y cuando el manuscrito esté escrito, pre-chequea su adherencia al checklist:

```bash
uv run prisma-loop check manuscrito.md          # 27 ítems: ✅/🟡/❌ + evidencia
```

## Estado

**Completo · cobertura metodológica end-to-end.** Pipeline PRISMA
con HITL en todas las etapas; capa LLM provider-agnostic (Gemini /
OpenAI / Anthropic / local / **Claude Code** / `agent` / `fake`); **búsqueda multi-base**
(OpenAlex / Crossref / Semantic Scholar / **Europe PMC (MEDLINE/PubMed)** + import
RIS/BibTeX para Scopus/WoS);
**meta-análisis cuantitativo** (efectos fijos/aleatorios, I²/τ², Egger,
forest/funnel); doble extracción con kappa; exclusiones humano/IA y generación
de `metodologia.md`; **auditoría post-corrida** (`prisma-loop audit`);
**memoria de investigador** con living review (`--brain`); checklists 2020 +
resúmenes + trAIce; exports interoperables (robvis / metafor / PRISMA2020).
Métricas defendibles + verificador anti-alucinación.
**118 tests verdes** offline (sin API key ni CLI: el provider Claude Code se
testea con `subprocess` mockeado). Licencia Apache-2.0, `CITATION.cff` y
`.zenodo.json` listos para depósito en Zenodo.

## Equipo de agentes, autonomías y auditorías

Cada etapa la ejecuta un **agente mono-tarea** con nivel de autonomía explícito
(A0–A3, configurable por etapa en `protocol.yml`) y verificación posterior:
screening/extracción/RoB **nunca superan A1** (la IA propone, el humano decide).
La defensa en profundidad tiene cinco capas: verificador por etapa → checkpoints
HITL → gold standard con κ → **auditor post-corrida** → manifiesto reproducible.
El equipo completo, con tipos, autonomías y verificaciones, está declarado en
[`AGENTS.md`](AGENTS.md).

## Usar Claude Code (driver headless)

`prisma-loop` incluye un proveedor `claude_code` que delega el razonamiento en
**Claude Code en modo headless** (`claude -p --output-format json`): consume tu
suscripción Max, sin API key ni costo por token. Requiere
[Claude Code](https://claude.com/claude-code) instalado y con sesión iniciada.

**Auth de la suscripción (una sola vez).** El modo headless necesita un token de
larga duración. Acúñalo con tu cuenta Max/Pro y guárdalo en `.env`:

```bash
claude setup-token        # flujo OAuth en el navegador → imprime el token
echo "CLAUDE_CODE_OAUTH_TOKEN=<token>" >> .env   # el CLI lo usa para autenticar
```

> ⚠️ Un `claude -p` lanzado **dentro** de otra sesión de Claude Code no hereda la
> auth del host (el token vive en memoria del host, no en disco): sin
> `CLAUDE_CODE_OAUTH_TOKEN` propio devolverá 401. Si conduces prisma-loop desde
> dentro de un agente, usa el proveedor [`agent`](#usar-el-proveedor-agent-conducir-prisma-loop-en-proceso).

Para usarlo, pon en tu `protocol.yml`:

```yaml
llm:
  default:
    provider: claude_code
    model: sonnet      # screening masivo: rápido/barato; sube a 'opus' para más juicio
    temperature: 0.0
  sintesis:
    provider: claude_code
    model: opus
    temperature: 0.2
```

El `structured output` se resuelve inyectando el JSON Schema y validando con
Pydantic (con reintentos), ya que el CLI no fuerza *tool-use*. Como el CLI
headless no expone `seed`/`temperature` estables, la reproducibilidad queda a
nivel de decisión (ledger), no de token.

> **Windows / auth headless.** En Windows `claude` es un shim `.cmd`: el
> proveedor lo resuelve con `shutil.which`. Y si el `claude -p` headless no puede
> autenticar (p. ej. corriendo *dentro* de otra sesión de Claude Code, cuya
> sesión Max no es delegable a un subproceso), verás un 401 con remedios
> accionables. Para ese caso usa el proveedor `agent` (abajo).

## Usar el proveedor `agent` (conducir prisma-loop en proceso)

Cuando ya estás **dentro** de una sesión de agente (p. ej. Claude Code) y
quieres que ese agente sea el motor de razonamiento —sin API key ni `claude -p`
headless—, usa `provider: agent`. El agente *es* el modelo: inyectas un callback
y conduces el pipeline en proceso.

```yaml
llm:
  default: { provider: agent, model: sonnet, temperature: 0.0 }
  sintesis: { provider: agent, model: opus, temperature: 0.2 }
```

```python
from prisma_loop.agent_driver import run_review_with_agent

def reason(req, schema):
    # el agente lee req.prompt y devuelve un dict/objeto que cumple `schema`
    # (o un str si schema es None, para la síntesis de texto libre).
    ...

result = run_review_with_agent("protocols/mi-revision", reason, timestamp="...")
```

A diferencia de `claude_code`, no lanza ningún subproceso (evita el problema de
auth headless). En una corrida CLI desatendida `provider: agent` falla con un
error claro: no hay agente a quien delegar.

## Grounding sin vectores + cerebro de investigador (costo cero)

**Grounding por agente.** El verificador anti-alucinación puede juzgar el respaldo
de cada cita **sin embeddings**: un modelo decide si la fuente sustenta la
afirmación y devuelve la cita textual. Cruza idiomas (síntesis en español vs.
abstracts en inglés) donde la similitud léxica falla, y es gratis con
`provider: agent`. En `protocol.yml`:

```yaml
grounding: agent        # 'embedder' (default, coseno portátil) | 'agent' | 'existence'
```

**Cerebro de investigador (memoria persistente en markdown).** Con `--brain` cada
revisión se sedimenta en archivos portátiles (sin vectores ni servidores), siguiendo
el patrón de memoria del proyecto [cerebro](https://github.com/jhonmosquerav/cerebro)
(MIT), de modo que el conocimiento se **acumula y se consulta** entre corridas:

```bash
uv run prisma-loop run protocols/mi-revision --auto-approve --brain cerebro
# escribe cerebro/{genome/events.jsonl, wiki/semantic, wiki/episodic, raw, index.md}

uv run prisma-loop brain cerebro               # qué revisiones recuerda
uv run prisma-loop brain cerebro mi-revision   # memoria vigente de un tema
```

Si vuelves a correr un protocolo con memoria previa, la corrida se registra como
**actualización (living review)**: el episodio y el evento llevan el delta de
estudios incluidos (nuevos / retirados) respecto a la corrida anterior. La
memoria informa al investigador y al reporte; **nunca** se inyecta en el juicio
de screening/extracción/RoB (regla anti-sesgo). Ver
[`docs/memoria-cerebro.md`](docs/memoria-cerebro.md).

> Evolución opcional y gratuita: un índice vectorial **local** del cerebro con
> `FastEmbedEmbedder` (`uv add fastembed`, ONNX/CPU, multilingüe, offline) para
> recuperación semántica entre revisiones — sin API ni servidores.

## Defaults de buenas prácticas (cómo evitan las limitaciones típicas)

La plantilla `_TEMPLATE` y los guardrails de `validate` están calibrados para que
una RS no repita las limitaciones clásicas de una revisión rápida:

| Limitación típica | Default / guardrail que la mitiga |
|---|---|
| Pocas bases | **4 bases abiertas** por defecto (+ Europe PMC = MEDLINE/PubMed); `validate` avisa si hay <3. Scopus/WoS por import RIS/BibTeX |
| Un solo cribador / sin kappa | `ensemble` en `screening_ta`; `gold.yml` plantilla + `prisma-loop gold-template`; `validate` avisa si falta gold o ensemble |
| Volumen bajo | `--max` por defecto **50** por base |
| Sesgo de idioma | cadenas de ejemplo **EN/ES/PT** + `grounding: agent` (verificación cross-lingual) |
| Sesgo de modelo IA | `grounding: agent` (juicio cross-lingual) + ensemble multi-modelo + verificador |
| Sin metaanálisis | `effects.yml` → efectos fijos/aleatorios, I²/τ², Egger (cuando hay efectos poolables) |

Scopus/Web of Science **no** se automatizan (su licencia lo prohíbe): se incorporan
por export→import RIS/BibTeX desde la biblioteca de tu institución.

## Estructura

```
prisma_loop/          # EL MOTOR (paquete instalable · provider-agnostic)
  llm/                # capa de abstracción LLM + proveedores + ensemble
    providers/        #   gemini · openai · anthropic · local · claude_code · agent · fake
  rag/                # grounding / verificación anti-alucinación
  agents/             # un agente mono-tarea por etapa PRISMA
  schemas/            # structured output (Pydantic) por etapa
  exports/            # diagrama PRISMA, checklists 2020/abstracts/trAIce, interop OSS
  provenance/         # RunMeta + ledger append-only de decisiones
  orchestration/      # flujo Prefect + checkpoints HITL
  memory/             # cerebro de investigador (markdown + JSONL, living review)
  audit.py            # auditor post-corrida (PRISMA 2020 / -S / trAIce)
  prompts/            # prompts versionados y hash-eados
protocols/_TEMPLATE/  # LA CONFIG (una carpeta por revisión · default: gemini)
  protocolo-prisma-p.md  #   plantilla de preregistro (17 ítems PRISMA-P)
runs/                 # OUTPUTS reproducibles (una carpeta por ejecución)
docs/                 # metodología (KB de fuentes primarias), integraciones, memoria
examples/             # tracer bullet: revisión mini end-to-end (offline · fake)
tests/                # golden tests por etapa
AGENTS.md             # el equipo: agentes, autonomías A0-A3, auditorías
```

## Fundamento metodológico

`prisma-loop` automatiza un flujo de revisión sistemática canónico:
PICO/PEO/SPIDER · protocolo PRISMA-P · búsqueda PRISMA-S · screening doble ·
extracción · RoB2/ROBINS-I/GRADE · síntesis SWiM · checklist 27 ítems +
resúmenes · PRISMA-trAIce. Cada etapa del pipeline espeja un paso de ese método.

La **base de conocimiento** con las fuentes primarias (declaración PRISMA 2020,
checklists oficiales, las 4 plantillas del flow diagram, el catálogo de 20
extensiones y la extensión PRISMA-trAIce para reporte de IA) vive en
[`docs/metodologia/`](docs/metodologia/), extraída con licencias y atribución
declaradas — el sistema trabaja contra la norma, no contra recuerdos de la norma.

## Cómo citar

Si usas `prisma-loop` en tu investigación, cítalo con los metadatos de
[`CITATION.cff`](CITATION.cff). Tras el primer depósito en Zenodo habrá un DOI
citable (ver [`RELEASING.md`](RELEASING.md)).

## Contribuir

Las contribuciones son bienvenidas. Lee [`CONTRIBUTING.md`](CONTRIBUTING.md)
(entorno con `uv`, tests offline, Conventional Commits) y respeta el principio
no negociable: **la IA es un acelerador, no un reemplazo** (HITL en cada etapa).
Participa según el [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Seguridad

Para reportar vulnerabilidades o entender el manejo de credenciales y datos
sensibles, ver [`SECURITY.md`](SECURITY.md). **Nunca** commitees `.env` ni API keys.

## Licencia

[Apache-2.0](LICENSE) © 2026 Jhon Alexander Mosquera Vanegas. Ver también
[`NOTICE`](NOTICE).
