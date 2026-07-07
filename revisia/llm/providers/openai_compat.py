"""Gateways remotos OpenAI-compatibles (Z.ai, OpenRouter) · panel multi-modelo.

Cualquier pasarela que exponga la API de chat de OpenAI sirve para armar un
panel de modelos heterogéneo — p. ej. el benchmark de sensibilidad del cribado
(``docs/benchmark-cribado.md``): **Z.ai** para la familia GLM y **OpenRouter**
como agregador (GPT / Gemini / … con una sola key). Reutilizan ``_OpenAIBase``
para ``complete`` y el ``structured`` por inyección de schema de
:class:`~revisia.llm.providers.local_openai.LocalOpenAIProvider` (máxima
compatibilidad: no todos los gateways implementan el ``json_schema`` estricto
de OpenAI).

A diferencia del endpoint local, estos servicios son remotos y autenticados:
la API key es obligatoria y su ausencia falla con un error accionable **antes**
de tocar la red o importar el SDK.
"""

from __future__ import annotations

import os
from typing import Any

from revisia.llm.providers.local_openai import LocalOpenAIProvider


class _RemoteOpenAICompat(LocalOpenAIProvider):
    """Base para gateways remotos: ``base_url`` propia y API key obligatoria."""

    env_base_url = ""
    default_base_url = ""

    def __init__(self, model: str) -> None:
        super().__init__(model)
        self.base_url = os.environ.get(self.env_base_url) or self.default_base_url

    def _client(self) -> Any:
        if not os.environ.get(self.env_key):
            raise RuntimeError(f"{self.env_key} no está definida en el entorno (ver .env.example).")
        return super()._client()


class ZaiProvider(_RemoteOpenAICompat):
    """Familia GLM vía Z.ai (endpoint OpenAI-compatible)."""

    name = "zai"
    env_key = "ZAI_API_KEY"
    env_base_url = "ZAI_BASE_URL"
    default_base_url = "https://api.z.ai/api/paas/v4"


class OpenRouterProvider(_RemoteOpenAICompat):
    """Agregador OpenRouter: GPT / Gemini / … con una sola API key."""

    name = "openrouter"
    env_key = "OPENROUTER_API_KEY"
    env_base_url = "OPENROUTER_BASE_URL"
    default_base_url = "https://openrouter.ai/api/v1"
