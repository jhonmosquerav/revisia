"""Tests del proveedor Claude Code (driver de referencia · Hito H5).

Mockean ``subprocess.run``: NO invocan el CLI real ``claude``, así que corren
offline en CI sin login Max ni red. Verifican el parseo del JSON de
``claude -p --output-format json``, el structured output por inyección de
schema + reintento, el ``RunMeta`` (no determinista) y los errores accionables.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from revisia.llm import LLMProvider, ProviderConfig, build_provider
from revisia.llm.base import LLMRequest
from revisia.llm.providers import claude_code as cc


class _Decision(BaseModel):
    include: bool
    reason: str


def _result_json(result_text: str, *, is_error: bool = False) -> str:
    """Fabrica la línea JSON que emite ``claude -p --output-format json``."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": is_error,
            "result": result_text,
            "session_id": "sess-test",
            "usage": {"input_tokens": 12, "output_tokens": 7},
            "modelUsage": {},
        }
    )


def _fake_run_factory(stdouts, recorder=None):
    """Devuelve un sustituto de ``subprocess.run`` que sirve ``stdouts`` en orden.

    Cada elemento de ``stdouts`` puede ser un str (stdout, returncode 0) o una
    excepción a lanzar. ``recorder`` (lista) acumula los ``cmd``/``input`` vistos.
    """
    calls = iter(stdouts)

    def _fake_run(cmd, **kwargs):
        if recorder is not None:
            recorder.append({"cmd": cmd, "input": kwargs.get("input"), "env": kwargs.get("env")})
        nxt = next(calls)
        if isinstance(nxt, BaseException):
            raise nxt
        return SimpleNamespace(returncode=0, stdout=nxt, stderr="")

    return _fake_run


def _provider() -> cc.ClaudeCodeProvider:
    return build_provider(ProviderConfig(provider="claude_code", model="sonnet"))  # type: ignore[return-value]


def test_claude_code_se_construye_y_cumple_protocolo() -> None:
    provider = _provider()
    assert provider.name == "claude_code"
    assert provider.model == "sonnet"
    assert isinstance(provider, LLMProvider)


def test_complete_parsea_result_y_tokens(monkeypatch) -> None:
    recorder: list[dict] = []
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("pong")], recorder))
    provider = _provider()
    resp = provider.complete(LLMRequest(prompt="di pong", system="eres conciso"))

    assert resp.text == "pong"
    assert resp.meta.provider == "claude_code"
    assert resp.meta.model == "sonnet"
    assert resp.meta.deterministic is False  # el CLI no expone seed/temperature
    assert resp.meta.input_tokens == 12
    assert resp.meta.output_tokens == 7

    # El prompt viaja por stdin; el system va como --append-system-prompt.
    cmd = recorder[0]["cmd"]
    assert recorder[0]["input"] == "di pong"
    assert "-p" in cmd and "--output-format" in cmd and "json" in cmd
    assert "--model" in cmd and "sonnet" in cmd
    assert "--append-system-prompt" in cmd and "eres conciso" in cmd


def test_structured_valida_aunque_venga_con_fences(monkeypatch) -> None:
    payload = "```json\n" + json.dumps({"include": True, "reason": "cumple PECO"}) + "\n```"
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json(payload)]))
    provider = _provider()
    obj, meta = provider.structured(LLMRequest(prompt="¿incluir?"), _Decision)

    assert isinstance(obj, _Decision)
    assert obj.include is True
    assert obj.reason == "cumple PECO"
    assert meta.deterministic is False


def test_structured_reintenta_tras_json_invalido(monkeypatch) -> None:
    good = _result_json(json.dumps({"include": False, "reason": "fuera de alcance"}))
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory([_result_json("no soy json"), good]),
    )
    provider = _provider()
    obj, _ = provider.structured(LLMRequest(prompt="¿incluir?"), _Decision)
    assert obj.include is False


def test_structured_agota_reintentos_y_falla(monkeypatch) -> None:
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory([_result_json("basura")] * 5),
    )
    provider = _provider()
    with pytest.raises(RuntimeError, match="JSON"):
        provider.structured(LLMRequest(prompt="x"), _Decision)


def test_error_de_api_es_accionable(monkeypatch) -> None:
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory([_result_json("API Error: 401", is_error=True)]),
    )
    provider = _provider()
    with pytest.raises(RuntimeError, match="401"):
        provider.complete(LLMRequest(prompt="x"))


def test_cli_ausente_da_error_accionable(monkeypatch) -> None:
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory([FileNotFoundError()]),
    )
    provider = _provider()
    with pytest.raises(RuntimeError, match="claude"):
        provider.complete(LLMRequest(prompt="x"))


def test_401_da_error_accionable_de_auth(monkeypatch) -> None:
    err = _result_json("Failed to authenticate. API Error: 401", is_error=True)
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([err]))
    with pytest.raises(RuntimeError, match="setup-token"):
        _provider().complete(LLMRequest(prompt="x"))


def test_token_de_suscripcion_se_propaga_al_subproceso(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-headless-123")
    recorder: list[dict] = []
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")], recorder))
    _provider().complete(LLMRequest(prompt="hola"))
    env = recorder[0]["env"]
    assert env is not None
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "tok-headless-123"


def test_clean_env_quita_overrides_de_endpoint_con_token(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-prod")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://staging.example/")
    monkeypatch.setenv("USE_STAGING_OAUTH", "true")
    recorder: list[dict] = []
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")], recorder))
    provider = cc.ClaudeCodeProvider(model="sonnet", clean_env=True)
    provider.complete(LLMRequest(prompt="x"))
    env = recorder[0]["env"]
    assert "ANTHROPIC_BASE_URL" not in env
    assert "USE_STAGING_OAUTH" not in env
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "tok-prod"


def test_sin_clean_env_conserva_el_entorno(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-prod")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://staging.example/")
    recorder: list[dict] = []
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")], recorder))
    provider = cc.ClaudeCodeProvider(model="sonnet", clean_env=False)
    provider.complete(LLMRequest(prompt="x"))
    assert recorder[0]["env"].get("ANTHROPIC_BASE_URL") == "https://staging.example/"
