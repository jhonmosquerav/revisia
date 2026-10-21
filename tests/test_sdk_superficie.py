"""Superficie real de los SDK que imitan los clientes falsos (Tarea 7, D25, §19 fila 6).

Sin red ni claves reales: se construye el cliente con claves ficticias y solo se
comprueba que los métodos que usan los proveedores existen. El job ``sdk-smoke``
del CI fija ``REVISIA_SDK_SMOKE=1``: allí un SDK ausente es un error, no un salto.
Si una subida del lock rompe la superficie, el fallo es del proveedor (PR-A, §15):
marcar ese test ``xfail(strict=True, reason=...)`` con la causa, nunca borrarlo.
"""

from __future__ import annotations

import importlib
import os
from types import ModuleType

import pytest

from revisia.llm.base import LLMRequest
from revisia.llm.providers.anthropic_api import AnthropicProvider
from revisia.llm.providers.gemini import GeminiProvider
from revisia.llm.providers.local_openai import LocalOpenAIProvider
from revisia.llm.providers.openai_api import OpenAIProvider
from revisia.llm.providers.openai_compat import OpenRouterProvider, ZaiProvider

REQ = LLMRequest(prompt="¿Incluir?", system="Eres un cribador.", temperature=0.3, seed=42)

_CLAVES = (
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ZAI_API_KEY",
    "OPENROUTER_API_KEY",
)


def _sdk(nombre: str) -> ModuleType:
    try:
        return importlib.import_module(nombre)
    except ImportError:
        if os.environ.get("REVISIA_SDK_SMOKE") == "1":
            pytest.fail(f"SDK {nombre!r} ausente en el job sdk-smoke")
        pytest.skip(f"SDK {nombre!r} no instalado (extra opcional)")


@pytest.fixture(autouse=True)
def _claves_ficticias(monkeypatch: pytest.MonkeyPatch) -> None:
    for clave in _CLAVES:
        monkeypatch.setenv(clave, "clave-ficticia")


def test_superficie_gemini() -> None:
    _sdk("google.genai")
    proveedor = GeminiProvider("gemini-3.5-flash-lite")
    assert callable(proveedor._client().models.generate_content)
    config = proveedor._config(REQ)
    assert config.temperature == REQ.temperature
    assert config.seed == REQ.seed


def test_superficie_openai_y_compatibles() -> None:
    _sdk("openai")
    for clase in (OpenAIProvider, ZaiProvider, OpenRouterProvider, LocalOpenAIProvider):
        cliente = clase("modelo")._client()
        assert callable(cliente.chat.completions.create), clase.__name__
        assert callable(cliente.beta.chat.completions.parse), clase.__name__


def test_superficie_anthropic() -> None:
    _sdk("anthropic")
    assert callable(AnthropicProvider("claude-sonnet-5-5")._client().messages.create)
