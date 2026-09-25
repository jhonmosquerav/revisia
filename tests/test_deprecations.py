"""Modelos retirados por su proveedor (auditoría 2026-09-03, C4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from revisia.config import load_protocol
from revisia.llm.deprecations import RETIRED_MODELS, Retirement, retirement_for
from revisia.llm.providers.gemini import DEFAULT_MODEL

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"


def test_gemini_2_0_flash_esta_retirado() -> None:
    r = retirement_for("gemini-2.0-flash")
    assert r == Retirement("gemini-2.0-flash", date(2026, 6, 1))
    assert r.is_past(date(2026, 6, 1))
    assert not r.is_past(date(2026, 5, 31))


def test_modelo_desconocido_no_esta_retirado() -> None:
    assert retirement_for("gemini-3.5-flash-lite") is None
    assert retirement_for("sonnet") is None


def test_default_gemini_no_esta_retirado() -> None:
    assert DEFAULT_MODEL == "gemini-3.5-flash-lite"
    assert retirement_for(DEFAULT_MODEL) is None


def test_plantilla_no_usa_modelos_retirados() -> None:
    protocol = load_protocol(TEMPLATE_DIR)
    assert all(retirement_for(cfg.model) is None for cfg in protocol.llm.values())


def test_lista_de_retirados_bien_formada() -> None:
    assert RETIRED_MODELS
    assert all(isinstance(d, date) for d in RETIRED_MODELS.values())


@pytest.mark.parametrize(
    "model",
    [
        "models/gemini-2.0-flash",  # nombre de recurso de la API de Gemini
        "google/gemini-2.0-flash-001",  # OpenRouter
        "google/gemini-2.0-flash-001:free",  # OpenRouter, variante gratuita
        "publishers/google/models/gemini-2.5-pro",  # Vertex AI
        "Gemini-2.0-Flash",  # mayúsculas
    ],
)
def test_retirado_con_prefijo_o_variante(model: str) -> None:
    # Seguimiento de la Ola 0: la tabla comparaba el id exacto y un id con
    # prefijo de proveedor o variante `:tag` se colaba.
    r = retirement_for(model)
    assert r is not None
    assert r.model == model  # el mensaje muestra el id tal como está en protocol.yml


@pytest.mark.parametrize(
    "model",
    ["gemini-3.5-flash-lite", "google/gemini-3.5-flash-lite:free", "llama3.1:8b", "openai/gpt-5"],
)
def test_vigente_con_prefijo_no_se_marca(model: str) -> None:
    assert retirement_for(model) is None
