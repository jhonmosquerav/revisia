"""Tests del puente motor↔config: carga y validación de protocol.yml."""

from __future__ import annotations

from pathlib import Path

from prisma_loop.config import load_protocol

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"


def test_plantilla_valida() -> None:
    protocol = load_protocol(TEMPLATE_DIR)
    assert protocol.slug == "_TEMPLATE"
    assert protocol.question.framework.value == "PICO"
    assert "OpenAlex" in protocol.databases
    assert protocol.rob_tool == "RoB2"


def test_autonomia_regla_dura() -> None:
    protocol = load_protocol(TEMPLATE_DIR)
    # screening/extracción/rob nunca superan A1.
    assert protocol.autonomy_for("extraccion") == "A0"
    assert protocol.autonomy_for("rob") == "A0"
    assert protocol.autonomy_for("screening_ta") == "A1"


def test_provider_cae_a_default() -> None:
    protocol = load_protocol(TEMPLATE_DIR)
    # 'busqueda' no tiene proveedor propio → usa 'default' (Gemini, neutral).
    assert protocol.provider_for("busqueda").provider == "gemini"
    # 'sintesis' sí tiene proveedor propio con su temperatura.
    assert protocol.provider_for("sintesis").temperature == 0.2
