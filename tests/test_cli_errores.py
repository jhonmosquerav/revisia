"""Errores de configuración y de decisión humana: mensaje, no traceback."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from revisia.cli import main
from revisia.orchestration.hitl import DecisionFileError

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "protocols" / "_TEMPLATE"
EXAMPLE = ROOT / "examples" / "demo-mini-review"


def _protocolo_con_autonomia(tmp_path: Path, stage: str, level: str) -> Path:
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["autonomy"][stage] = level
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return proto


def test_cli_validate_protocolo_con_a3_sale_2_sin_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = main(["validate", str(_protocolo_con_autonomia(tmp_path, "screening_ta", "A3"))])
    err = capsys.readouterr().err
    assert rc == 2
    assert "nunca superan A1" in err
    assert "Traceback" not in err


def test_cli_run_protocolo_con_a3_no_arranca(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_debe_correr(*_a, **_k):
        raise AssertionError("run_review no debe llamarse con un protocolo inválido")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _no_debe_correr)
    rc = main(["run", str(_protocolo_con_autonomia(tmp_path, "extraccion", "A2"))])
    assert rc == 2
    assert "nunca superan A1" in capsys.readouterr().err


def test_cli_run_decision_invalida_sale_2(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _falla(*_a, **_k):
        raise DecisionFileError("runs/x/reporte/decision.yml: está vacío.")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _falla)
    rc = main(["run", str(EXAMPLE)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "decision.yml" in err
    assert "Traceback" not in err


def test_cli_validate_yaml_roto_sale_2_sin_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    proto = tmp_path / "p"
    proto.mkdir()
    (proto / "protocol.yml").write_text("autonomy: [", encoding="utf-8")
    rc = main(["validate", str(proto)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "protocol.yml inválido" in err
    assert "Traceback" not in err


def test_cli_run_rechazado_sale_1_y_no_sedimenta(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from revisia.orchestration.pipeline import PipelineResult

    run_dir = tmp_path / "runs" / "demo-T"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "revisia.orchestration.flow.run_review",
        lambda *_a, **_k: PipelineResult(
            "rejected", "reporte: rechazado por human:x.", run_dir=run_dir
        ),
    )
    brain = tmp_path / "cerebro"
    rc = main(["run", str(EXAMPLE), "--brain", str(brain)])
    assert rc == 1
    assert "REJECTED" in capsys.readouterr().out
    assert list(brain.rglob("*.md")) == []  # una revisión rechazada no se sedimenta
