"""Tests del proveedor ``agent`` (razonamiento delegado al agente de la sesión).

Corren offline y sin red: el "agente" es un callback de prueba. Verifican el
structured output (dict / BaseModel / str), el texto libre, el ``RunMeta`` (no
determinista), el error accionable cuando no hay callback, y el alcance del
context manager.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from prisma_loop.llm import LLMProvider, ProviderConfig, build_provider
from prisma_loop.llm.base import LLMRequest
from prisma_loop.llm.providers import agent


class _Decision(BaseModel):
    include: bool
    reason: str


@pytest.fixture(autouse=True)
def _clear_callback():
    """Garantiza que ningún callback sobreviva entre tests."""
    agent.set_agent_callback(None)
    yield
    agent.set_agent_callback(None)


def _provider() -> agent.AgentProvider:
    return build_provider(ProviderConfig(provider="agent", model="opus"))  # type: ignore[return-value]


def test_se_construye_via_registry_y_cumple_protocolo() -> None:
    provider = _provider()
    assert provider.name == "agent"
    assert provider.model == "opus"
    assert isinstance(provider, LLMProvider)


def test_structured_acepta_dict_del_callback() -> None:
    def cb(req, schema):
        assert schema is _Decision
        return {"include": True, "reason": "cumple PEO"}

    with agent.use_agent_callback(cb):
        obj, meta = _provider().structured(LLMRequest(prompt="¿incluir?"), _Decision)

    assert isinstance(obj, _Decision)
    assert obj.include is True
    assert meta.provider == "agent"
    assert meta.deterministic is False


def test_structured_acepta_instancia_basemodel() -> None:
    def cb(req, schema):
        return _Decision(include=False, reason="fuera de alcance")

    with agent.use_agent_callback(cb):
        obj, _ = _provider().structured(LLMRequest(prompt="x"), _Decision)
    assert obj.include is False
    assert obj.reason == "fuera de alcance"


def test_structured_acepta_str_json_con_fences() -> None:
    def cb(req, schema):
        return '```json\n{"include": true, "reason": "ok"}\n```'

    with agent.use_agent_callback(cb):
        obj, _ = _provider().structured(LLMRequest(prompt="x"), _Decision)
    assert obj.include is True


def test_complete_devuelve_texto_libre() -> None:
    def cb(req, schema):
        assert schema is None
        return "Borrador de síntesis del agente."

    with agent.use_agent_callback(cb):
        resp = _provider().complete(LLMRequest(prompt="sintetiza"))
    assert resp.text == "Borrador de síntesis del agente."
    assert resp.meta.provider == "agent"


def test_sin_callback_da_error_accionable() -> None:
    with pytest.raises(RuntimeError, match="callback"):
        _provider().complete(LLMRequest(prompt="x"))


def test_salida_invalida_del_callback_falla() -> None:
    def cb(req, schema):
        return {"include": "no-es-bool"}  # falta reason + tipo inválido

    with agent.use_agent_callback(cb), pytest.raises(RuntimeError, match="_Decision"):
        _provider().structured(LLMRequest(prompt="x"), _Decision)


def test_context_manager_restaura_estado_previo() -> None:
    assert agent.get_agent_callback() is None
    with agent.use_agent_callback(lambda req, schema: "x"):
        assert agent.get_agent_callback() is not None
    assert agent.get_agent_callback() is None
