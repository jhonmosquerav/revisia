"""Errores de llamada y `prompt_template` del contrato LLM (spec 2026-10-18 §4.4, D9)."""

from __future__ import annotations

import dataclasses

import pytest

from revisia.llm.base import DeterministicCallError, LLMRequest, TransientCallError


def test_los_errores_de_llamada_son_runtime_error_y_distintos_entre_si() -> None:
    # Subclases de RuntimeError: el código de la Ola 1 que atrapa RuntimeError (rc 3) sigue
    # atrapándolos; distintos entre sí para que D9 pueda separar «reanudar» de «al humano».
    assert issubclass(TransientCallError, RuntimeError)
    assert issubclass(DeterministicCallError, RuntimeError)
    assert not issubclass(DeterministicCallError, TransientCallError)
    assert not issubclass(TransientCallError, DeterministicCallError)


def test_deterministic_call_error_lleva_los_intentos() -> None:
    exc = DeterministicCallError("salida inválida", attempts=3)
    assert str(exc) == "salida inválida"
    assert exc.attempts == 3
    assert DeterministicCallError("400").attempts == 1


def test_llm_request_admite_prompt_template_y_sigue_siendo_inmutable() -> None:
    req = LLMRequest(prompt="p")
    assert req.prompt_template is None
    con = dataclasses.replace(req, prompt_template="extraccion/v2.md")
    assert con.prompt_template == "extraccion/v2.md"
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.prompt_template = "x"  # type: ignore[misc]
