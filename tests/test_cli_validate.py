"""`revisia validate`/`run`: modelos retirados (C4, D7) y preflight sin red (M6, D10)."""

from __future__ import annotations

import os
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from revisia import cli
from revisia.llm import preflight as preflight_mod

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"


@pytest.fixture()
def entorno_listo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Máquina "configurada": key de Gemini, SDKs y httpx instalados, sin .env real.

    La plantilla usa Gemini y bases con backend: sin esto, el preflight (M6)
    daría rc 2 por el entorno del venv de pruebas, no por el protocolo.
    """
    monkeypatch.setattr(cli, "_load_dotenv", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(preflight_mod, "_default_find_spec", lambda _name: object())


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
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    entorno_listo: None,
) -> None:
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 9, 25))
    rc = cli.main(["validate", str(_protocolo_con_modelo(tmp_path, "gemini-3.1-flash-lite"))])
    assert rc == 0
    assert "2027-05-07" in capsys.readouterr().out


def test_validate_plantilla_pasa(capsys: pytest.CaptureFixture, entorno_listo: None) -> None:
    assert cli.main(["validate", str(TEMPLATE_DIR)]) == 0


def test_check_usa_el_modelo_por_defecto_vigente() -> None:
    from revisia.llm.providers.gemini import DEFAULT_MODEL

    args = cli.build_parser().parse_args(["check", "manuscrito.md"])
    assert args.model == DEFAULT_MODEL


def test_run_con_modelo_retirado_sale_2_y_no_ejecuta_run_review(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El quickstart (README) va directo a `run`: el 404 de un modelo retirado
    (C4) debe atajarse aquí, no solo en `validate` (revisión final, ítem 3)."""

    def _no_debe_correr(*_a, **_k):
        raise AssertionError("run_review no debe llamarse con un modelo retirado")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _no_debe_correr)
    rc = cli.main(["run", str(_protocolo_con_modelo(tmp_path, "gemini-2.0-flash"))])
    err = capsys.readouterr().err
    assert rc == 2
    assert "gemini-2.0-flash" in err
    assert "2026-06-01" in err


def test_run_con_modelo_por_retirarse_avisa_y_ejecuta(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    entorno_listo: None,
) -> None:
    from revisia.orchestration.pipeline import PipelineResult

    run_dir = tmp_path / "runs" / "demo-T"
    (run_dir / "deliverable").mkdir(parents=True)
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 9, 25))
    monkeypatch.setattr(
        "revisia.orchestration.flow.run_review",
        lambda *_a, **_k: PipelineResult("completed", "ok", run_dir=run_dir),
    )
    rc = cli.main(["run", str(_protocolo_con_modelo(tmp_path, "gemini-3.1-flash-lite"))])
    out = capsys.readouterr().out
    assert rc == 0
    assert "2027-05-07" in out


@pytest.mark.parametrize("comando", ["validate", "run"])
def test_umbral_no_finito_sale_2_en_validate_y_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    entorno_listo: None,
    comando: str,
) -> None:
    # `wmcc_fn_weight: .nan` cargaba, y el cribado reventaba con rc 3 en bucle (el WMCC nan no
    # se puede volcar a JSON). Ahora el protocolo no carga: error de uso, rc 2, ya en `validate`.
    def _no_debe_correr(*_a, **_k):
        raise AssertionError("run_review no debe llamarse con un umbral no finito")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _no_debe_correr)
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    ficha = proto / "protocol.yml"
    raw = yaml.safe_load(ficha.read_text(encoding="utf-8"))
    raw["thresholds"]["wmcc_fn_weight"] = float("nan")
    ficha.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")

    rc = cli.main([comando, str(proto)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "protocol.yml inválido" in err
    assert "thresholds.wmcc_fn_weight" in err and "no es un número finito" in err
    assert "Traceback" not in err


def test_validate_detecta_retirado_con_prefijo_de_openrouter(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    proto = _protocolo_con_modelo(tmp_path, "google/gemini-2.0-flash-001")
    rc = cli.main(["validate", str(proto)])
    assert rc == 2
    assert "google/gemini-2.0-flash-001" in capsys.readouterr().err


# ── Preflight en el CLI (auditoría 2026-09-03, M6; spec 2026-10-04 §5) ──────


def _protocolo_sin_proveedor_ft(tmp_path: Path) -> Path:
    """Protocolo que carga pero no puede correr: solo T/A tiene proveedor."""
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["llm"] = {"screening_ta": {"provider": "fake", "model": "fake-1"}}
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return proto


def test_cli_validate_sale_2_con_error_de_preflight(
    tmp_path: Path, capsys: pytest.CaptureFixture, entorno_listo: None
) -> None:
    # M6: antes devolvía 0 e imprimía "(sin proveedor)".
    rc = cli.main(["validate", str(_protocolo_sin_proveedor_ft(tmp_path))])
    captured = capsys.readouterr()
    assert rc == 2
    assert "screening_ft" in captured.err
    assert "Protocolo válido" not in captured.out


def test_cli_run_preflight_falla_sin_crear_runs_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    entorno_listo: None,
) -> None:
    def _no_debe_correr(*_a, **_k):
        raise AssertionError("run_review no debe llamarse si el preflight falla")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _no_debe_correr)
    runs_root = tmp_path / "runs"
    proto = _protocolo_sin_proveedor_ft(tmp_path)
    rc = cli.main(["run", str(proto), "--runs-root", str(runs_root)])
    assert rc == 2
    assert "screening_ft" in capsys.readouterr().err
    assert not runs_root.exists()


def test_cli_carga_dotenv_sin_sobrescribir_el_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "REVISIA_PRUEBA_DOTENV=desde-dotenv\nGEMINI_API_KEY=desde-dotenv\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "del-entorno")
    # setenv + delenv: la variable no existe, pero monkeypatch la borrará al
    # terminar aunque la cree load_dotenv (no se filtra a otros tests).
    monkeypatch.setenv("REVISIA_PRUEBA_DOTENV", "provisional")
    monkeypatch.delenv("REVISIA_PRUEBA_DOTENV")

    assert cli.main(["brain", str(tmp_path / "sin-cerebro")]) == 1  # cualquier subcomando

    assert os.environ["REVISIA_PRUEBA_DOTENV"] == "desde-dotenv"
    assert os.environ["GEMINI_API_KEY"] == "del-entorno"  # override=False
