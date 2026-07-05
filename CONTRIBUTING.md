# Contribuir a revisia

Gracias por tu interés. `revisia` es un sistema multiagéntico
**provider-agnostic** y reproducible para generar borradores de revisiones
sistemáticas bajo PRISMA 2020 + PRISMA-S + PRISMA-trAIce. Estas son las reglas
para contribuir.

## Principio rector (no negociable)

> **La IA es un acelerador, no un reemplazo.** Siguiendo la posición de la
> comunidad de síntesis de evidencia (Cochrane/JBI 2025), `revisia` mantiene
> **revisión humana obligatoria (HITL)** en cada etapa crítica. La decisión final
> es siempre humana.

Cualquier contribución que automatice una decisión metodológica saltándose el
checkpoint humano, o que suba la autonomía de screening/extracción/RoB por encima
de A1, será rechazada. El sistema acelera y documenta; no decide solo.

## Arquitectura: motor ↔ config

- `revisia/` es **el motor**: nunca contiene nada de una revisión concreta.
- Cada revisión vive en `protocols/<slug>/` y produce `runs/<slug>-<fecha>/`.

No mezcles datos de una revisión con el código del motor en un PR.

## Entorno de desarrollo

Requiere **Python 3.13+** y [`uv`](https://docs.astral.sh/uv/).

```bash
git clone <tu-fork> revisia && cd revisia
uv sync --extra dev          # instala el motor + herramientas de desarrollo
uv run pytest -q             # 49 tests, offline, sin API key
```

Los tests corren **sin credenciales** gracias al proveedor `fake` determinista.
No necesitas ninguna API key para desarrollar ni para correr la suite.

## Antes de abrir un PR

Tu rama debe pasar, en este orden:

```bash
uv run ruff check .          # linting
uv run black --check .       # formato (line-length 100)
uv run pytest -q             # todos los tests verdes
```

Pautas:

- **Tipos estrictos** y docstrings (estilo Google) en código nuevo.
- **Structured output** vía esquemas Pydantic en `revisia/schemas/`. No
  parsees texto libre del LLM a mano; define/extiende un esquema.
- **Prompts versionados**: viven en `revisia/prompts/<etapa>/vN.md` y se
  hashean en el manifiesto. Si cambias un prompt, sube la versión.
- **Proveedores**: para añadir uno nuevo, implementa el contrato
  `revisia/llm/base.py:LLMProvider`, regístralo en `llm/registry.py` y deja
  su SDK como *extra opcional* en `pyproject.toml` (import perezoso). El núcleo
  debe seguir importándose sin ese SDK.
- **Métricas**: nunca uses "accuracy" en datos desbalanceados; usa
  Recall/Lost-Evidence, MCC, WMCC, Cohen's kappa.
- **Nunca** subas `.env`, API keys, PDFs con copyright ni datos personales de
  terceros (ya están en `.gitignore`).

## Commits y ramas

- **Conventional Commits**: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`,
  `test:`.
- **Ramas**: `feat/<area>/<descripcion>`, p. ej. `feat/llm/anthropic-provider`.
- PRs pequeños y de responsabilidad única; describe el porqué, no solo el qué.

## Reportar bugs y proponer mejoras

Usa las plantillas de issue de GitHub. Para vulnerabilidades de seguridad,
sigue [`SECURITY.md`](SECURITY.md) — **no** abras un issue público.

## Licencia de tus contribuciones

Al contribuir aceptas que tu aporte se licencie bajo
[Apache-2.0](LICENSE), igual que el resto del proyecto.
