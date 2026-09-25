"""Tests de la auditoría post-corrida (transparencia metodológica verificable)."""

from __future__ import annotations

import json

import yaml

from revisia.audit import render_audit_md, run_audit


def _make_run(
    tmp_path,
    *,
    human_decisions: bool = True,
    with_gold: bool = True,
    provenance: str | None = "pipeline",
):
    """Construye una corrida sintética completa en disco."""
    run = tmp_path / "runs" / "demo-20260705"
    deliverable = run / "deliverable"
    deliverable.mkdir(parents=True)
    manifest = {
        "slug": "demo",
        "timestamp": "20260705",
        "protocol": {
            "search_window": {"from": "2015-01-01", "to": "2026-12-31", "executed": "2026-07-05"},
            "registration": {"prospero": "CRD42026XXXXXX", "osf": ""},
        },
        "counts": {"identified": 10, "included": 2},
        "models_used": ["fake:fake-model"],
        "llm_calls": [
            {"provider": "fake", "model": "fake-model", "prompt_sha256": "abc123"},
            {"provider": "fake", "model": "fake-model", "prompt_sha256": "def456"},
        ],
    }
    if provenance is not None:
        manifest["provenance"] = provenance
    (run / "manifest.yml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
    )
    actor = "human:revisor" if human_decisions else "agent:screener"
    ledger_lines = [
        json.dumps(
            {
                "stage": "screening_ta",
                "actor": actor,
                "autonomy": "A1",
                "action": "approve",
                "timestamp_utc": "2026-07-05T00:00:00+00:00",
            }
        ),
        json.dumps(
            {
                "stage": "reporte",
                "actor": actor,
                "autonomy": "A1",
                "action": "approve",
                "timestamp_utc": "2026-07-05T00:10:00+00:00",
            }
        ),
    ]
    (run / "decisions_ledger.jsonl").write_text("\n".join(ledger_lines) + "\n", encoding="utf-8")
    for name in (
        "documento.md",
        "prisma_flow.md",
        "metodologia.md",
        "tabla_extraccion.md",
        "risk_of_bias.md",
        "referencias.bib",
        "checklist_2020.md",
        "checklist_traice.md",
    ):
        (deliverable / name).write_text("x", encoding="utf-8")
    screening = run / "03_screening"
    screening.mkdir(parents=True)
    (screening / "exclusions.json").write_text("{}", encoding="utf-8")
    if with_gold:
        (screening / "metrics.json").write_text(
            json.dumps({"recall": 1.0, "cohen_kappa": 0.75}), encoding="utf-8"
        )
    synthesis = run / "06_synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / "verification.json").write_text(
        json.dumps({"hallucination_flagged": False}), encoding="utf-8"
    )
    return run


def test_audit_corrida_completa_es_publicable(tmp_path) -> None:
    run = _make_run(tmp_path)
    report = run_audit(run)
    assert report.n_fail == 0
    assert report.publishable
    statuses = {c.check_id: c.status for c in report.checks}
    assert statuses["manifest"] == "PASS"
    assert statuses["prompts"] == "PASS"
    assert statuses["hitl"] == "PASS"
    assert statuses["deliverable"] == "PASS"
    assert statuses["gold"] == "PASS"
    assert statuses["registration"] == "PASS"
    assert statuses["final_gate"] == "PASS"
    markdown = render_audit_md(report)
    assert "APTA" in markdown
    assert "trAIce M8" in markdown


def test_audit_sin_decisiones_humanas_advierte_hitl(tmp_path) -> None:
    run = _make_run(tmp_path, human_decisions=False)
    report = run_audit(run)
    hitl = next(c for c in report.checks if c.check_id == "hitl")
    assert hitl.status == "WARN"
    assert "NO publicable sin revisión humana" in hitl.detail


def test_audit_sin_gold_advierte(tmp_path) -> None:
    run = _make_run(tmp_path, with_gold=False)
    report = run_audit(run)
    gold = next(c for c in report.checks if c.check_id == "gold")
    assert gold.status == "WARN"


def test_audit_corrida_vacia_falla(tmp_path) -> None:
    run = tmp_path / "runs" / "vacia"
    run.mkdir(parents=True)
    report = run_audit(run)
    assert report.n_fail >= 2  # manifest + ledger + deliverable
    assert not report.publishable
    assert "NO publicable" in render_audit_md(report)


def test_cli_audit_escribe_informe(tmp_path, capsys) -> None:
    from revisia.cli import main

    run = _make_run(tmp_path)
    assert main(["audit", str(run)]) == 0
    assert (run / "audit.md").exists()
    out = capsys.readouterr().out
    assert "APTA" in out

    empty = tmp_path / "runs" / "vacia"
    empty.mkdir(parents=True)
    assert main(["audit", str(empty)]) == 1


def test_audit_fails_on_reconstruction_provenance(tmp_path) -> None:
    report = run_audit(_make_run(tmp_path, provenance="reconstruction"))
    statuses = {c.check_id: c.status for c in report.checks}
    assert statuses["provenance"] == "FAIL"
    assert report.publishable is False


def test_audit_sin_procedencia_falla(tmp_path) -> None:
    report = run_audit(_make_run(tmp_path, provenance=None))
    check = next(c for c in report.checks if c.check_id == "provenance")
    assert check.status == "FAIL"
    assert "ausente" in check.detail


def test_audit_procedencia_pipeline_pasa(tmp_path) -> None:
    report = run_audit(_make_run(tmp_path))
    assert {c.check_id: c.status for c in report.checks}["provenance"] == "PASS"


def test_audit_sin_manifiesto_no_duplica_fail_de_procedencia(tmp_path) -> None:
    run = _make_run(tmp_path)
    (run / "manifest.yml").unlink()
    report = run_audit(run)
    assert "provenance" not in {c.check_id for c in report.checks}


def test_audit_sin_decision_de_reporte_falla_gate_final(tmp_path) -> None:
    run = _make_run(tmp_path)
    ledger = run / "decisions_ledger.jsonl"
    lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    only_screening = [line for line in lines if json.loads(line)["stage"] != "reporte"]
    ledger.write_text("\n".join(only_screening) + "\n", encoding="utf-8")

    report = run_audit(run)
    final_gate = next(c for c in report.checks if c.check_id == "final_gate")
    assert final_gate.status == "FAIL"
    assert "pausada o incompleta" in final_gate.detail
    assert report.publishable is False


def test_audit_reporte_rechazado_falla_gate_final(tmp_path) -> None:
    run = _make_run(tmp_path)
    ledger = run / "decisions_ledger.jsonl"
    lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    entries = [json.loads(line) for line in lines]
    for entry in entries:
        if entry["stage"] == "reporte":
            entry["action"] = "reject"
            entry["actor"] = "human:revisora"
    ledger.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")

    report = run_audit(run)
    final_gate = next(c for c in report.checks if c.check_id == "final_gate")
    assert final_gate.status == "FAIL"
    assert "rechazado" in final_gate.detail
    assert "human:revisora" in final_gate.detail
    assert report.publishable is False


def test_audit_reporte_aprobado_pasa_gate_final(tmp_path) -> None:
    report = run_audit(_make_run(tmp_path))
    final_gate = next(c for c in report.checks if c.check_id == "final_gate")
    assert final_gate.status == "PASS"
