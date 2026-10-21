"""Lo que `pyproject.toml` y `uv.lock` declaran para la matriz del CI (spec 2026-10-18 §12, D25)."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_requires_python_311_y_classifiers() -> None:
    project = _pyproject()["project"]
    assert project["requires-python"] == ">=3.11"
    for version in ("3.11", "3.12", "3.13"):
        assert f"Programming Language :: Python :: {version}" in project["classifiers"]


def test_herramientas_apuntan_a_py311() -> None:
    tool = _pyproject()["tool"]
    assert tool["ruff"]["target-version"] == "py311"
    assert tool["black"]["target-version"] == ["py311"]


def test_pytest_cov_en_dev_y_cobertura_con_cota_90() -> None:
    data = _pyproject()
    dev = data["project"]["optional-dependencies"]["dev"]
    assert any(d.startswith("pytest-cov") for d in dev)
    assert data["tool"]["coverage"]["run"]["source"] == ["revisia"]
    assert "omit" not in data["tool"]["coverage"]["run"]
    assert data["tool"]["coverage"]["report"]["fail_under"] == 90


def test_uv_lock_resuelto_para_311() -> None:
    cabecera = (ROOT / "uv.lock").read_text(encoding="utf-8")[:400]
    assert 'requires-python = ">=3.11"' in cabecera
