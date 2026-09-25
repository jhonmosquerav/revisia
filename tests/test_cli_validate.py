"""`revisia validate` detiene el quickstart ante un modelo retirado (C4, D7)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from revisia import cli

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"


def _protocolo_con_modelo(tmp_path: Path, model: str) -> Path:
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    for cfg in raw["llm"].values():
        cfg["model"] = model
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return proto


def test_validate_exits_2_on_retired_model(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = cli.main(["validate", str(_protocolo_con_modelo(tmp_path, "gemini-2.0-flash"))])
    err = capsys.readouterr().err
    assert rc == 2
    assert "gemini-2.0-flash" in err
    assert "2026-06-01" in err


def test_validate_avisa_retiro_futuro_sin_fallar(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 9, 25))
    rc = cli.main(["validate", str(_protocolo_con_modelo(tmp_path, "gemini-2.5-flash"))])
    assert rc == 0
    assert "2026-10-16" in capsys.readouterr().out


def test_validate_plantilla_pasa(capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["validate", str(TEMPLATE_DIR)]) == 0


def test_check_usa_el_modelo_por_defecto_vigente() -> None:
    from revisia.llm.providers.gemini import DEFAULT_MODEL

    args = cli.build_parser().parse_args(["check", "manuscrito.md"])
    assert args.model == DEFAULT_MODEL
