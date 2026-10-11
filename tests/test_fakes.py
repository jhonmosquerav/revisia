"""Los dobles compartidos de la Ola 1 hacen lo que prometen (tests/fakes.py)."""

from __future__ import annotations

import pytest
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible

from revisia.agents.extraccion import extract_record
from revisia.agents.screening import ScreenerMember, screen_record
from revisia.agents.screening_ft import screen_fulltext
from revisia.llm.base import LLMProvider, LLMRequest
from revisia.schemas.records import SearchRecord


def _rec(rid: str, title: str, abstract: str = "") -> SearchRecord:
    return SearchRecord(record_id=rid, title=title, abstract=abstract)


def _cribar(proveedor: ScriptedProvider, record: SearchRecord):
    member = ScreenerMember(provider=proveedor, model_name="fake:guion")
    return screen_record([member], question="¿X?", criteria="- c: incluir", record=record)


def test_cumple_el_protocolo_y_declara_fake_determinista() -> None:
    proveedor = ScriptedProvider()
    assert isinstance(proveedor, LLMProvider)
    respuesta = proveedor.complete(LLMRequest(prompt="sintetiza"))
    assert "[" not in respuesta.text
    assert (respuesta.meta.provider, respuesta.meta.deterministic) == ("fake", True)
    assert respuesta.meta.model == "fake-guion"


@pytest.mark.parametrize(
    ("titulo", "esperado"),
    [
        ("Estudio irrelevante para la pregunta", "exclude"),
        ("Un caso DUDOSO", "unclear"),
        ("LLM screening for systematic reviews", "include"),
    ],
)
def test_etiqueta_por_palabra_clave_en_el_cribado(titulo: str, esperado: str) -> None:
    decision, metas = _cribar(ScriptedProvider(), _rec("r", titulo))
    assert decision.ensemble_label == esperado
    assert decision.votes[0].label == esperado
    # Solo `exclude` declara criterio violado (el `criterio_exclusion` por defecto).
    criterios = ["fuera de alcance"] if esperado == "exclude" else []
    assert decision.votes[0].criteria_violated == criterios
    assert len(metas) == 1


def test_precedencia_es_el_orden_del_dict_no_la_posicion_en_el_prompt() -> None:
    # "dudoso" aparece antes en el prompt, pero "irrelevante" va primero en
    # `PALABRAS_POR_DEFECTO`: gana el orden del dict (regla vigente de `label_for`).
    assert ScriptedProvider().label_for("dudoso pero irrelevante") == "exclude"
    assert ScriptedProvider().label_for("irrelevante pero dudoso") == "exclude"


def test_palabras_propias_sustituyen_a_las_de_por_defecto() -> None:
    proveedor = ScriptedProvider(palabras={"Piloto": "unclear", "dudoso": "exclude"})
    assert proveedor.label_for("Un ensayo PILOTO") == "unclear"  # sin distinguir mayúsculas
    assert proveedor.label_for("caso dudoso") == "exclude"
    # Las de por defecto ya no están: "irrelevante" solo no coincide con nada.
    assert proveedor.label_for("estudio irrelevante") == "include"


def test_fail_at_menor_que_uno_es_un_error() -> None:
    # Cuenta desde 1: un 0 nunca dispararía el 429 y el test no probaría nada.
    for invalido in (0, -1):
        with pytest.raises(ValueError, match="desde 1"):
            ScriptedProvider(fail_at=invalido)
    assert ScriptedProvider(fail_at=1).fail_at == 1
    assert ScriptedProvider().fail_at is None


def test_exclusion_lleva_criterio_violado() -> None:
    proveedor = ScriptedProvider(criterio_exclusion="población")
    decision, _ = screen_fulltext(
        proveedor,
        "fake:guion",
        question="¿X?",
        criteria="- c",
        record=_rec("r", "T"),
        text="texto irrelevante",
    )
    assert decision.ensemble_label == "exclude"
    assert decision.votes[0].criteria_violated == ["población"]


def test_esquemas_sin_etiqueta_se_fabrican_como_fake() -> None:
    extraccion, meta = extract_record(
        ScriptedProvider(), record=_rec("r", "irrelevante"), form_fields=[{"key": "n"}]
    )
    assert extraccion.study_id == "r"
    assert meta.provider == "fake"


def test_cuenta_llamadas_y_falla_en_la_k() -> None:
    proveedor = ScriptedProvider(fail_at=2)
    _cribar(proveedor, _rec("a", "registro alfa"))
    with pytest.raises(RuntimeError, match="429 Too Many Requests"):
        _cribar(proveedor, _rec("b", "registro beta"))
    _cribar(proveedor, _rec("c", "registro gamma"))  # tras el fallo sigue respondiendo
    assert proveedor.calls == 3
    assert "registro alfa" in proveedor.prompts[0]
    assert "registro beta" in proveedor.prompts[1]


def test_fetch_disponible_y_no_disponible() -> None:
    a, b = _rec("10.1/a", "Título A", "resumen A"), _rec("10.1/b", "Título B", "resumen B")
    ft = fetch_disponible(a)
    assert ft.available is True and "Título A" in ft.text and ft.source_url
    fetch = fetch_no_disponible(["10.1/b"])
    assert fetch(a).available is True
    no = fetch(b)
    assert (no.available, no.text) == (False, "resumen B")


def test_fetch_no_disponible_rechaza_una_cadena_suelta() -> None:
    # Un `str` es iterable: sin la guarda, "10.1/b" se troceaba en caracteres y el
    # registro salía disponible sin avisar.
    with pytest.raises(TypeError, match="colección de ids"):
        fetch_no_disponible("10.1/b")
