"""Tests de la auditoría post-corrida (transparencia metodológica verificable).

Corren sobre ``corrida`` (``tests/conftest.py``): una corrida real del
pipeline con decisiones humanas, copiada a ``tmp_path`` en cada test.
"""

from __future__ import annotations

import json

from audit_fixtures import auditar, edit_ledger, edit_yaml, fila

from revisia.audit import render_audit_md


def test_audit_corrida_completa_es_publicable(corrida) -> None:
    report = auditar(corrida)
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


def _sin_humanos(entries: list[dict]) -> None:
    for entry in entries:
        entry["actor"] = "agent:screener"


def test_audit_sin_decisiones_humanas_advierte_hitl(corrida) -> None:
    edit_ledger(corrida, _sin_humanos)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "WARN"
    assert "NO publicable sin revisión humana" in hitl.detail


def test_audit_sin_gold_advierte(corrida) -> None:
    (corrida / "03_screening" / "metrics.json").unlink()
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_corrida_vacia_falla(tmp_path) -> None:
    run = tmp_path / "runs" / "vacia"
    run.mkdir(parents=True)
    report = auditar(run)
    assert report.n_fail >= 2  # manifest + ledger + deliverable
    assert not report.publishable
    assert "NO publicable" in render_audit_md(report)


def test_cli_audit_escribe_informe(corrida, tmp_path, capsys) -> None:
    from revisia.cli import main

    assert main(["audit", str(corrida)]) == 0
    assert (corrida / "audit.md").exists()
    out = capsys.readouterr().out
    assert "APTA" in out

    empty = tmp_path / "runs" / "vacia"
    empty.mkdir(parents=True)
    assert main(["audit", str(empty)]) == 1


def test_audit_fails_on_reconstruction_provenance(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(provenance="reconstruction"))
    report = auditar(corrida)
    assert fila(report, "provenance").status == "FAIL"
    assert report.publishable is False


def _sin_procedencia(manifest: dict) -> None:
    del manifest["provenance"]


def test_audit_sin_procedencia_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", _sin_procedencia)
    check = fila(auditar(corrida), "provenance")
    assert check.status == "FAIL"
    assert "ausente" in check.detail


def test_audit_procedencia_pipeline_pasa(corrida) -> None:
    assert fila(auditar(corrida), "provenance").status == "PASS"


def test_audit_sin_manifiesto_no_duplica_fail_de_procedencia(corrida) -> None:
    # Una fila por check, siempre: la de procedencia sale N/A (su raíz, el
    # manifiesto, ya dio FAIL) en vez de omitirse o duplicar el FAIL.
    (corrida / "manifest.yml").unlink()
    report = auditar(corrida)
    assert fila(report, "manifest").status == "FAIL"
    assert fila(report, "provenance").status == "N/A"


def _sin_reporte(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e["stage"] != "reporte"]


def test_audit_sin_decision_de_reporte_falla_gate_final(corrida) -> None:
    edit_ledger(corrida, _sin_reporte)
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "pausada o incompleta" in final_gate.detail
    assert report.publishable is False


def _set_ultima_decision_reporte(run, *, action: str, actor: str) -> None:
    """Reescribe la entrada `reporte` del ledger de la corrida."""

    def _editar(entries: list[dict]) -> None:
        for entry in entries:
            if entry["stage"] == "reporte":
                entry["action"] = action
                entry["actor"] = actor

    edit_ledger(run, _editar)


def test_audit_reporte_rechazado_falla_gate_final(corrida) -> None:
    _set_ultima_decision_reporte(corrida, action="reject", actor="human:revisora")
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "rechazado" in final_gate.detail
    assert "human:revisora" in final_gate.detail
    assert report.publishable is False


def test_audit_reporte_aprobado_pasa_gate_final(corrida) -> None:
    assert fila(auditar(corrida), "final_gate").status == "PASS"


def test_audit_gate_final_auto_approve_no_es_humano_advierte(corrida) -> None:
    # `--auto-approve` sin decision.yml deja actor "auto-approve (demo)": no es
    # aprobación humana, así que no puede ser PASS (revisión final 2026-09-25).
    _set_ultima_decision_reporte(corrida, action="approve", actor="auto-approve (demo)")
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "WARN"
    assert "no lo aprobó un humano" in final_gate.detail
    assert "auto-approve (demo)" in final_gate.detail
    assert report.publishable  # WARN no bloquea publicabilidad, a diferencia de FAIL


def test_audit_gate_final_auto_proceed_advierte(corrida) -> None:
    # `reporte` en A2/A3 se auto-ejecuta y notifica (agent:reporte): tampoco es
    # una decisión humana.
    _set_ultima_decision_reporte(corrida, action="auto-proceed", actor="agent:reporte")
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "WARN"
    assert "no lo aprobó un humano" in final_gate.detail
    assert "agent:reporte" in final_gate.detail


def test_audit_gate_final_accion_desconocida_falla(corrida) -> None:
    _set_ultima_decision_reporte(corrida, action="otra-cosa", actor="human:revisor")
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "Acción desconocida" in final_gate.detail
    assert "otra-cosa" in final_gate.detail


def test_audit_sin_ledger_no_duplica_fail_de_final_gate(corrida) -> None:
    # El ledger ausente ya produce un FAIL propio (§3); final_gate no debe
    # añadir un segundo FAIL redundante (mismo criterio que "provenance" con
    # manifest ausente).
    (corrida / "decisions_ledger.jsonl").unlink()
    report = auditar(corrida)
    assert fila(report, "final_gate").status == "N/A"
    assert fila(report, "ledger").status == "FAIL"


def test_audit_ledger_vacio_no_duplica_fail_de_final_gate(corrida) -> None:
    (corrida / "decisions_ledger.jsonl").write_text("", encoding="utf-8")
    report = auditar(corrida)
    assert fila(report, "final_gate").status == "N/A"
    assert fila(report, "ledger").status == "FAIL"


def _escribir_metricas(run, metrics: dict) -> None:
    (run / "03_screening" / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")


def test_audit_gold_kappa_no_calculable_advierte(corrida) -> None:
    _escribir_metricas(corrida, {"recall": 1.0, "cohen_kappa": None})
    gold = fila(auditar(corrida), "gold")
    assert gold.status == "WARN"  # antes: PASS con κ inventado
    assert "no calculable" in gold.detail


def test_audit_gold_matriz_con_valor_null_advierte(corrida) -> None:
    """``tp``/``fp``/``fn``/``tn`` presentes pero con algún valor ``null`` (no
    numérico): la matriz debe tratarse como ilegible en vez de romper la
    auditoría con un TypeError al sumar ``None`` con ``int``."""
    _escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.5, "mcc": 0.4, "tp": None, "fp": 2, "fn": 0, "tn": 0},
    )
    gold = fila(auditar(corrida), "gold")
    assert gold.status == "WARN"
    assert "matriz de confusión ilegible" in gold.detail


def test_audit_ia_una_sola_clase_con_gold_mixto_advierte(corrida) -> None:
    """Caso A11 (decisión D6): con matriz (tp=3, fp=2, fn=0, tn=0) el gold es
    mixto (3 relevantes, 2 irrelevantes) pero la IA asignó una sola clase
    (siempre "relevante": fn+tn=0) — kappa=0.0 (no None) y mcc=None no debe
    pasar como PASS; hay que mirar mcc y la matriz, no solo κ."""
    _escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.0, "mcc": None, "tp": 3, "fp": 2, "fn": 0, "tn": 0},
    )
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_una_sola_clase_con_matriz_advierte(corrida) -> None:
    """Caso real de los ``metrics.json`` de v0.6.0: matriz completa con gold de
    una sola clase (todo relevante: tp=3, fn=2, fp=0, tn=0 → tn+fp == 0), con
    mcc=0.0 y kappa numérico (ninguno de los dos es None). El chequeo de
    ``gold_una_sola_clase`` sobre la matriz debe advertir igual, porque un
    gold sin la clase "irrelevante" no es informativo aunque mcc/kappa den
    un número."""
    _escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.0, "mcc": 0.0, "tp": 3, "fp": 0, "fn": 2, "tn": 0},
    )
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_mcc_none_formato_antiguo_sin_matriz_advierte(corrida) -> None:
    """``metrics.json`` de formato antiguo (sin tp/fp/fn/tn): sin matriz no se
    puede evaluar si el gold o la IA son de una sola clase, así que la
    decisión se apoya solo en que mcc esté explícitamente en null; sigue
    siendo WARN."""
    _escribir_metricas(corrida, {"recall": 1.0, "cohen_kappa": 0.42, "mcc": None})
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_sano_con_matriz_completa_pasa(corrida) -> None:
    _escribir_metricas(
        corrida,
        {"recall": 0.8, "cohen_kappa": 0.75, "mcc": 0.6, "tp": 4, "fp": 1, "fn": 1, "tn": 4},
    )
    assert fila(auditar(corrida), "gold").status == "PASS"
