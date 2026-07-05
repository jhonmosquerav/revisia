"""Carga de prompts versionados (fuente única de verdad).

Los prompts viven como ``prompts/<agente>/<version>.md`` y NO en el código, de
modo que se versionan, se revisan y su hash queda en el ``RunMeta`` de cada
llamada (auditabilidad PRISMA-trAIce). Usan marcadores ``{nombre}`` de
``str.format``; por eso las plantillas no contienen llaves literales.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(agent: str, version: str = "v1") -> str:
    """Devuelve el texto de ``prompts/<agent>/<version>.md``."""
    path = _PROMPTS_DIR / agent / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"No existe el prompt {agent}/{version}.md en {path}.")
    return path.read_text(encoding="utf-8")
