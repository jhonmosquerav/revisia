"""Modelos retirados por su proveedor (auditoría 2026-09-03, C4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

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
