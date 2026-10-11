"""Tests de los helpers de ``tests/audit_fixtures.py`` (revisión de la Tarea C3).

Los helpers de edición rompen una corrida real para que cada test del auditor
pruebe una sola relación; si el helper rompe de más (p. ej. pisa el manifiesto
entero), el test del auditor pasaría o fallaría por un motivo ajeno. Por eso
los helpers tienen sus propios tests, sobre la corrida real (``corrida``) y sin
tocar lo que esta rama aún no produce (``llm_calls.jsonl``, diarios,
``00_protocol/``).
"""

from __future__ import annotations

import json
from pathlib import Path

import audit_fixtures
import pytest
import yaml
from audit_fixtures import (
    auditar,
    edit_json,
    edit_ledger,
    edit_yaml,
    editar_protocolo,
    escribir_metricas,
    fila,
)

from revisia.audit import AuditCheck, AuditReport


def _manifiesto(run: Path) -> dict:
    return yaml.safe_load((run / "manifest.yml").read_text(encoding="utf-8"))


def _metricas(run: Path) -> dict:
    return json.loads((run / "03_screening" / "metrics.json").read_text(encoding="utf-8"))


def _ledger(run: Path) -> list[dict]:
    texto = (run / "decisions_ledger.jsonl").read_text(encoding="utf-8")
    return [json.loads(linea) for linea in texto.splitlines() if linea]


# --- editar_protocolo --------------------------------------------------------


def test_editar_protocolo_pop_de_un_mapa_no_pisa_el_manifiesto(corrida) -> None:
    """``registration`` es un mapa: ``pop`` lo devuelve y, sin la envoltura, el
    manifiesto entero pasaba a ser ese mapa (``_apply`` toma un dict devuelto
    como documento de reemplazo)."""
    antes = _manifiesto(corrida)
    assert isinstance(antes["protocol"]["registration"], dict)

    editar_protocolo(corrida, lambda p: p.pop("registration"))

    despues = _manifiesto(corrida)
    assert "registration" not in despues["protocol"]
    assert despues["slug"] == antes["slug"]
    assert despues["counts"] == antes["counts"]
    assert despues["llm_calls"] == antes["llm_calls"]
    sin_protocolo = {k: v for k, v in despues.items() if k != "protocol"}
    assert sin_protocolo == {k: v for k, v in antes.items() if k != "protocol"}
    resto = {k: v for k, v in antes["protocol"].items() if k != "registration"}
    assert despues["protocol"] == resto


def test_editar_protocolo_setdefault_de_un_mapa_no_pisa_el_manifiesto(corrida) -> None:
    antes = _manifiesto(corrida)

    editar_protocolo(corrida, lambda p: p.setdefault("registration", {"osf": "otro"}))

    despues = _manifiesto(corrida)
    assert despues["protocol"] == antes["protocol"]  # ya existía: no cambia
    assert despues["counts"] == antes["counts"]


def test_editar_protocolo_muta_en_sitio_solo_el_protocolo(corrida) -> None:
    antes = _manifiesto(corrida)

    def _titulo(protocolo: dict) -> None:
        protocolo["title"] = "Título editado"

    editar_protocolo(corrida, _titulo)

    despues = _manifiesto(corrida)
    assert despues["protocol"]["title"] == "Título editado"
    assert despues["protocol"]["question"] == antes["protocol"]["question"]
    assert {k: v for k, v in despues.items() if k != "protocol"} == {
        k: v for k, v in antes.items() if k != "protocol"
    }


def test_editar_protocolo_ignora_el_valor_devuelto(corrida) -> None:
    """Un mapa devuelto no es un documento de reemplazo: ni pisa el manifiesto
    ni deja el protocolo reducido a ese mapa."""
    antes = _manifiesto(corrida)

    editar_protocolo(corrida, lambda _p: {"title": "no debe aplicarse"})

    assert _manifiesto(corrida) == antes


def test_editar_protocolo_sustituye_el_protocolo_completo_con_clear_y_update(corrida) -> None:
    antes = _manifiesto(corrida)
    nuevo = {"title": "Protocolo sustituto"}

    def _sustituir(protocolo: dict) -> None:
        protocolo.clear()
        protocolo.update(nuevo)

    editar_protocolo(corrida, _sustituir)

    despues = _manifiesto(corrida)
    assert despues["protocol"] == nuevo
    assert {k: v for k, v in despues.items() if k != "protocol"} == {
        k: v for k, v in antes.items() if k != "protocol"
    }


def test_editar_protocolo_sin_manifiesto_ni_instantanea_no_hace_nada(tmp_path) -> None:
    editar_protocolo(tmp_path, lambda p: p.pop("x"))  # no debe lanzar ni crear ficheros
    assert list(tmp_path.iterdir()) == []


# --- edit_json / edit_yaml ---------------------------------------------------


def test_edit_json_muta_en_sitio(corrida) -> None:
    ruta = corrida / "03_screening" / "metrics.json"
    antes = _metricas(corrida)

    edit_json(ruta, lambda m: m.update(recall=0.5))

    despues = _metricas(corrida)
    assert despues["recall"] == 0.5
    assert {k: v for k, v in despues.items() if k != "recall"} == {
        k: v for k, v in antes.items() if k != "recall"
    }


def test_edit_json_con_dict_devuelto_reemplaza_el_documento(corrida) -> None:
    ruta = corrida / "03_screening" / "metrics.json"

    edit_json(ruta, lambda _m: {"recall": 1.0})

    assert _metricas(corrida) == {"recall": 1.0}


def test_edit_json_ignora_un_valor_devuelto_que_no_es_mapa_ni_lista(corrida) -> None:
    """``lambda d: d.pop("k")`` con un escalar es una edición en sitio."""
    ruta = corrida / "03_screening" / "metrics.json"
    antes = _metricas(corrida)

    edit_json(ruta, lambda m: m.pop("recall"))  # devuelve un float

    assert _metricas(corrida) == {k: v for k, v in antes.items() if k != "recall"}


def test_edit_yaml_muta_en_sitio_y_conserva_el_orden_de_claves(corrida) -> None:
    ruta = corrida / "manifest.yml"
    antes = _manifiesto(corrida)

    edit_yaml(ruta, lambda m: m.update(provenance="reconstruction"))

    despues = _manifiesto(corrida)
    assert despues["provenance"] == "reconstruction"
    assert list(despues) == list(antes)
    assert despues["counts"] == antes["counts"]


def test_edit_yaml_con_dict_devuelto_reemplaza_el_documento(corrida) -> None:
    ruta = corrida / "manifest.yml"

    edit_yaml(ruta, lambda _m: {"slug": "otro"})

    assert _manifiesto(corrida) == {"slug": "otro"}


# --- edit_ledger -------------------------------------------------------------


def test_edit_ledger_muta_las_entradas_en_sitio(corrida) -> None:
    antes = _ledger(corrida)
    assert len(antes) == 9  # 5 aprobaciones + 4 etiquetas a texto completo (A0, D1)

    def _agente(entradas: list[dict]) -> None:
        for entrada in entradas:
            entrada["actor"] = "agent:screener"

    edit_ledger(corrida, _agente)

    despues = _ledger(corrida)
    assert len(despues) == len(antes)
    assert {e["actor"] for e in despues} == {"agent:screener"}
    assert [e["stage"] for e in despues] == [e["stage"] for e in antes]


def test_edit_ledger_con_lista_devuelta_reemplaza_las_entradas(corrida) -> None:
    antes = _ledger(corrida)

    edit_ledger(corrida, lambda entradas: [e for e in entradas if e["stage"] != "reporte"])

    despues = _ledger(corrida)
    assert len(despues) == len(antes) - 1
    assert "reporte" not in {e["stage"] for e in despues}
    texto = (corrida / "decisions_ledger.jsonl").read_text(encoding="utf-8")
    assert texto.endswith("\n")  # una línea JSON por entrada


# --- escribir_metricas -------------------------------------------------------


def test_escribir_metricas_sustituye_metrics_json(corrida) -> None:
    metricas = {"recall": 1.0, "cohen_kappa": None, "nota": "κ no calculable"}

    escribir_metricas(corrida, metricas)

    assert _metricas(corrida) == metricas
    # ensure_ascii=False: el texto no se escapa a \uXXXX.
    assert "κ" in (corrida / "03_screening" / "metrics.json").read_text(encoding="utf-8")


# --- auditar / fila ----------------------------------------------------------


def test_auditar_devuelve_el_informe_de_una_corrida_real(corrida) -> None:
    report = auditar(corrida)

    assert report.n_fail == 0
    ids = [c.check_id for c in report.checks]
    assert len(ids) == len(set(ids))  # una fila por check


def _informe(*checks: AuditCheck) -> AuditReport:
    return AuditReport(run_dir=Path("."), checks=list(checks))


def test_auditar_rechaza_un_na_sin_ningun_fail(monkeypatch, tmp_path) -> None:
    informe = _informe(
        AuditCheck("a", "x", "PASS", ""),
        AuditCheck("b", "x", "N/A", ""),
    )
    monkeypatch.setattr(audit_fixtures, "run_audit", lambda _run: informe)

    with pytest.raises(AssertionError, match="N/A sin ningún FAIL"):
        auditar(tmp_path)


def test_auditar_acepta_un_na_con_un_fail(monkeypatch, tmp_path) -> None:
    informe = _informe(
        AuditCheck("a", "x", "FAIL", ""),
        AuditCheck("b", "x", "N/A", ""),
    )
    monkeypatch.setattr(audit_fixtures, "run_audit", lambda _run: informe)

    assert auditar(tmp_path) is informe


def test_auditar_rechaza_filas_repetidas(monkeypatch, tmp_path) -> None:
    informe = _informe(
        AuditCheck("a", "x", "PASS", ""),
        AuditCheck("a", "x", "PASS", ""),
    )
    monkeypatch.setattr(audit_fixtures, "run_audit", lambda _run: informe)

    with pytest.raises(AssertionError, match="filas repetidas"):
        auditar(tmp_path)


def test_fila_devuelve_la_fila_pedida_y_falla_si_no_esta(corrida) -> None:
    report = auditar(corrida)

    assert fila(report, "manifest").check_id == "manifest"
    with pytest.raises(AssertionError, match="sin fila 'no-existe'"):
        fila(report, "no-existe")
