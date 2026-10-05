"""La reconstrucción C3 deja de ser publicable, y por más de una vía.

Auditoría 2026-09-03, C3: la corrida fundacional era una reconstrucción y el
auditor la declaraba "APTA". La Ola 0 añadió ``provenance: pipeline``, que se
falsifica con una línea; la Ola 1 exige que la corrida no sea publicable aunque
la procedencia esté falsificada, por al menos siete checks independientes, y
que cada síntoma, aplicado solo a una corrida coherente, baste (spec
2026-10-04 §9.4 y §11).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from audit_fixtures import (
    auditar,
    comprimir_llamadas,
    edit_json,
    edit_ledger,
    edit_yaml,
    fila,
    write_c3_reconstruction,
)

VIAS_C3 = {"schemas", "ledger", "timing", "hitl", "stage_artifacts", "arithmetic", "final_gate"}


def test_audit_c3_reconstruccion_no_es_publicable_por_varias_vias(tmp_path) -> None:
    report = auditar(write_c3_reconstruction(tmp_path, provenance="pipeline"))
    fails = {c.check_id for c in report.checks if c.status == "FAIL"}
    assert fails >= VIAS_C3
    assert len(fails) >= 7
    assert fila(report, "provenance").status == "PASS"  # la marca falsificada no basta
    assert not report.publishable


def test_audit_c3_con_su_procedencia_real_tambien_falla_provenance(tmp_path) -> None:
    report = auditar(write_c3_reconstruction(tmp_path, provenance="reconstruction"))
    assert fila(report, "provenance").status == "FAIL"
    assert {c.check_id for c in report.checks if c.status == "FAIL"} >= VIAS_C3


def _accion_desconocida(run: Path) -> None:
    edit_ledger(
        run,
        lambda e: [{**e[0], "action": "propose", "actor": "agent:opus+sonnet"}, *e],
    )


def _metricas_sin_matriz(run: Path) -> None:
    edit_json(
        run / "03_screening" / "metrics.json",
        lambda _m: {"n": 47, "recall": 1.0, "mcc": 0.71, "cohen_kappa": 0.75},
    )


def _sin_04_fulltext(run: Path) -> None:
    shutil.rmtree(run / "04_fulltext")


def _excluded_human_3(run: Path) -> None:
    edit_json(run / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=3))


def _ledger_una_semana_antes(run: Path) -> None:
    def _editar(entries: list[dict]) -> None:
        for entry in entries:
            marca = datetime.fromisoformat(entry["timestamp_utc"]) - timedelta(days=7)
            entry["timestamp_utc"] = marca.isoformat()

    edit_ledger(run, _editar)


def _fuentes_40_40_40(run: Path) -> None:
    fuentes = {"OpenAlex": 40, "Crossref": 40, "Europe PMC": 40}
    edit_yaml(run / "manifest.yml", lambda m: m["counts"].update(identified_by_source=fuentes))


SINTOMAS: list = [
    pytest.param(_accion_desconocida, "ledger", "FAIL", id="accion-desconocida"),
    pytest.param(_metricas_sin_matriz, "schemas", "FAIL", id="metricas-sin-matriz"),
    pytest.param(_sin_04_fulltext, "stage_artifacts", "FAIL", id="falta-04-fulltext"),
    pytest.param(_excluded_human_3, "hitl", "FAIL", id="excluded-human-3"),
    pytest.param(_ledger_una_semana_antes, "timing", "FAIL", id="ledger-una-semana-antes"),
    pytest.param(_fuentes_40_40_40, "arithmetic", "FAIL", id="identified-by-source-40-40-40"),
    # Una heurística temporal nunca basta sola: 1,3 ms es WARN.
    pytest.param(comprimir_llamadas, "timing", "WARN", id="llamadas-en-1-3-ms-solo-advierte"),
]


@pytest.mark.parametrize(("sintoma", "check_id", "esperado"), SINTOMAS)
def test_audit_c3_cada_sintoma_basta_solo(
    corrida, sintoma: Callable[[Path], None], check_id: str, esperado: str
) -> None:
    assert auditar(corrida).publishable  # la corrida coherente de partida
    sintoma(corrida)
    report = auditar(corrida)
    assert fila(report, check_id).status == esperado
    assert report.publishable is (esperado != "FAIL")
