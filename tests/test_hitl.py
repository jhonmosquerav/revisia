"""Tests del checkpoint humano file-based (auditoría 2026-09-03, C1 y bajos)."""

from __future__ import annotations

from pathlib import Path

import pytest

from revisia.orchestration.hitl import DecisionFileError, review_gate
from revisia.orchestration.run_context import RunContext


def _gate(tmp_path: Path, decision_text: str | None, *, auto_approve: bool = False):
    ctx = RunContext("demo", tmp_path, "T")
    stage_dir = ctx.stage_dir("reporte")
    if decision_text is not None:
        (stage_dir / "decision.yml").write_text(decision_text, encoding="utf-8")
    result = review_gate(
        stage="reporte",
        autonomy="A1",
        run_ctx=ctx,
        review_payload={"included": 1},
        auto_approve=auto_approve,
    )
    return ctx, result


def test_decision_string_false_does_not_approve(tmp_path: Path) -> None:
    # bool("false") es True: antes, esta decisión APROBABA.
    with pytest.raises(DecisionFileError, match="booleano"):
        _gate(tmp_path, 'approved: "false"\n')


def test_decision_false_rechaza(tmp_path: Path) -> None:
    ctx, result = _gate(tmp_path, "approved: false\nactor: human:revisora\n")
    assert result.status == "rejected"
    entry = ctx.ledger.read_all()[-1]
    assert entry.action == "reject"
    assert entry.actor == "human:revisora"


def test_decision_booleana_aprueba_y_registra_actor(tmp_path: Path) -> None:
    ctx, result = _gate(tmp_path, "approved: true\nactor: human:jhon\nreason: ok\n")
    assert result.status == "approved"
    entry = ctx.ledger.read_all()[-1]
    assert entry.actor == "human:jhon"
    assert entry.detail == {"reason": "ok"}


def test_campos_extra_se_conservan_en_el_ledger(tmp_path: Path) -> None:
    ctx, _ = _gate(tmp_path, "approved: true\nnota: revisado a mano\n")
    assert ctx.ledger.read_all()[-1].detail == {"nota": "revisado a mano"}


@pytest.mark.parametrize(
    "text",
    [
        "- approved: true\n",  # raíz lista (antes: AttributeError)
        "",  # vacío (antes: rechazo silencioso de human:desconocido)
        "approved: [\n",  # YAML roto (antes: traceback de yaml)
        "actor: human:x\n",  # falta approved
    ],
)
def test_malformed_decision_yaml_is_actionable(tmp_path: Path, text: str) -> None:
    with pytest.raises(DecisionFileError, match="decision.yml"):
        _gate(tmp_path, text)


def test_auto_approve_sin_decision(tmp_path: Path) -> None:
    ctx, result = _gate(tmp_path, None, auto_approve=True)
    assert result.status == "approved"
    entry = ctx.ledger.read_all()[-1]
    assert entry.actor == "auto-approve (demo)"
    assert entry.detail == {}


def test_sin_decision_pausa(tmp_path: Path) -> None:
    _, result = _gate(tmp_path, None)
    assert result.status == "paused"
