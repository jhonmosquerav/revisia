"""Especificaciones oficiales de RoB como datos (spec 2026-10-18 §4.2, §4.4; D5; riesgo 5)."""

from __future__ import annotations

from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from revisia.schemas.rob import RoBTool
from revisia.schemas.rob_tools import (
    TOOLS_DIR,
    RoBToolSpec,
    load_tool_spec,
    tool_spec_fingerprint,
    tool_spec_path,
)

HERRAMIENTAS = get_args(RoBTool)


@pytest.mark.parametrize("tool", HERRAMIENTAS)
def test_cada_herramienta_tiene_su_yaml_y_carga(tool: str) -> None:
    assert tool_spec_path(tool) == TOOLS_DIR / f"{tool}.yml"
    spec = load_tool_spec(tool)
    assert spec.id == tool
    assert spec.source.url.startswith("https://")
    assert spec.source.version and spec.source.license_note
    for dominio in spec.domains:
        assert len(spec.scale_for(dominio.id)) >= 2
        for q in dominio.signalling_questions:
            assert q.id and 0 < len(q.text) <= 200 and len(q.answers) >= 2


def test_rob2_estructura_oficial() -> None:
    spec = load_tool_spec("RoB2")
    assert spec.domain_ids == ("D1", "D2", "D3", "D4", "D5")
    assert [len(d.signalling_questions) for d in spec.domains] == [3, 7, 4, 5, 3]
    assert spec.n_questions == 22
    assert spec.judgment_scale == ["low", "some_concerns", "high"] == spec.overall_scale
    assert (spec.unit, spec.aggregation, spec.robvis_template) == ("domain", "rob2", "rob2")
    assert spec.domains[1].signalling_questions[0].answers == ["Y", "PY", "PN", "N", "NI"]
    assert [q.id for q in spec.domains[0].signalling_questions] == ["1.1", "1.2", "1.3"]


def test_robins_i_estructura_oficial() -> None:
    spec = load_tool_spec("ROBINS-I")
    assert spec.domain_ids == tuple(f"D{i}" for i in range(1, 8))
    # D4 en la variante «efecto de la asignación», como RoB 2: solo 4.1 y 4.2.
    assert [len(d.signalling_questions) for d in spec.domains] == [8, 5, 3, 2, 5, 4, 3]
    assert spec.n_questions == 30
    assert spec.judgment_scale == ["low", "moderate", "serious", "critical", "no_information"]
    assert (spec.aggregation, spec.robvis_template) == ("robins_i", "robins_i")


def _ids(*por_dominio: int) -> list[str]:
    """Secuencia oficial de ids ``"<dominio>.<n>"`` a partir del número de preguntas."""
    return [f"{d}.{n}" for d, total in enumerate(por_dominio, 1) for n in range(1, total + 1)]


@pytest.mark.parametrize(
    ("tool", "ids"),
    [
        ("RoB2", _ids(3, 7, 4, 5, 3)),
        ("ROBINS-I", _ids(8, 5, 3, 2, 5, 4, 3)),
        ("QUADAS-2", _ids(3, 2, 2, 4)),
        ("AMSTAR2", []),
        ("NewcastleOttawa", []),
        ("NewcastleOttawaCaseControl", []),
    ],
)
def test_secuencia_completa_de_ids_de_preguntas(tool: str, ids: list[str]) -> None:
    spec = load_tool_spec(tool)
    assert [q.id for d in spec.domains for q in d.signalling_questions] == ids


NA_OFICIAL = {
    "RoB2": ["2.3", "2.4", "2.5", "2.7", "3.2", "3.3", "3.4", "4.3", "4.4", "4.5"],
    "ROBINS-I": ["1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "2.2", "2.3", "2.5", "5.4"]
    + ["5.5"],
}


@pytest.mark.parametrize("tool", HERRAMIENTAS)
def test_na_solo_en_las_preguntas_condicionales(tool: str) -> None:
    spec = load_tool_spec(tool)
    con_na = [q.id for d in spec.domains for q in d.signalling_questions if "NA" in q.answers]
    assert con_na == NA_OFICIAL.get(tool, [])
    for d in spec.domains:
        for q in d.signalling_questions:
            base = ["Y", "N", "U"] if tool == "QUADAS-2" else ["Y", "PY", "PN", "N", "NI"]
            assert q.answers == base + (["NA"] if q.id in con_na else [])


@pytest.mark.parametrize(
    ("tool", "ids"),
    [
        ("NewcastleOttawa", ("S1", "S2", "S3", "S4", "C1", "O1", "O2", "O3")),
        ("NewcastleOttawaCaseControl", ("S1", "S2", "S3", "S4", "C1", "E1", "E2", "E3")),
    ],
)
def test_nos_ocho_items_y_nueve_estrellas(tool: str, ids: tuple[str, ...]) -> None:
    spec = load_tool_spec(tool)
    assert spec.domain_ids == ids
    assert (spec.unit, spec.aggregation, spec.overall_scale, spec.robvis_template) == (
        "star",
        "nos_stars",
        None,
        "generic",
    )
    assert spec.scale_for("C1") == ("0", "1", "2")
    assert sum(int(spec.scale_for(i)[-1]) for i in spec.domain_ids) == 9
    assert spec.n_questions == 0


def test_amstar2_dieciseis_items_siete_criticos() -> None:
    spec = load_tool_spec("AMSTAR2")
    assert spec.domain_ids == tuple(str(i) for i in range(1, 17))
    assert spec.critical_items == ["2", "4", "7", "9", "11", "13", "15"]
    parciales = {i for i in spec.domain_ids if "partial_yes" in spec.scale_for(i)}
    assert parciales == {"2", "4", "7", "8", "9"}
    sin_meta = {i for i in spec.domain_ids if "no_meta_analysis" in spec.scale_for(i)}
    assert sin_meta == {"11", "12", "15"}
    assert spec.overall_scale == ["high", "moderate", "low", "critically_low"]
    assert (spec.unit, spec.aggregation, spec.robvis_template) == ("item", "amstar2", "generic")


def test_quadas2_cuatro_dominios_tres_de_aplicabilidad_sin_global() -> None:
    spec = load_tool_spec("QUADAS-2")
    assert spec.domain_ids == (
        "patient_selection",
        "index_test",
        "reference_standard",
        "flow_and_timing",
    )
    assert [len(d.signalling_questions) for d in spec.domains] == [3, 2, 2, 4]
    assert [a.id for a in spec.applicability] == [
        "patient_selection",
        "index_test",
        "reference_standard",
    ]
    assert spec.judgment_scale == ["low", "high", "unclear"]
    assert (spec.overall_scale, spec.aggregation, spec.robvis_template) == (
        None,
        "none",
        "quadas2",
    )


def _minima(**cambios) -> dict:
    base = {
        "id": "RoB2",
        "name": "x",
        "version": "v",
        "unit": "domain",
        "judgment_scale": ["low", "high"],
        "overall_scale": ["low", "high"],
        "domains": [{"id": "D1", "name": "a"}, {"id": "D2", "name": "b"}],
        "aggregation": "rob2",
        "robvis_template": "rob2",
        "source": {"citation": "c", "url": "https://x", "version": "v", "license_note": "n"},
    }
    base.update(cambios)
    return base


def _pregunta(qid: str) -> dict:
    return {"id": qid, "text": "t", "answers": ["Y", "N"]}


@pytest.mark.parametrize(
    "cambios",
    [
        {"domains": [{"id": "D1", "name": "a"}, {"id": "D1", "name": "b"}]},  # id repetido
        {"critical_items": ["D9"]},  # crítico inexistente
        {"judgment_scale": ["low"]},  # escala de un valor
        {"judgment_scale": ["low", "low"]},  # escala con repetidos
        {"overall_scale": None},  # rob2 produce un juicio global: necesita su escala
        {"aggregation": "none"},  # sin agregación no hay escala global (y aquí viene una)
        {"domains": [{"id": "D1", "name": "a", "scale": []}]},  # escala vacía
        {"extra": 1},  # clave desconocida
        {
            "domains": [
                {"id": "D1", "name": "a", "signalling_questions": [_pregunta("1.1")]},
                {"id": "D2", "name": "b", "signalling_questions": [_pregunta("1.1")]},
            ]
        },  # pregunta repetida entre dominios
        {
            "domains": [
                {"id": "D1", "name": "a", "signalling_questions": [_pregunta("1.1")]},
                {"id": "D2", "name": "b", "signalling_questions": [_pregunta("1.2")]},
            ]
        },  # pregunta de D2 con el prefijo de D1
        {
            "domains": [
                {"id": "D1", "name": "a", "signalling_questions": [_pregunta("11.1")]},
            ]
        },  # «11.1» no es del dominio 1 aunque empiece por «1»
        {
            "domains": [
                {
                    "id": "D1",
                    "name": "a",
                    "signalling_questions": [{"id": "1.1", "text": "t", "answers": ["Y", "Y"]}],
                },
            ]
        },  # respuestas repetidas
    ],
)
def test_una_especificacion_incoherente_no_carga(cambios: dict) -> None:
    with pytest.raises(ValidationError):
        RoBToolSpec.model_validate(_minima(**cambios))


def test_scale_for_desconocido_es_key_error() -> None:
    with pytest.raises(KeyError):
        load_tool_spec("RoB2").scale_for("D9")


def test_fingerprint_cubre_los_seis_con_la_clave_rob_tool_yml() -> None:
    huella = tool_spec_fingerprint()
    assert set(huella) == {f"rob/{t}.yml" for t in HERRAMIENTAS}
    assert all(len(h) == 64 for h in huella.values())
    assert list(huella) == sorted(huella)


def test_los_yaml_son_mapas_planos_sin_anclas_ni_fusion() -> None:
    for tool in HERRAMIENTAS:
        texto = tool_spec_path(tool).read_text(encoding="utf-8")
        assert "&" not in texto and "<<" not in texto  # sin anclas: lo que se lee es lo que se ve
        assert isinstance(yaml.safe_load(texto), dict)


def test_load_tool_spec_con_yaml_incoherente_falla_al_cargar_y_nombra_el_fichero(
    tmp_path, monkeypatch
) -> None:
    import revisia.schemas.rob_tools as modulo

    datos = _minima(domains=[{"id": "D1", "name": "a"}, {"id": "D1", "name": "b"}])
    (tmp_path / "RoB2.yml").write_text(yaml.safe_dump(datos), encoding="utf-8")
    monkeypatch.setattr(modulo, "TOOLS_DIR", tmp_path)
    with pytest.raises(ValueError, match=r"RoB2\.yml"):
        load_tool_spec("RoB2")


def test_load_tool_spec_exige_que_el_id_coincida_con_el_fichero(tmp_path, monkeypatch) -> None:
    import revisia.schemas.rob_tools as modulo

    (tmp_path / "AMSTAR2.yml").write_text(yaml.safe_dump(_minima()), encoding="utf-8")
    monkeypatch.setattr(modulo, "TOOLS_DIR", tmp_path)
    with pytest.raises(ValueError, match=r"AMSTAR2\.yml"):
        load_tool_spec("AMSTAR2")


def test_load_tool_spec_con_yaml_mal_formado_nombra_el_fichero(tmp_path, monkeypatch) -> None:
    import revisia.schemas.rob_tools as modulo

    (tmp_path / "RoB2.yml").write_text("id: [sin cerrar\n", encoding="utf-8")
    monkeypatch.setattr(modulo, "TOOLS_DIR", tmp_path)
    with pytest.raises(ValueError, match=r"RoB2\.yml"):
        load_tool_spec("RoB2")


def test_load_tool_spec_sin_fichero_nombra_el_fichero(tmp_path, monkeypatch) -> None:
    import revisia.schemas.rob_tools as modulo

    monkeypatch.setattr(modulo, "TOOLS_DIR", tmp_path)
    with pytest.raises(ValueError, match=r"QUADAS-2\.yml"):
        load_tool_spec("QUADAS-2")
