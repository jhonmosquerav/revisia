"""Tests del puente motor↔config: carga y validación de protocol.yml."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from revisia.config import ReviewProtocol, load_protocol

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"
EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


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


# ── umbrales: finitos y en su rango ──────────────────────────────────────


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("clave", ["kappa_min", "recall_target", "wmcc_fn_weight", "kapa_min"])
def test_umbral_no_finito_rechazado(clave: str, valor: float) -> None:
    # `.nan` e `.inf` son YAML válido y `dict[str, float]` los aceptaba: un
    # `wmcc_fn_weight: .nan` daba un WMCC nan y `json.dumps(allow_nan=False)` reventaba en
    # el cribado, una y otra vez al reanudar. Vale para toda clave, también una errata.
    raw = _template_raw()
    raw["thresholds"][clave] = valor
    with pytest.raises(ValidationError, match=rf"thresholds\.{clave}: .*no es un número finito"):
        ReviewProtocol.model_validate(raw)


@pytest.mark.parametrize(
    ("clave", "valor", "rango"),
    [
        ("recall_target", -0.01, r"\[0, 1\]"),
        ("recall_target", 1.01, r"\[0, 1\]"),
        ("kappa_min", -1.01, r"\[-1, 1\]"),
        ("kappa_min", 1.01, r"\[-1, 1\]"),
        ("wmcc_fn_weight", 0.0, "mayor que 0"),
        ("wmcc_fn_weight", -3.0, "mayor que 0"),
        ("wmcc_fn_weight", 1000.01, "no pasar de 1000"),
    ],
)
def test_umbral_fuera_de_rango_rechazado(clave: str, valor: float, rango: str) -> None:
    raw = _template_raw()
    raw["thresholds"][clave] = valor
    with pytest.raises(ValidationError, match=rf"thresholds\.{clave}: .*{rango}"):
        ReviewProtocol.model_validate(raw)


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("recall_target", 0.0),
        ("recall_target", 1.0),
        ("kappa_min", -1.0),  # κ admite [-1, 1]; los extremos valen
        ("kappa_min", 0.6),
        ("kappa_min", 1.0),
        ("wmcc_fn_weight", 0.5),
        ("wmcc_fn_weight", 10.0),
        ("wmcc_fn_weight", 1000.0),  # el tope cuenta: es el último peso válido
        ("otro_umbral", 5.0),  # una clave desconocida solo debe ser finita (el auditor avisa)
    ],
)
def test_umbral_valido_se_acepta(clave: str, valor: float) -> None:
    raw = _template_raw()
    raw["thresholds"] = {clave: valor}
    assert ReviewProtocol.model_validate(raw).thresholds == {clave: valor}


def test_load_protocol_con_umbral_nan_en_el_yaml_falla(tmp_path: Path) -> None:
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["thresholds"]["wmcc_fn_weight"] = float("nan")  # safe_dump lo escribe como `.nan`
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    assert ".nan" in (proto / "protocol.yml").read_text(encoding="utf-8")
    with pytest.raises(ValidationError, match="wmcc_fn_weight"):
        load_protocol(proto)


def test_load_protocol_con_wmcc_fn_weight_enorme_pero_finito_falla(tmp_path: Path) -> None:
    # `1e308` es finito y positivo, y pasaba: con algún falso negativo `fn_weight * fn` se
    # desbordaba, el WMCC salía nan y `canonical_sha256(allow_nan=False)` reventaba en el
    # cribado (rc 3 en bucle). Un peso de falso negativo razonable no pasa de unos cientos.
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["thresholds"]["wmcc_fn_weight"] = 1e308
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValidationError, match=r"thresholds\.wmcc_fn_weight: .*no pasar de 1000"):
        load_protocol(proto)


@pytest.mark.parametrize("carpeta", [TEMPLATE_DIR, EXAMPLE_DIR], ids=["_TEMPLATE", "demo"])
def test_los_protocolos_incluidos_cumplen_los_umbrales(carpeta: Path) -> None:
    assert load_protocol(carpeta).thresholds  # declaran umbrales y siguen cargando


@pytest.mark.parametrize("contenido", ["- a\n", "hola\n", "42\n", "", "# solo un comentario\n"])
def test_load_protocol_que_no_es_un_mapa_lanza_validation_error(
    tmp_path: Path, contenido: str
) -> None:
    # Una lista o un escalar hacían `raw.setdefault(...)` y lanzaban AttributeError; un
    # fichero vacío o solo con comentarios sigue siendo `{}` y falla por la pregunta.
    (tmp_path / "protocol.yml").write_text(contenido, encoding="utf-8")
    with pytest.raises(ValidationError, match="ReviewProtocol"):
        load_protocol(tmp_path)


# ── quién cribá una etapa: un solo predicado para `n_screeners_for` y `screeners_for` ──


def _protocolo_con_ensemble(declaradas: list[str], miembros: int) -> ReviewProtocol:
    raw = _template_raw()
    raw["llm"]["default"] = {"provider": "fake", "model": "m-unico"}
    raw["ensemble"] = declaradas
    raw["ensemble_llm"] = {
        "screening_ta": [{"provider": "fake", "model": f"m-{i}"} for i in range(miembros)]
    }
    return ReviewProtocol.model_validate(raw)


@pytest.mark.parametrize(
    ("declaradas", "miembros", "esperado"),
    [
        (["screening_ta"], 3, 3),
        (["screening_ta"], 1, 1),
        (["screening_ta"], 0, 1),  # declarada pero sin modelos: cae al proveedor de la etapa
        ([], 3, 1),  # modelos sin declarar la etapa en `ensemble`: no hay ensemble
    ],
)
def test_n_screeners_for_cuenta_lo_que_devuelve_screeners_for(
    declaradas: list[str], miembros: int, esperado: int
) -> None:
    # Fija el contrato de los dos métodos, que comparten el criterio de «hay ensemble».
    protocol = _protocolo_con_ensemble(declaradas, miembros)
    assert protocol.n_screeners_for("screening_ta") == esperado
    assert len(protocol.screeners_for("screening_ta")) == esperado


def test_n_screeners_for_no_exige_proveedor_pero_screeners_for_si() -> None:
    # `metodologia.md` se rinde también sobre protocolos incompletos: contar no lanza.
    raw = _template_raw()
    raw["llm"], raw["ensemble"], raw["ensemble_llm"] = {}, [], {}
    protocol = ReviewProtocol.model_validate(raw)
    assert protocol.n_screeners_for("screening_ta") == 1
    with pytest.raises(KeyError):
        protocol.screeners_for("screening_ta")
