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
    # Cada vía FAIL por lo que ve en los artefactos, no porque el auditor reviente.
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []


def test_audit_c3_con_su_procedencia_real_tambien_falla_provenance(tmp_path) -> None:
    report = auditar(write_c3_reconstruction(tmp_path, provenance="reconstruction"))
    assert fila(report, "provenance").status == "FAIL"
    assert {c.check_id for c in report.checks if c.status == "FAIL"} >= VIAS_C3
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []


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


def _sin_solicitud_del_reporte(run: Path) -> None:
    (run / "reporte" / "review_request.yml").unlink()


# (síntoma, fila, estado esperado, fragmento del detalle de esa fila): el fragmento fija que la
# fila falla por lo que debe y no por otra causa.
SINTOMAS: list = [
    pytest.param(_accion_desconocida, "ledger", "FAIL", "propose", id="accion-desconocida"),
    pytest.param(_metricas_sin_matriz, "schemas", "FAIL", "metrics.json", id="metricas-sin-matriz"),
    pytest.param(
        _sin_04_fulltext, "stage_artifacts", "FAIL", "04_fulltext", id="falta-04-fulltext"
    ),
    pytest.param(_excluded_human_3, "hitl", "FAIL", "exclusiones humanas", id="excluded-human-3"),
    pytest.param(
        _ledger_una_semana_antes,
        "timing",
        "FAIL",
        "anterior al inicio",
        id="ledger-una-semana-antes",
    ),
    pytest.param(_fuentes_40_40_40, "arithmetic", "FAIL", "Σ", id="identified-by-source-40-40-40"),
    pytest.param(
        _sin_solicitud_del_reporte,
        "final_gate",
        "FAIL",
        "review_request.yml",
        id="reporte-sin-solicitud",
    ),
    # Una heurística temporal nunca basta sola: 1,3 ms es WARN.
    pytest.param(
        comprimir_llamadas, "timing", "WARN", "mediana", id="llamadas-en-1-3-ms-solo-advierte"
    ),
]


@pytest.mark.parametrize(("sintoma", "check_id", "esperado", "fragmento"), SINTOMAS)
def test_audit_c3_cada_sintoma_basta_solo(
    corrida, sintoma: Callable[[Path], None], check_id: str, esperado: str, fragmento: str
) -> None:
    assert auditar(corrida).publishable  # la corrida coherente de partida
    sintoma(corrida)
    report = auditar(corrida)
    assert fila(report, check_id).status == esperado
    assert fragmento in fila(report, check_id).detail
    assert report.publishable is (esperado != "FAIL")


def test_audit_c3_una_aprobacion_final_sin_solicitud_falla_solo_final_gate(corrida) -> None:
    # La reconstrucción escribía un `approve` humano de `reporte` sin pasar por el gate: quitar
    # `reporte/review_request.yml` de una corrida coherente deja ESA fila como única en FAIL.
    assert auditar(corrida).publishable
    _sin_solicitud_del_reporte(corrida)
    report = auditar(corrida)
    assert {c.check_id for c in report.checks if c.status == "FAIL"} == {"final_gate"}
    assert not report.publishable
