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
        "publishers/google/models/gemini-2.0-flash",  # Vertex AI
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


@pytest.mark.parametrize("model", ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"])
def test_sin_fecha_oficial_no_se_marca_como_retirado(model: str) -> None:
    # La página de deprecaciones de la Gemini API (consultada 2026-09-28) dice
    # "No shutdown date announced" para estos ids. El 2026-10-16 que llegó a la
    # tabla se anunció en julio y luego se retiró de esa página; en Vertex AI es
    # un "no antes de". Marcarlo haría fallar `validate`/`run` con protocolos
    # que funcionan.
    assert retirement_for(model) is None


@pytest.mark.parametrize(
    ("model", "apagado"),
    [
        ("gemini-2.5-pro-preview-06-05", date(2025, 12, 2)),
        ("gemini-2.5-flash-preview-05-20", date(2025, 11, 18)),
        ("gemini-2.5-flash-lite-preview-09-2025", date(2026, 3, 31)),
        ("gemini-2.0-flash-lite-preview-02-05", date(2025, 12, 9)),
        ("gemini-3.1-flash-lite", date(2027, 5, 7)),
    ],
)
def test_fechas_de_la_pagina_oficial(model: str, apagado: date) -> None:
    r = retirement_for(model)
    assert r is not None
    assert r.shutdown == apagado
