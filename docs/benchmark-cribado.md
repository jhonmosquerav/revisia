# Benchmark de sensibilidad del cribado (panel multi-modelo)

> **Aviso de procedencia (auditoría 2026-09-03).** Las cifras del artículo
> fundacional que se citan abajo (sensibilidad 0,820, I² = 90,7 %) provienen
> de la corrida `runs/prisma-ia-origen-20260706-080747`, que la auditoría
> identificó como una **reconstrucción ilustrativa**, no una ejecución del
> pipeline tal como está en el repositorio: su manifiesto registra 140 llamadas
> IA en 1,3 ms, el ledger tiene marcas de tiempo escritas a mano y faltan las
> etapas intermedias. Además, su `effects.yml` agrega 27 de 28 efectos de un
> mismo artículo (nueve modelos sobre tres corpus), lo que viola la
> independencia entre estudios. **Estas cifras deben leerse como ilustración
> del diseño, no como evidencia**, hasta que el benchmark se regenere con el
> pipeline real y un meta-análisis por subgrupos (corpus → modelo) sin
> duplicados. Detalle en `docs/auditoria/2026-09-03-auditoria-completa.md`.

El hallazgo central del artículo fundacional de RevisIA es que **no existe un
número único de "qué tan bueno es el cribado por LLM"**: la sensibilidad
agregada fue 0,820 pero con heterogeneidad extrema (I² = 90,7%) — el desempeño
es una propiedad de *este modelo* sobre *este corpus*. La regla operativa que
se deriva es: **elegir el modelo con evidencia y validarlo en el corpus propio
contra un gold humano**. Este documento describe cómo instanciar esa regla con
RevisIA: un benchmark reproducible de la sensibilidad del cribado
título/abstract, modelo por modelo, sobre el mismo protocolo.

El benchmark es un **estudio independiente que consume RevisIA**: el motor no
privilegia ningún proveedor (capa provider-agnostic) y sus resultados pueden
alimentar una actualización del artículo como living review (`--brain`).

## Diseño

1. **Protocolo fijo.** Un solo `protocol.yml` para todo el panel. Para
   eliminar la variación de búsqueda entre corridas, congela el corpus: usa la
   misma ventana y bases, o importa un corpus fijo por RIS/BibTeX.
2. **Gold humano.** Genera la plantilla con `revisia gold-template <run_dir>`,
   etiqueta cada registro (true/false) y guárdala como `gold.yml` en la
   carpeta del protocolo. Es el estándar de referencia de TODAS las corridas.
3. **Una corrida por modelo.** Cambia solo el bloque `llm.screening_ta`
   (proveedor y modelo), `temperature: 0.0`, y **sin ensemble** (el ensemble
   mide al comité, no al modelo). Autonomía del cribado en A1, como siempre.
4. **Métricas contra el gold.** El motor las emite en
   `runs/<slug>-<fecha>/03_screening/metrics.json`: recall (sensibilidad),
   lost-evidence, MCC, WMCC y kappa. No se reporta "accuracy" a secas.
5. **Repeticiones.** Si el proveedor no es determinista
   (`RunMeta.deterministic = false`), corre n ≥ 3 réplicas por modelo y
   reporta la variabilidad, no solo el punto.
6. **Reporte.** Tabla modelo × (recall, lost-evidence, MCC, κ) y, si agregas
   proporciones, forest con `revisia.meta_analysis` (display=proportion).
   Declara cada modelo bajo PRISMA-trAIce: el manifest ya registra `RunMeta`
   por llamada (modelo, versión, seed, temperatura, hashes).

## Panel de referencia (frontera 2026 · configuración de ejemplo)

| Modelo | Proveedor RevisIA | Credenciales |
|---|---|---|
| Claude Opus 4.8 | `agent` o `claude_code` | suscripción Claude (sin API key) |
| Claude Sonnet | `agent` o `claude_code` | suscripción Claude (sin API key) |
| Claude Haiku | `agent` o `claude_code` | suscripción Claude (sin API key) |
| GLM-5.2 | `zai` | `ZAI_API_KEY` (API o plan de suscripción Z.ai) |
| GLM-5-Turbo | `zai` | `ZAI_API_KEY` |
| GPT-5 | `openrouter` (o `openai`) | `OPENROUTER_API_KEY` (o `OPENAI_API_KEY`) |
| Gemini 2.5 | `openrouter` (o `gemini`) | `OPENROUTER_API_KEY` (o `GEMINI_API_KEY`) |

El panel es abierto: cualquier endpoint OpenAI-compatible entra vía `zai`,
`openrouter` o `local_openai` sin tocar código del motor (modelos locales
incluidos, para líneas base de costo cero).

## Cómo correr una celda del panel

```yaml
# protocols/<slug>/protocol.yml · solo cambia este bloque entre corridas
llm:
  screening_ta:
    provider: zai        # agent | claude_code | zai | openrouter | openai | gemini | …
    model: glm-5.2
    temperature: 0.0
```

```bash
uv sync --extra zai            # o --extra openrouter / anthropic / gemini …
cp .env.example .env           # rellena SOLO la key del proveedor de la celda
uv run revisia run protocols/<slug>        # cribado A1: revisa la cola HITL
uv run revisia audit runs/<slug>-<fecha>   # PASS/WARN/FAIL antes de usarla
# métricas vs gold → runs/<slug>-<fecha>/03_screening/metrics.json
```

Al terminar el panel, exporta cada corrida como documento único si quieres
compartir los entregables: `uv run revisia export runs/<slug>-<fecha>`.
