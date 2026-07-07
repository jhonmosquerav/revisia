"""Tests del contrato LLM y el registro provider-agnostic.

No requieren credenciales ni SDKs: el proveedor Gemini se puede instanciar sin
``google-genai`` (el SDK solo se importa al llamar al modelo). Así verificamos
que el núcleo es provider-agnostic de verdad.
"""

from __future__ import annotations

import pytest

from revisia.llm import LLMProvider, ProviderConfig, build_provider
from revisia.llm.base import LLMRequest


def test_build_provider_desconocido_falla() -> None:
    with pytest.raises(ValueError, match="Proveedor desconocido"):
        build_provider(ProviderConfig(provider="inventado", model="x"))


def test_build_provider_gemini_sin_credenciales() -> None:
    # Instanciar NO debe requerir API key ni el SDK (carga perezosa).
    provider = build_provider(ProviderConfig(provider="gemini", model="gemini-2.0-flash"))
    assert provider.name == "gemini"
    assert provider.model == "gemini-2.0-flash"


def test_gemini_cumple_el_protocolo() -> None:
    provider = build_provider(ProviderConfig(provider="gemini", model="m"))
    assert isinstance(provider, LLMProvider)


def test_openai_local_y_anthropic_se_construyen_offline() -> None:
    # Construcción perezosa sin SDK ni credenciales (el SDK se importa al llamar).
    openai = build_provider(ProviderConfig(provider="openai", model="gpt-4o-mini"))
    assert openai.name == "openai"
    assert isinstance(openai, LLMProvider)

    local = build_provider(ProviderConfig(provider="local_openai", model="llama3"))
    assert local.name == "local_openai"
    assert local.base_url  # apunta a un endpoint local por defecto
    assert isinstance(local, LLMProvider)

    anthropic = build_provider(ProviderConfig(provider="anthropic", model="claude-opus-4-8"))
    assert anthropic.name == "anthropic"
    assert anthropic.model == "claude-opus-4-8"
    assert isinstance(anthropic, LLMProvider)


def test_zai_y_openrouter_se_construyen_offline() -> None:
    # Gateways OpenAI-compatibles del panel multi-modelo (benchmark de cribado):
    # se instancian sin SDK ni credenciales (carga perezosa).
    zai = build_provider(ProviderConfig(provider="zai", model="glm-5.2"))
    assert zai.name == "zai"
    assert "z.ai" in zai.base_url
    assert isinstance(zai, LLMProvider)

    router = build_provider(ProviderConfig(provider="openrouter", model="openai/gpt-5"))
    assert router.name == "openrouter"
    assert "openrouter.ai" in router.base_url
    assert isinstance(router, LLMProvider)


def test_zai_respeta_base_url_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    # P. ej. el endpoint del plan de suscripción (coding plan) de Z.ai.
    monkeypatch.setenv("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
    zai = build_provider(ProviderConfig(provider="zai", model="glm-5-turbo"))
    assert zai.base_url == "https://api.z.ai/api/coding/paas/v4"


def test_gateways_remotos_exigen_su_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # A diferencia del endpoint local, un gateway remoto de pago sin API key
    # debe fallar con un error accionable ANTES de tocar la red o el SDK.
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    zai = build_provider(ProviderConfig(provider="zai", model="glm-5.2"))
    with pytest.raises(RuntimeError, match="ZAI_API_KEY"):
        zai.complete(LLMRequest(prompt="hola"))
    router = build_provider(ProviderConfig(provider="openrouter", model="openai/gpt-5"))
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        router.complete(LLMRequest(prompt="hola"))


def test_claude_code_se_construye_offline() -> None:
    # Driver de referencia (H5 ✅): se instancia sin invocar el CLI ni requerir
    # login Max; la llamada real a `claude` solo ocurre en complete/structured.
    provider = build_provider(ProviderConfig(provider="claude_code", model="sonnet"))
    assert provider.name == "claude_code"
    assert provider.model == "sonnet"
    assert isinstance(provider, LLMProvider)
