"""Registro de proveedores LLM · resuelve el proveedor desde la config.

Lee un bloque ``llm`` (por etapa) de ``protocol.yml`` y devuelve una instancia
del proveedor adecuado. Los módulos de proveedor se importan de forma
**perezosa**: importar ``revisia`` NO requiere tener instalado ningún SDK
ni Claude Code; solo se importa el proveedor que la config pide. Si el SDK no
está instalado, el error es explícito y accionable.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from revisia.llm.base import LLMProvider

# nombre lógico → (módulo, clase). Carga perezosa: el módulo solo se importa
# cuando la config lo solicita.
_BUILDERS: dict[str, tuple[str, str]] = {
    "gemini": ("revisia.llm.providers.gemini", "GeminiProvider"),
    "openai": ("revisia.llm.providers.openai_api", "OpenAIProvider"),
    "anthropic": ("revisia.llm.providers.anthropic_api", "AnthropicProvider"),
    "local_openai": ("revisia.llm.providers.local_openai", "LocalOpenAIProvider"),
    "claude_code": ("revisia.llm.providers.claude_code", "ClaudeCodeProvider"),
    "agent": ("revisia.llm.providers.agent", "AgentProvider"),
    "fake": ("revisia.llm.providers.fake", "FakeProvider"),
}


class ProviderConfig(BaseModel):
    """Config de proveedor para una etapa (subbloque ``llm`` de protocol.yml).

    Attributes:
        provider: nombre lógico del proveedor (clave de ``_BUILDERS``).
        model: nombre del modelo a usar.
        temperature: temperatura por defecto de la etapa.
        top_p: nucleus sampling opcional.
        seed: semilla para reproducibilidad (si el proveedor la soporta).
    """

    provider: str
    model: str
    temperature: float = 0.0
    top_p: float | None = None
    seed: int | None = None


def available_providers() -> list[str]:
    """Lista de nombres lógicos de proveedor reconocidos."""
    return sorted(_BUILDERS)


def build_provider(cfg: ProviderConfig) -> LLMProvider:
    """Instancia el proveedor descrito por ``cfg`` (import perezoso).

    Raises:
        ValueError: si el nombre de proveedor no está registrado.
        RuntimeError: si el SDK del proveedor no está instalado.
    """
    if cfg.provider not in _BUILDERS:
        raise ValueError(
            f"Proveedor desconocido: {cfg.provider!r}. "
            f"Disponibles: {', '.join(available_providers())}."
        )
    module_path, class_name = _BUILDERS[cfg.provider]
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:  # SDK del proveedor no instalado
        raise RuntimeError(
            f"El proveedor {cfg.provider!r} requiere una dependencia no instalada. "
            f"Instala el extra correspondiente, p. ej. `uv sync --extra {cfg.provider}`. "
            f"Detalle: {exc}"
        ) from exc
    provider_cls = getattr(module, class_name)
    return provider_cls(model=cfg.model)
