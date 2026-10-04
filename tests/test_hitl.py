"""Tests del checkpoint humano file-based (auditoría 2026-09-03, C1 y bajos; Ola 1,
`request_sha256`, ledger idempotente: spec 2026-10-04 §4.3 y §7)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from revisia.orchestration.hitl import DecisionFileError, GateResult, review_gate
from revisia.orchestration.run_context import RunContext
from revisia.provenance.runmeta import canonical_sha256


def _solicitar(
    ctx: RunContext,
    *,
    payload: dict | None = None,
    autonomy: str = "A1",
    auto_approve: bool = False,
) -> GateResult:
    return review_gate(
        stage="reporte",
        autonomy=autonomy,
        run_ctx=ctx,
        review_payload={"included": 1} if payload is None else payload,
        auto_approve=auto_approve,
    )


def _decidir(ctx: RunContext, texto: str, sha: str) -> None:
    """Escribe decision.yml; ``@SHA@`` se sustituye por el hash de la solicitud."""
    path = ctx.stage_dir("reporte") / "decision.yml"
    path.write_text(texto.replace("@SHA@", sha), encoding="utf-8")


def _gate(tmp_path: Path, decision_text: str | None, *, auto_approve: bool = False):
    ctx = RunContext("demo", tmp_path, "T")
    if decision_text is None:
        return ctx, _solicitar(ctx, auto_approve=auto_approve)
    pausa = _solicitar(ctx)  # primera vuelta: escribe la solicitud y pausa
    _decidir(ctx, decision_text, pausa.request_sha256)
    return ctx, _solicitar(ctx, auto_approve=auto_approve)


def test_decision_string_false_does_not_approve(tmp_path: Path) -> None:
    # bool("false") es True: antes, esta decisión APROBABA.
    with pytest.raises(DecisionFileError, match="booleano"):
        _gate(tmp_path, 'request_sha256: "@SHA@"\napproved: "false"\n')


def test_decision_false_rechaza(tmp_path: Path) -> None:
    ctx, result = _gate(
        tmp_path, 'request_sha256: "@SHA@"\napproved: false\nactor: human:revisora\n'
    )
    assert result.status == "rejected"
    entry = ctx.ledger.read_all()[-1]
    assert entry.action == "reject"
    assert entry.actor == "human:revisora"


def test_decision_booleana_aprueba_y_registra_actor(tmp_path: Path) -> None:
    ctx, result = _gate(
        tmp_path, 'request_sha256: "@SHA@"\napproved: true\nactor: human:jhon\nreason: ok\n'
    )
    assert result.status == "approved"
    entry = ctx.ledger.read_all()[-1]
    assert entry.actor == "human:jhon"
    assert {"reason": "ok", "request_sha256": result.request_sha256}.items() <= entry.detail.items()


def test_campos_extra_se_conservan_en_el_ledger(tmp_path: Path) -> None:
    ctx, _ = _gate(tmp_path, 'request_sha256: "@SHA@"\napproved: true\nnota: revisado a mano\n')
    assert ctx.ledger.read_all()[-1].detail["nota"] == "revisado a mano"


@pytest.mark.parametrize(
    "text",
    [
        "- approved: true\n",  # raíz lista (antes: AttributeError)
        "",  # vacío (antes: rechazo silencioso de human:desconocido)
        "approved: [\n",  # YAML roto (antes: traceback de yaml)
        'request_sha256: "@SHA@"\nactor: human:x\n',  # falta approved
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
    assert set(entry.detail) == {"request_sha256", "decision_sha256", "n_labels", "forced_human"}
    assert (entry.detail["n_labels"], entry.detail["forced_human"]) == (0, False)


def test_sin_decision_pausa(tmp_path: Path) -> None:
    _, result = _gate(tmp_path, None)
    assert result.status == "paused"


# ── request_sha256 y ledger idempotente (Ola 1, spec 2026-10-04 §7) ─────────


def test_gate_exige_request_sha256(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _solicitar(ctx)
    plantilla = (ctx.run_dir / "reporte" / "decision.template.yml").read_text(encoding="utf-8")
    assert f'request_sha256: "{pausa.request_sha256}"' in plantilla
    assert "approved: null" in plantilla
    assert "revisia run --resume" in pausa.message and "decision.template.yml" in pausa.message

    _decidir(ctx, "approved: true\nactor: human:x\n", pausa.request_sha256)  # sin el hash
    with pytest.raises(DecisionFileError, match="request_sha256"):
        _solicitar(ctx)
    assert ctx.ledger.read_all() == []


def test_decision_obsoleta_pausa_sin_aplicar(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    vieja = _solicitar(ctx, payload={"included": 1})
    _decidir(ctx, 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n', vieja.request_sha256)

    nueva = _solicitar(ctx, payload={"included": 2})  # la solicitud cambió

    assert nueva.status == "paused"
    assert nueva.request_sha256 != vieja.request_sha256
    assert "otra solicitud" in nueva.message
    assert ctx.ledger.read_all() == []  # no se aplicó nada
    solicitud = yaml.safe_load(
        (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")
    )
    assert solicitud["request_sha256"] == nueva.request_sha256


def test_ledger_idempotente_al_reanudar(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _solicitar(ctx)
    _decidir(ctx, 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n', pausa.request_sha256)
    for _ in range(3):  # tres reanudaciones con la misma decisión
        assert _solicitar(ctx).status == "approved"
    assert [e.action for e in ctx.ledger.read_all()] == ["approve"]

    # Cambiar de opinión es legítimo y queda registrado (D14).
    _decidir(
        ctx, 'request_sha256: "@SHA@"\napproved: false\nactor: human:x\n', pausa.request_sha256
    )
    assert _solicitar(ctx).status == "rejected"
    assert _solicitar(ctx).status == "rejected"
    assert [e.action for e in ctx.ledger.read_all()] == ["approve", "reject"]

    # auto-proceed (A2) tampoco se duplica.
    for _ in range(2):
        _solicitar(ctx, autonomy="A2")
    assert [e.action for e in ctx.ledger.read_all()].count("auto-proceed") == 1


def test_ledger_reconstruye_decision_sin_decision_yml(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _solicitar(ctx)
    _decidir(ctx, 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n', pausa.request_sha256)
    assert _solicitar(ctx).status == "approved"
    (ctx.run_dir / "reporte" / "decision.yml").unlink()  # el canal de entrada desaparece

    result = _solicitar(ctx)

    assert (result.status, result.actor) == ("approved", "human:x")  # el ledger manda
    assert len(ctx.ledger.read_all()) == 1
    # Una solicitud distinta no hereda esa decisión.
    assert _solicitar(ctx, payload={"included": 2}).status == "paused"


def test_request_sha256_recomputable_desde_yaml(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    payload = {"records": [{"record_id": "10.1/ñ", "votes": [{"label": "include"}]}], "n": 1}
    result = _solicitar(ctx, payload=payload)
    solicitud = yaml.safe_load(
        (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")
    )
    sha = solicitud.pop("request_sha256")
    assert sha == result.request_sha256 == canonical_sha256(solicitud)
    assert (solicitud["schema_version"], solicitud["stage"], solicitud["autonomy"]) == (
        1,
        "reporte",
        "A1",
    )
