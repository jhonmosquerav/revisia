# prisma-loop

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-84%20passing-brightgreen.svg)](tests/)
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
- `prisma_flow.md` · diagrama de flujo PRISMA 2020
- `tabla_extraccion.md` · características de los estudios incluidos
- `risk_of_bias.md` · tabla de riesgo de sesgo
- `referencias.bib` · bibliografía BibTeX
- `checklist_2020.md` + `checklist_traice.md` · checklists (27 ítems + uso de IA)

…todo con un **manifiesto reproducible** (modelo, versión, seed, prompts
hash-eados, exclusiones humano/IA, acuerdo de extracción, decisiones con timestamp).

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

# 3. Crear tu revisión a partir de la plantilla
cp -r protocols/_TEMPLATE protocols/mi-revision
#     edita protocols/mi-revision/protocol.yml

# 4. Ejecutar el pipeline (se pausa en cada checkpoint humano)
uv run prisma-loop run protocols/mi-revision

# 5. Revisar y aprobar en cada checkpoint; al final se exporta el
#    entregable + checklists + diagrama a runs/mi-revision-<fecha>/
```

## Estado

**Completo (H0–H5) · cobertura metodológica completa.** Pipeline PRISMA
end-to-end con HITL en todas las etapas; capa LLM provider-agnostic (Gemini /
OpenAI / Anthropic / local / **Claude Code** / `agent` / `fake`); **búsqueda multi-base**
(OpenAlex / Crossref / Semantic Scholar / **Europe PMC (MEDLINE/PubMed)** + import
RIS/BibTeX para Scopus/WoS);
**meta-análisis cuantitativo** (efectos fijos/aleatorios, I²/τ², Egger,
forest/funnel); doble extracción con kappa; exclusiones humano/IA y generación
de `metodologia.md`. Métricas defendibles + verificador anti-alucinación.
**84 tests verdes** offline (sin API key ni CLI: el provider Claude Code se
testea con `subprocess` mockeado). Licencia Apache-2.0, `CITATION.cff` y
`.zenodo.json` listos para depósito en Zenodo.

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
revisión se sedimenta en archivos portátiles (sin vectores ni servidores), de modo
que el conocimiento se acumula entre corridas:

```bash
uv run prisma-loop run protocols/mi-revision --auto-approve --brain cerebro
# escribe cerebro/{genome/events.jsonl, wiki/semantic, wiki/episodic, raw, index.md}
```

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
  exports/            # diagrama PRISMA, checklists 2020/trAIce, bibliografía
  provenance/         # RunMeta + ledger append-only de decisiones
  orchestration/      # flujo Prefect + checkpoints HITL
  prompts/            # prompts versionados y hash-eados
protocols/_TEMPLATE/  # LA CONFIG (una carpeta por revisión · default: gemini)
runs/                 # OUTPUTS reproducibles (una carpeta por ejecución)
examples/             # tracer bullet: revisión mini end-to-end (offline · fake)
tests/                # golden tests por etapa
```

## Fundamento metodológico

`prisma-loop` automatiza un flujo de revisión sistemática canónico:
PICO/PEO/SPIDER · búsqueda PRISMA-S · screening doble · extracción ·
RoB2/ROBINS-I/GRADE · síntesis SWiM · checklist 27 ítems · PRISMA-trAIce.
Cada etapa del pipeline espeja un paso de ese método.

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
