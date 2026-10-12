"""Tests del puente motor↔config: carga y validación de protocol.yml."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from revisia.config import ReviewProtocol, load_protocol

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


def _template_raw() -> dict:
    raw = yaml.safe_load((TEMPLATE_DIR / "protocol.yml").read_text(encoding="utf-8"))
    raw["slug"] = "demo"
    return raw


def test_effort_por_etapa_se_carga_desde_protocolo() -> None:
    raw = _template_raw()
    raw["llm"]["screening_ta"] = {"provider": "claude_code", "model": "sonnet", "effort": "low"}
    protocol = ReviewProtocol.model_validate(raw)
    assert protocol.provider_for("screening_ta").effort == "low"
    assert protocol.provider_for("busqueda").effort is None


@pytest.mark.parametrize("stage", ["screening_ta", "screening_ft", "extraccion", "rob"])
@pytest.mark.parametrize("level", ["A2", "A3"])
def test_autonomy_a3_in_judgement_stage_rejected(stage: str, level: str) -> None:
    raw = _template_raw()
    raw["autonomy"][stage] = level
    with pytest.raises(ValidationError, match="nunca superan A1"):
        ReviewProtocol.model_validate(raw)


def test_autonomy_nivel_invalido_rechazado() -> None:
    raw = _template_raw()
    raw["autonomy"]["busqueda"] = "A5"
    with pytest.raises(ValidationError, match="inválido"):
        ReviewProtocol.model_validate(raw)


def test_autonomy_etapa_desconocida_rechazada() -> None:
    raw = _template_raw()
    raw["autonomy"]["cribado"] = "A1"
    with pytest.raises(ValidationError, match="etapa desconocida"):
        ReviewProtocol.model_validate(raw)


def test_autonomy_a3_permitido_en_etapa_determinista() -> None:
    raw = _template_raw()
    raw["autonomy"]["dedup"] = "A3"
    assert ReviewProtocol.model_validate(raw).autonomy_for("dedup") == "A3"


def test_load_protocol_con_a3_en_juicio_falla(tmp_path: Path) -> None:
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["autonomy"]["rob"] = "A3"
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_protocol(proto)


@pytest.mark.parametrize("contenido", ["- a\n", "hola\n", "42\n", "", "# solo un comentario\n"])
def test_load_protocol_que_no_es_un_mapa_lanza_validation_error(
    tmp_path: Path, contenido: str
) -> None:
    # Una lista o un escalar hacían `raw.setdefault(...)` y lanzaban AttributeError; un
    # fichero vacío o solo con comentarios sigue siendo `{}` y falla por la pregunta.
    (tmp_path / "protocol.yml").write_text(contenido, encoding="utf-8")
    with pytest.raises(ValidationError, match="ReviewProtocol"):
        load_protocol(tmp_path)
