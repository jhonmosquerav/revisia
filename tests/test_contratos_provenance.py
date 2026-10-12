"""Hashes canónicos y reductor del ledger (spec 2026-10-04 §4.1, §4.3; PR-0)."""

from __future__ import annotations

import hashlib
import math
from typing import get_args

import pytest

from revisia.provenance.ledger import (
    AUTO_APPROVE_ACTOR,
    GATE_DECISION_ACTIONS,
    HUMAN_ACTOR_PREFIX,
    LEDGER_ACTIONS,
    DecisionEntry,
    is_human_actor,
    summarize_gates,
)
from revisia.provenance.runmeta import canonical_json, canonical_sha256
from revisia.schemas.artifacts import GateAction

# ── canonical_json / canonical_sha256 ───────────────────────────────────


def test_canonical_json_ordena_claves_sin_espacios_y_utf8_literal() -> None:
    assert canonical_json({"b": 1, "a": "ñ", "c": [1, {"z": None, "y": True}]}) == (
        '{"a":"ñ","b":1,"c":[1,{"y":true,"z":null}]}'
    )


def test_canonical_sha256_no_depende_del_orden_de_insercion() -> None:
    uno = {"stage": "screening_ta", "records": [{"id": "10.1/x", "label": "include"}]}
    otro = {"records": [{"label": "include", "id": "10.1/x"}], "stage": "screening_ta"}
    assert canonical_sha256(uno) == canonical_sha256(otro)
    esperado = hashlib.sha256(canonical_json(uno).encode("utf-8")).hexdigest()
    assert canonical_sha256(uno) == esperado
    assert len(esperado) == 64


@pytest.mark.parametrize("valor", [math.nan, math.inf, -math.inf])
def test_canonical_json_rechaza_no_finitos(valor: float) -> None:
    with pytest.raises(ValueError):
        canonical_json({"recall": valor})


# ── Constantes del ledger ────────────────────────────────────────────────


def test_constantes_del_ledger() -> None:
    assert set(LEDGER_ACTIONS) == {"approve", "reject", "auto-proceed", "label", "flag_review"}
    assert set(GATE_DECISION_ACTIONS) == {"approve", "reject", "auto-proceed"}
    assert GATE_DECISION_ACTIONS < LEDGER_ACTIONS
    assert HUMAN_ACTOR_PREFIX == "human:"
    assert AUTO_APPROVE_ACTOR == "auto-approve (demo)"
    # Las acciones de la reconstrucción C3 no las emite el motor.
    assert not {"propose", "exclude", "verify"} & LEDGER_ACTIONS


def test_gate_action_y_gate_decision_actions_van_atados() -> None:
    # Dos fuentes de verdad (el Literal de `GateSummary.action` y el conjunto que
    # usa el reductor): si una crece sin la otra, el reductor produciría un resumen
    # que su propio modelo rechaza, o ignoraría una acción válida.
    assert set(get_args(GateAction)) == GATE_DECISION_ACTIONS


# ── is_human_actor: la única definición de «humano» ─────────────────────


@pytest.mark.parametrize(
    "actor",
    ["human:ana", "human:desconocido", "human: ana", "human:a" + chr(0x200B) + "na"],
)
def test_is_human_actor_acepta_un_nombre_visible(actor: str) -> None:
    assert is_human_actor(actor)


@pytest.mark.parametrize(
    "actor",
    [
        "",
        "ana",
        "agent:extraccion",
        AUTO_APPROVE_ACTOR,
        "human:",
        "human:   ",
        "human:\t",
        "human:" + chr(0xA0),
        "human:" + chr(0x200B),  # espacio de ancho cero (Cf): invisible, no es un nombre
        "human:" + chr(0xFEFF) + chr(0xAD) + " ",
        "human:" + chr(0),  # NUL: no imprimible
    ],
)
def test_is_human_actor_rechaza_lo_que_no_es_un_humano_con_nombre(actor: str) -> None:
    assert not is_human_actor(actor)


# ── summarize_gates ──────────────────────────────────────────────────────


def _e(stage: str, action: str, actor: str = "human:ana", **detail) -> DecisionEntry:
    target = detail.pop("target", None)
    return DecisionEntry(
        stage=stage, actor=actor, autonomy="A1", action=action, target=target, detail=detail
    )


def test_summarize_gates_ledger_vacio() -> None:
    assert summarize_gates([]) == {}


def test_summarize_gates_ultima_decision_gana_tras_rechazo() -> None:
    resumen = summarize_gates(
        [
            _e("screening_ta", "reject", request_sha256="r1", decision_sha256="d1"),
            _e("screening_ta", "approve", request_sha256="r1", decision_sha256="d2"),
        ]
    )
    ta = resumen["screening_ta"]
    assert (ta.action, ta.request_sha256, ta.decision_sha256) == ("approve", "r1", "d2")


def test_summarize_gates_cuenta_solo_etiquetas_de_la_decision_efectiva() -> None:
    resumen = summarize_gates(
        [
            # Decisión anterior, rechazada, con una etiqueta de su mismo hash ("viejo"). Tras
            # el `approve` posterior queda como etiqueta huérfana: no cuenta, porque su
            # `decision_sha256` no es el de la decisión efectiva ("nuevo").
            _e("screening_ft", "label", target="a", decision_sha256="viejo"),
            _e("screening_ft", "reject", decision_sha256="viejo"),
            # Decisión efectiva con dos etiquetas.
            _e("screening_ft", "label", target="a", decision_sha256="nuevo"),
            _e("screening_ft", "label", target="b", decision_sha256="nuevo"),
            _e("screening_ft", "approve", decision_sha256="nuevo", request_sha256="r"),
            # Una etiqueta de otra etapa con el mismo hash no cuenta.
            _e("screening_ta", "label", target="z", decision_sha256="nuevo"),
        ]
    )
    assert resumen["screening_ft"].n_labels == 2
    assert resumen["screening_ft"].n_flag_reviews == 0
    assert "screening_ta" not in resumen  # sin approve/reject/auto-proceed


def test_summarize_gates_reject_final_es_la_decision_efectiva() -> None:
    resumen = summarize_gates(
        [
            _e("screening_ft", "label", target="a", decision_sha256="A"),
            _e("screening_ft", "approve", decision_sha256="A", request_sha256="r"),
            # Se rechaza después: la decisión efectiva es el `reject` (hash B) y la
            # etiqueta del `approve` anterior (hash A) pasa a ser huérfana.
            _e("screening_ft", "reject", decision_sha256="B", request_sha256="r"),
        ]
    )
    ft = resumen["screening_ft"]
    assert (ft.action, ft.decision_sha256, ft.n_labels) == ("reject", "B", 0)


def test_summarize_gates_sin_hash_de_decision_no_cuenta_etiquetas_sin_hash() -> None:
    # `auto-proceed` no lleva `decision_sha256`, y una etiqueta de la misma etapa
    # tampoco: `None == None` no debe hacerlas coincidir. Sin la guarda
    # `decision_sha is not None` de `summarize_gates`, `n_labels` saldría 1.
    resumen = summarize_gates(
        [
            _e("extraccion", "label", target="a"),
            _e("extraccion", "auto-proceed", actor="agent:extraccion", reason="autonomía A2"),
        ]
    )
    extraccion = resumen["extraccion"]
    assert extraccion.decision_sha256 is None
    assert (extraccion.n_labels, extraccion.n_flag_reviews) == (0, 0)


def test_summarize_gates_flag_reviews_y_forced_human() -> None:
    resumen = summarize_gates(
        [
            _e("reporte", "flag_review", target="flag:0", decision_sha256="d"),
            _e("reporte", "flag_review", target="flag:3", decision_sha256="d"),
            _e("reporte", "approve", decision_sha256="d", forced_human=True),
        ]
    )
    reporte = resumen["reporte"]
    assert (reporte.n_flag_reviews, reporte.forced_human) == (2, True)
    assert reporte.actor.startswith(HUMAN_ACTOR_PREFIX)


def test_summarize_gates_auto_proceed_y_ledger_antiguo() -> None:
    resumen = summarize_gates(
        [
            _e("sintesis", "auto-proceed", actor="agent:sintesis", reason="autonomía A2"),
            # Entrada de la Ola 0: sin hashes en el detail.
            _e("reporte", "approve", actor=AUTO_APPROVE_ACTOR, reason="demo"),
        ]
    )
    assert resumen["sintesis"].action == "auto-proceed"
    assert resumen["sintesis"].decision_sha256 is None
    assert resumen["reporte"].request_sha256 is None
    assert resumen["reporte"].n_labels == 0
    assert resumen["reporte"].actor == AUTO_APPROVE_ACTOR
