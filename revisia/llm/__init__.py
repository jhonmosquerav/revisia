"""Capa LLM provider-agnostic: contrato, registro y proveedores."""

from __future__ import annotations

from revisia.llm.base import LLMProvider, LLMRequest, LLMResponse
from revisia.llm.registry import ProviderConfig, build_provider

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "ProviderConfig",
    "build_provider",
]
