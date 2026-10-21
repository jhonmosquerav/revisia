"""El CI cumple D25 (spec 2026-10-18 §12): matriz, permisos, lock, cobertura, acciones fijadas."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _pasos(job: str) -> list[dict]:
    return _workflow()["jobs"][job]["steps"]


def test_permisos_minimos_y_cuatro_jobs() -> None:
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    # PyYAML lee la clave `on` como True.
    disparadores = wf[True]
    assert disparadores["push"] == {"branches": ["main"]}
    assert not (disparadores["pull_request"] or {}).get("branches")  # PR apiladas también
    assert set(wf["jobs"]) == {"lint", "test", "build", "sdk-smoke"}
    assert wf["jobs"]["test"]["runs-on"] == "${{ matrix.os }}"


def test_matriz_seis_celdas_sin_fail_fast() -> None:
    estrategia = _workflow()["jobs"]["test"]["strategy"]
    assert estrategia["fail-fast"] is False
    assert estrategia["matrix"]["os"] == ["ubuntu-latest", "windows-latest"]
    assert estrategia["matrix"]["python"] == ["3.11", "3.12", "3.13"]


def test_acciones_fijadas_por_sha_y_uv_con_version() -> None:
    texto = CI.read_text(encoding="utf-8")
    usos = re.findall(r"uses:\s*(\S+)", texto)
    assert usos and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in usos)
    for paso in _pasos("test") + _pasos("lint") + _pasos("build") + _pasos("sdk-smoke"):
        if "setup-uv" in paso.get("uses", ""):
            assert paso["with"]["enable-cache"] is True
            assert re.fullmatch(r"\d+\.\d+\.\d+", str(paso["with"]["version"]))


def test_lint_comprueba_el_lock_y_el_formato() -> None:
    runs = " ".join(p.get("run", "") for p in _pasos("lint"))
    for orden in ("uv lock --check", "ruff check .", "ruff format --check .", "black --check ."):
        assert orden in runs


def test_pdf_solo_en_ubuntu_y_cobertura_solo_en_ubuntu_313() -> None:
    for paso in _pasos("test"):
        run = paso.get("run", "")
        cond = paso.get("if", "")
        if "--extra pdf" in run or "apt-get" in run or "weasyprint" in run:
            assert "Linux" in cond, run
        if "--cov" in run:
            assert "ubuntu-latest" in cond and "3.13" in cond, run
        if "cronometrado" in run and "not cronometrado" not in run and "--cov" in run:
            assert "--cov-fail-under=90" in run and "--cov-append" in run
    runs = " ".join(p.get("run", "") for p in _pasos("test"))
    assert "import httpx, pypdf, scipy" in runs and "--basetemp" in runs


def test_build_hace_humo_del_empaquetado() -> None:
    runs = " ".join(p.get("run", "") for p in _pasos("build"))
    assert "uv build" in runs and "zipfile -l" in runs and "rob/tools/RoB2" in runs
    assert "tarfile -l" in runs


def test_sdk_smoke_instala_los_tres_sdk_y_no_admite_saltos() -> None:
    job = _workflow()["jobs"]["sdk-smoke"]
    assert job["runs-on"] == "ubuntu-latest"
    runs = " ".join(p.get("run", "") for p in job["steps"])
    for extra in ("--extra gemini", "--extra openai", "--extra anthropic"):
        assert extra in runs
    paso = next(p for p in job["steps"] if "test_sdk_superficie" in p.get("run", ""))
    assert paso["env"]["REVISIA_SDK_SMOKE"] == "1"


def test_superficie_de_seguridad_del_workflow() -> None:
    texto = CI.read_text(encoding="utf-8")
    assert "pull_request_target" not in texto
    assert "secrets." not in texto
    for paso in [p for job in _workflow()["jobs"].values() for p in job["steps"]]:
        assert "${{ github.event" not in paso.get("run", "")
        if "checkout" in paso.get("uses", ""):
            assert paso["with"]["persist-credentials"] is False
    assert set(re.findall(r"uses:\s*(\S+)", texto)) == {
        "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
        "astral-sh/setup-uv@e58605a9b6da7c637471fab8847a5e5a6b8df081",
    }


def test_sdist_busca_runs_bajo_el_directorio_raiz_con_control_positivo() -> None:
    runs = " ".join(p.get("run", "") for p in _pasos("build"))
    assert "[^/]+/runs/" in runs and "/pyproject.toml" in runs
