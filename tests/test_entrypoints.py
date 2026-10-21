"""Entrypoints de ejecución (auditoría 2026-09-03, A13): flow, agent_driver y CLI, offline.

Lo que ya cubrían otros ficheros no se repite: `new` (`test_flow_oficial_y_check.py:145,152`),
`export` (`test_export_document.py:218-234`), `check` (`test_flow_oficial_y_check.py:164`),
`audit` (`test_audit.py:78,85`), `validate` con protocolos inválidos (`test_cli_validate.py`) y
el rc 3 de `run` (`test_cli_reanudacion.py::test_cli_interrupcion_rc_3_con_instrucciones`, en
proceso: un fallo transitorio no se reproduce en un subproceso sin red).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from fakes import protocolo_offline
from hitl_helpers import responder_gate

from revisia.agent_driver import run_review_with_agent
from revisia.cli import main
from revisia.llm.providers.fake import _fabricate_model
from revisia.orchestration.flow import resume_review, run_review
from revisia.provenance.ledger import DecisionLedger

ROOT = Path(__file__).resolve().parent.parent
_CLI = "import sys; from revisia.cli import main; sys.exit(main(sys.argv[1:]))"


@pytest.fixture(autouse=True)
def _sin_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("revisia.cli._load_dotenv", lambda: None)


def test_protocolo_offline_no_declara_fuentes_con_backend(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    assert raw["databases"] == ["Scopus"]
    assert (proto / "imported" / "corpus.ris").read_text(encoding="utf-8").count("ER  -") == 2
    assert not (proto / "search_strings").exists() and not (proto / "effects.yml").exists()
    assert {c["provider"] for c in raw["llm"].values()} == {"fake"}


def test_run_review_de_punta_a_punta_sin_red(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    result = run_review(proto, timestamp="T", runs_root=tmp_path / "runs", auto_approve=True)
    assert result.status == "completed"
    assert result.counts is not None and result.counts.identified == 2
    assert result.counts.fulltext_not_retrieved == 2 and result.counts.included == 0
    run_dir = result.run_dir
    assert run_dir.parent == tmp_path / "runs"
    assert (run_dir / "run.json").exists() and (run_dir / "manifest.yml").exists()
    log = json.loads((run_dir / "01_search" / "log.json").read_text(encoding="utf-8"))
    assert {e["kind"] for e in log["entries"]} == {"database", "manual_import"}
    assert all(e["status"] in {"manual_only", "ok"} for e in log["entries"])


def test_run_review_pausa_en_el_gate_y_resume_review_continua(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    pausa = run_review(proto, timestamp="T", runs_root=tmp_path / "runs", auto_approve=False)
    assert (pausa.status, pausa.stage) == ("paused", "screening_ta")
    responder_gate(pausa.run_dir, "screening_ta")
    final = resume_review(pausa.run_dir, protocol_dir=proto, auto_approve=True)
    assert final.status == "completed"
    acciones = [
        e.action for e in DecisionLedger(pausa.run_dir / "decisions_ledger.jsonl").read_all()
    ]
    assert acciones[0] in {"label", "approve"} and "approve" in acciones


def _callback(req, schema):
    return _fabricate_model(schema) if schema is not None else "Síntesis de prueba del agente."


def test_agent_driver_sin_auto_approve_pausa_en_el_primer_gate(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p", provider="agent", model="session-agent")
    result = run_review_with_agent(
        proto, _callback, timestamp="T", runs_root=tmp_path / "runs", auto_approve=False
    )
    assert (result.status, result.stage) == ("paused", "screening_ta")
    ledger = DecisionLedger(result.run_dir / "decisions_ledger.jsonl").read_all()
    assert not any(e.action == "approve" for e in ledger)


def test_agent_driver_con_auto_approve_explicito_completa_y_reanuda(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p", provider="agent", model="session-agent")
    result = run_review_with_agent(
        proto, _callback, timestamp="T", runs_root=tmp_path / "runs", auto_approve=True
    )
    assert result.status == "completed"
    otra = run_review_with_agent(None, _callback, run_dir=result.run_dir, auto_approve=True)
    assert otra.status == "completed" and otra.run_dir == result.run_dir


def test_cli_gold_template_desde_una_corrida(corrida: Path, tmp_path: Path, capsys) -> None:
    out = tmp_path / "gold_template.yml"
    assert main(["gold-template", str(corrida), "--out", str(out)]) == 0
    texto = out.read_text(encoding="utf-8")
    assert texto.startswith("# gold.yml") and "\ngold:\n" in texto
    ids = json.loads((corrida / "03_screening" / "decisions.json").read_text(encoding="utf-8"))
    assert texto.count('  # "') == len({d["record_id"] for d in ids})
    assert "Plantilla gold" in capsys.readouterr().out
    assert main(["gold-template", str(tmp_path / "sin-corrida")]) == 2
    assert "decisions.json" in capsys.readouterr().err


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _CLI, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def test_cli_run_en_subproceso_sale_0_y_deja_la_corrida(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    runs = tmp_path / "runs"
    proc = _run_cli("run", str(proto), "--auto-approve", "--runs-root", str(runs), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "COMPLETED" in proc.stdout and "Traceback" not in proc.stderr
    corridas = list(runs.iterdir())
    assert len(corridas) == 1 and (corridas[0] / "manifest.yml").exists()


def test_cli_run_en_subproceso_sale_2_con_a3_en_una_etapa_de_juicio(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw.setdefault("autonomy", {})["screening_ta"] = "A3"
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    proc = _run_cli(
        "run", str(proto), "--auto-approve", "--runs-root", str(tmp_path / "runs"), cwd=tmp_path
    )
    assert proc.returncode == 2 and "A3" in proc.stderr and "Traceback" not in proc.stderr
    assert not (tmp_path / "runs").exists()


def test_cli_validate_del_protocolo_offline_sale_0(tmp_path: Path, capsys) -> None:
    proto = protocolo_offline(tmp_path / "p")
    assert main(["validate", str(proto)]) == 0
    salida = capsys.readouterr()
    assert salida.out and "error" not in salida.err.lower()
