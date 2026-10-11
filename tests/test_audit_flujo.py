"""Checks del flujo PRISMA: ``stage_artifacts``, ``arithmetic``, ``exclusions``, ``deliverable``.

Spec 2026-10-04 §4.4 y §9.3 (filas 11-14). Cada caso de ``arithmetic`` rompe
una sola relación de la corrida real y comprueba que el auditor la nombra.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from audit_fixtures import (
    auditar,
    auditar_en_subproceso,
    bomba_de_alias,
    edit_json,
    edit_yaml,
    editar_llamadas,
    editar_protocolo,
    fila,
    write_legacy_v07,
)

from revisia.audit import CHECKS
from revisia.audit.artifacts import AuditContext, load_run
from revisia.audit.checks_flow import _limitar, collect_relations
from revisia.exports import PrismaCounts

TA = "03_screening/decisions.json"
FT = "04_fulltext/decisions.json"


def _counts(**cambios) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        edit_yaml(run / "manifest.yml", lambda m: m["counts"].update(cambios))

    return _editar


def _json(rel: str, fn: Callable) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        edit_json(run / rel, fn)

    return _editar


def _csv(clave: str, valor: str) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        path = run / "deliverable" / "interop" / "prisma2020_flow.csv"
        rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
        header = rows[0]
        for row in rows[1:]:
            if row[header.index("data")] == clave:
                row[header.index("n")] = valor
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        path.write_text(buf.getvalue(), encoding="utf-8")

    return _editar


def _decision(rid: str, **cambios) -> Callable[[list[dict]], None]:
    def _editar(decisions: list[dict]) -> None:
        for decision in decisions:
            if decision["record_id"] == rid:
                decision.update(cambios)

    return _editar


def _sin_clave(clave: str) -> Callable[[dict], None]:
    def _editar(data: dict) -> None:
        del data[clave]

    return _editar


def _sin_la_ultima(decisions: list[dict]) -> None:
    del decisions[-1]


def _herramienta_rob(assessments: dict) -> None:
    for assessment in assessments.values():
        assessment["tool"] = "ROBINS-I"


RELACIONES_ROTAS = [
    pytest.param(
        _counts(identified_by_source={"OpenAlex": 40, "Crossref": 40, "Europe PMC": 40}),
        "1 · Σ identified_by_source == identified",
        id="identified_by_source-40-40-40",
    ),
    pytest.param(_counts(duplicates_removed=0), "4 · screened", id="duplicados"),
    pytest.param(
        _json(TA, _sin_la_ultima), "5 · len(03_screening/decisions.json)", id="ta-de-menos"
    ),
    pytest.param(
        _json(TA, _decision("10.1000/cocina", ensemble_label="unclear", final_label="unclear")),
        "5 · ensemble_label == recall_biased_label",
        id="ensemble-manipulado",
    ),
    pytest.param(
        _json(TA, _decision("10.1000/cocina", final_label="include")),
        "5 · final_label == human_label or ensemble_label",
        id="final-sin-humano",
    ),
    pytest.param(_counts(excluded_ta=3), "6 · excluded_ta ==", id="excluded-ta"),
    pytest.param(_counts(excluded_ta_ai=1), "6 · excluded_ta_human + excluded_ta_ai", id="ta-h-ia"),
    pytest.param(
        _json(FT, _decision("10.1000/asreview", record_id="10.1000/otro")),
        "7 · ids de 04_fulltext == pasan T/A",
        id="ids-ft",
    ),
    pytest.param(_counts(excluded_ft=2), "9 · excluded_ft ==", id="excluded-ft"),
    pytest.param(
        _counts(ft_exclusion_reasons={"fuera de alcance": 2}),
        "9 · Σ ft_exclusion_reasons",
        id="razones-ft",
    ),
    pytest.param(_counts(included=4), "10 · included == fulltext_assessed", id="included"),
    pytest.param(
        _json("05_extraction/extractions.json", _sin_clave("10.1000/llm-1")),
        "10 · claves de 05_extraction/extractions.json",
        id="extracciones",
    ),
    pytest.param(
        _json("07_rob/assessments.json", _sin_clave("10.1000/llm-1")),
        "10 · claves de 07_rob/assessments.json",
        id="evaluaciones",
    ),
    pytest.param(
        _json("03_screening/exclusions.json", lambda e: e.update(total_excluded=5)),
        "10 · exclusions.total_excluded",
        id="total-excluidos",
    ),
    pytest.param(_csv("records_screened", "9"), "11 · CSV records_screened", id="csv"),
    pytest.param(
        _json("07_rob/assessments.json", _herramienta_rob),
        "§9.3 · assessment.tool == protocol.rob_tool",
        id="herramienta-rob",
    ),
    pytest.param(
        _json("05_extraction/agreement.json", lambda a: a.update(n_studies=2)),
        "§9.3 · extraction_agreement.n_studies",
        id="doble-extraccion",
    ),
]


@pytest.mark.parametrize(("romper", "relacion"), RELACIONES_ROTAS)
def test_arithmetic_cada_relacion_rota_falla(corrida, romper, relacion: str) -> None:
    romper(corrida)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert relacion in arithmetic.detail


def test_arithmetic_corrida_real_pasa(corrida) -> None:
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "PASS"
    assert "relaciones verificadas" in arithmetic.detail


def test_arithmetic_corrida_v07_usa_las_relaciones_v07(tmp_path) -> None:
    report = auditar(write_legacy_v07(tmp_path))
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "PASS"
    assert "relaciones v0.7: corrida sin run.json" in arithmetic.detail


def test_corrida_v07_cumple_las_cuatro_filas_del_flujo(tmp_path) -> None:
    # La corrida de referencia es coherente de punta a punta, no solo en `arithmetic`.
    report = auditar(write_legacy_v07(tmp_path))
    for check_id in ("stage_artifacts", "arithmetic", "exclusions", "deliverable"):
        assert fila(report, check_id).status == "PASS", (check_id, fila(report, check_id).detail)


def test_corrida_v07_de_referencia_tiene_la_forma_documentada(tmp_path) -> None:
    run = write_legacy_v07(tmp_path)
    manifest = yaml.safe_load((run / "manifest.yml").read_text(encoding="utf-8"))
    ledger = (run / "decisions_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert not (run / "run.json").exists()  # anterior a la Ola 1
    assert manifest["counts"]["identified"] == 5
    assert manifest["counts"]["duplicates_removed"] == 1
    assert manifest["counts"]["included"] == 2
    assert len(manifest["llm_calls"]) == 12
    assert len(ledger) == 5
    assert all(json.loads(line)["actor"].startswith("human:") for line in ledger)


def test_arithmetic_kappa_y_mcc_manipulados_fallan(corrida) -> None:
    # Síntoma C3: κ y MCC que ninguna matriz produce.
    edit_json(
        corrida / "03_screening" / "metrics.json",
        lambda m: m.update(cohen_kappa=0.75, mcc=0.71),
    )
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§9.3 · cohen_kappa recalculado desde la matriz: 0.75 ≠ 1.0" in arithmetic.detail
    assert "§9.3 · mcc recalculado desde la matriz: 0.71 ≠ 1.0" in arithmetic.detail


def test_arithmetic_voto_de_un_modelo_no_configurado_falla(corrida) -> None:
    def _intruso(decisions: list[dict]) -> None:
        decisions[0]["votes"][1]["model"] = "fake:intruso"

    edit_json(corrida / TA, _intruso)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§9.3 · un voto por screener T/A configurado: 10.1000/llm-1" in arithmetic.detail


def test_arithmetic_menos_llamadas_que_decisiones_falla(corrida) -> None:
    editar_llamadas(corrida, lambda calls: calls[:10])
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "llamadas ≥ cota inferior de las decisiones: 10 llamadas < 24" in arithmetic.detail


def test_arithmetic_copia_del_manifiesto_distinta_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["exclusions"].update(excluded_human=3))
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "copia `exclusions` del manifiesto == 03_screening/exclusions.json" in arithmetic.detail


def test_arithmetic_models_used_incoherente_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["models_used"].append("anthropic:opus"))
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§9.3 · models_used == modelos de llm_calls" in arithmetic.detail


def test_arithmetic_wmcc_fn_weight_distinto_del_protocolo_falla(corrida) -> None:
    editar_protocolo(corrida, lambda p: p["thresholds"].update(wmcc_fn_weight=5.0))
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§9.3 · wmcc_fn_weight == protocolo: 10.0 ≠ 5.0" in arithmetic.detail


def test_arithmetic_sin_csv_no_verificable_advierte(corrida) -> None:
    (corrida / "deliverable" / "interop" / "prisma2020_flow.csv").unlink()
    report = auditar(corrida)
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "WARN"
    assert "no verificables: 11 · CSV PRISMA2020" in arithmetic.detail
    assert fila(report, "deliverable").status == "FAIL"


# ── Entrada hostil: ningún valor del manifiesto rompe ni llena el detalle ──


def _sin_error_interno(filas: dict[str, tuple[str, str]]) -> list[str]:
    return [i for i, (_, detalle) in filas.items() if "error interno" in detalle]


def test_arithmetic_conteos_de_tipo_equivocado_no_revientan(corrida) -> None:
    # Una cadena de 50 000 caracteres y una lista donde van enteros: `schemas` los marca;
    # `arithmetic` no puede sumarlos ni volcarlos en el detalle.
    edit_yaml(
        corrida / "manifest.yml",
        lambda m: m["counts"].update(identified="9" * 50_000, screened=[1, 2], included=True),
    )
    report = auditar(corrida)
    arithmetic = fila(report, "arithmetic")
    assert "error interno" not in arithmetic.detail
    assert arithmetic.status in {"WARN", "FAIL"}
    assert len(arithmetic.detail) < 1_500
    assert fila(report, "schemas").status == "FAIL"
    assert len(report.checks) == len(CHECKS)


@pytest.mark.parametrize(
    "conteos",
    [
        pytest.param({"identified": None}, id="none"),
        pytest.param({"identified": float("nan")}, id="nan"),
        pytest.param({"identified": 1.5}, id="decimal"),
        pytest.param({"identified": {"a": [1]}}, id="mapa"),
        pytest.param({"identified_by_source": {"OpenAlex": "x" * 50_000}}, id="por-base-cadena"),
        pytest.param({"identified_by_source": {"k" * 50_000: "no-entero"}}, id="clave-enorme"),
        pytest.param({"ft_exclusion_reasons": ["a", "b"]}, id="razones-lista"),
    ],
)
def test_arithmetic_conteos_invalidos_son_no_verificables_y_acotados(corrida, conteos) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["counts"].update(conteos))
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert "error interno" not in arithmetic.detail
    assert arithmetic.status in {"WARN", "FAIL"}
    assert len(arithmetic.detail) < 1_500


def test_arithmetic_conteo_enorme_valido_no_desborda_el_detalle(corrida) -> None:
    # Un entero de 900 cifras sí valida (`int`) y pasa la guarda del YAML (los escalares
    # numéricos de más de 1 000 caracteres ya no se cargan: ver `test_audit_infra.py`), pero no
    # puede aparecer entero en el detalle.
    edit_yaml(corrida / "manifest.yml", lambda m: m["counts"].update(identified=10**900))
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "error interno" not in arithmetic.detail
    assert len(arithmetic.detail) < 1_500


def test_arithmetic_matriz_con_enteros_gigantes_no_revienta(corrida) -> None:
    # `math.sqrt` de un entero mayor que 1e308 lanza `OverflowError`.
    edit_json(
        corrida / "03_screening" / "metrics.json",
        lambda m: m.update(tp=10**400, fp=10**400, fn=10**400, tn=10**400, n=4 * 10**400),
    )
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert "error interno" not in arithmetic.detail
    assert arithmetic.status in {"WARN", "FAIL"}
    assert len(arithmetic.detail) < 1_500


def test_arithmetic_models_used_y_llamadas_de_tipo_equivocado_no_revientan(corrida) -> None:
    def _hostil(manifest: dict) -> None:
        manifest["models_used"] = [["a", ["b"]], 3, None, {"x": "y" * 50_000}]
        manifest["deterministic_token_level"] = "y" * 50_000
        for call in manifest["llm_calls"][:3]:
            call["provider"] = ["x"] * 3
            call["model"] = "m" * 50_000

    edit_yaml(corrida / "manifest.yml", _hostil)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert "error interno" not in arithmetic.detail
    assert arithmetic.status in {"WARN", "FAIL"}
    assert len(arithmetic.detail) < 1_500


def test_arithmetic_modelos_con_nombre_enorme_se_muestran_acotados(corrida) -> None:
    edit_yaml(
        corrida / "manifest.yml",
        lambda m: m["models_used"].extend(f"proveedor:{'m' * 50_000}-{i}" for i in range(30)),
    )
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§9.3 · models_used == modelos de llm_calls" in arithmetic.detail
    assert len(arithmetic.detail) < 1_500


def test_arithmetic_ids_enormes_o_muchos_se_acotan(corrida) -> None:
    def _hostil(decisions: list[dict]) -> None:
        for i, decision in enumerate(decisions):
            decision["final_label"] = "include"  # ≠ human or ensemble en las excluidas
            decision["record_id"] = f"{'r' * 50_000}-{i}"

    edit_json(corrida / TA, _hostil)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert len(arithmetic.detail) < 1_500


def test_arithmetic_celda_enorme_del_csv_se_acota(corrida) -> None:
    _csv("records_screened", "9" * 50_000)(corrida)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "11 · CSV records_screened" in arithmetic.detail
    assert len(arithmetic.detail) < 1_500


_LLAMADA_HOSTIL = "- {provider: *a9, model: *a9, deterministic: *a9, timestamp_utc: *a9}\n"


@pytest.mark.parametrize(
    ("cola", "estado"),
    [
        pytest.param("counts: *a9\n", "WARN", id="conteos-completos"),
        pytest.param("counts: {identified: *a9, screened: *a9}\n", "WARN", id="conteos-por-campo"),
        pytest.param("counts: {identified_by_source: *a9}\n", "WARN", id="por-base"),
        pytest.param("models_used: *a9\n", "WARN", id="models_used"),
        pytest.param("llm_calls:\n" + _LLAMADA_HOSTIL * 30, "FAIL", id="llamadas"),
        pytest.param("deterministic_token_level: *a9\n", "FAIL", id="determinismo"),
        pytest.param(
            "exclusions: *a9\nrisk_of_bias: *a9\nverification: *a9\n", "FAIL", id="copias"
        ),
    ],
)
def test_arithmetic_bomba_de_alias_no_cuelga_ni_llena_el_detalle(
    corrida, cola: str, estado: str
) -> None:
    # `*a9` carga en milisegundos (PyYAML comparte los nodos) pero `repr`, `str`, `sorted` o
    # una suma la recorren entera (9**10 hojas). El manifiesto real se conserva y un solo campo
    # se redefine al final (con claves repetidas, PyYAML se queda con la última): así cada caso
    # prueba una relación y el resto sigue verificándose. Corre en un subproceso: si colgara o
    # muriera, la sesión de pytest no se vería afectada.
    manifiesto = corrida / "manifest.yml"
    texto = manifiesto.read_text(encoding="utf-8")
    manifiesto.write_text(bomba_de_alias() + texto + cola, encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=60)
    assert filas["arithmetic"][0] == estado, filas["arithmetic"]
    assert len(filas["arithmetic"][1]) < 1_500
    assert _sin_error_interno(filas) == []
    assert len(filas) == len(CHECKS)


# ── Fail-closed: ninguna relación se omite (revisión de la Tarea 7) ────────
#
# Cada relación termina verificada, rota (FAIL) o no verificable (WARN). Lo que el motor
# escribe siempre y falta es manipulación (rota); el WARN es para lo que de verdad no se puede
# saber. Antes, un manifiesto sin `counts` o sin `protocol` y un CSV que `csv` no puede leer
# dejaban `arithmetic` en WARN y la corrida publicable.

SIN_CONTEOS = "counts ausente en el manifiesto (el motor siempre lo escribe)"
SIN_PROTOCOLO = "protocol ausente en el manifiesto (el motor siempre lo escribe)"
VOTOS = "§9.3 · un voto por screener T/A configurado"
HERRAMIENTA_ROB = "§9.3 · assessment.tool == protocol.rob_tool"
PESO_WMCC = "§9.3 · wmcc_fn_weight == protocolo"
DOBLE_DECLARADA = "§9.3 · doble extracción declarada en el protocolo"
SUMA_POR_BASE = "1 · Σ identified_by_source == identified"
RELACION_6 = "6 · excluded_ta_human + excluded_ta_ai == excluded_ta"
COTA_LLAMADAS = "§9.3 · llamadas ≥ cota inferior de las decisiones"
RESCATADOS = "v0.7 · fulltext_rescued == 0 (el motor v0.7 no rescata textos completos)"
FICHERO_DOBLE = "§9.3 · 05_extraction/agreement.json de la doble extracción declarada"
COPIA_DOBLE = "§9.3 · copia `extraction_agreement` del manifiesto"
MODELOS_USADOS = "§9.3 · models_used == modelos de llm_calls"


def _relaciones(run: Path) -> dict[str, tuple[bool | None, str]]:
    """Las relaciones de ``arithmetic`` (``nombre → (ok, detalle)``), sin nombres repetidos."""
    relaciones = collect_relations(AuditContext(load_run(run)))
    nombres = [r.name for r in relaciones]
    assert len(nombres) == len(set(nombres)), nombres
    return {r.name: (r.ok, r.detail) for r in relaciones}


def _quitar_de_counts(*claves: str) -> Callable[[dict], None]:
    def _editar(manifest: dict) -> None:
        for clave in claves:
            del manifest["counts"][clave]

    return _editar


def test_arithmetic_corrida_real_cuenta_sus_relaciones_verificadas(corrida) -> None:
    # La corrida de la Ola 1 tiene run.json: no lleva la relación v0.7 `fulltext_rescued == 0`
    # (49 en la fase 1, con una corrida sin run.json). Las relaciones que ahora son
    # incondicionales (Σ por base, desglose humano/IA, protocolo, doble extracción) no suman
    # nada a una corrida sana: en ella ya se verificaban todas. Con `llm_calls.jsonl` suma una:
    # la copia de las llamadas en el manifiesto es igual al original (§4.3).
    relaciones = _relaciones(corrida)
    assert [n for n, (ok, _) in relaciones.items() if ok is not True] == []
    assert len(relaciones) == 49
    assert "49 relaciones verificadas" in fila(auditar(corrida), "arithmetic").detail


def test_arithmetic_manifiesto_sin_counts_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", _sin_clave("counts"))
    report = auditar(corrida)
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "FAIL"
    assert SIN_CONTEOS in arithmetic.detail
    assert report.publishable is False
    # Cada relación que depende de `counts` queda rota por ausencia, ninguna se omite.
    relaciones = _relaciones(corrida)
    for nombre in (
        "conteos del embudo",
        "10 · exclusions.total_excluded == excluded_ta + excluded_ft",
        "11 · CSV PRISMA2020",
        "§9.3 · cota inferior de llamadas",
    ):
        assert relaciones[nombre] == (False, SIN_CONTEOS), nombre
    exclusions = fila(report, "exclusions")
    assert exclusions.status == "FAIL"
    assert SIN_CONTEOS in exclusions.detail


def test_arithmetic_manifiesto_sin_protocol_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", _sin_clave("protocol"))
    report = auditar(corrida)
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "FAIL"
    assert SIN_PROTOCOLO in arithmetic.detail
    assert report.publishable is False
    # Las relaciones que dependen del protocolo aparecen rotas, no desaparecen.
    relaciones = _relaciones(corrida)
    for nombre in (VOTOS, HERRAMIENTA_ROB, PESO_WMCC, DOBLE_DECLARADA):
        assert relaciones[nombre] == (False, SIN_PROTOCOLO), nombre
    # La cota de llamadas sigue verificándose con un solo screener (la cota más baja).
    assert relaciones[COTA_LLAMADAS][0] is True


def test_arithmetic_protocolo_invalido_es_no_verificable(corrida) -> None:
    # Presente pero que no valida: lo marca `schemas`; aquí queda no verificable, no rota.
    edit_yaml(corrida / "manifest.yml", lambda m: m["protocol"].update(rob_tool="no-existe"))
    relaciones = _relaciones(corrida)
    for nombre in (VOTOS, HERRAMIENTA_ROB, PESO_WMCC, DOBLE_DECLARADA):
        ok, detalle = relaciones[nombre]
        assert ok is None, nombre
        assert "manifest.protocol inválido" in detalle


def test_arithmetic_csv_con_campo_mayor_que_el_limite_falla(corrida) -> None:
    # El módulo `csv` rechaza campos de más de 131 072 caracteres con `csv.Error`: el motor
    # siempre escribe un CSV legible, así que no poder leerlo es manipulación.
    ruta = corrida / "deliverable" / "interop" / "prisma2020_flow.csv"
    ruta.write_text("data,n\nrecords_screened," + "9" * 200_000 + "\n", encoding="utf-8")
    report = auditar(corrida)
    arithmetic = fila(report, "arithmetic")
    assert "error interno" not in arithmetic.detail
    assert arithmetic.status == "FAIL"
    assert "11 · CSV PRISMA2020: " in arithmetic.detail
    assert "no se pudo leer como CSV (Error)" in arithmetic.detail
    assert len(arithmetic.detail) < 1_500
    assert report.publishable is False


def test_arithmetic_csv_que_no_es_utf8_falla(corrida) -> None:
    ruta = corrida / "deliverable" / "interop" / "prisma2020_flow.csv"
    ruta.write_bytes(b"\xff\xfe\x00 no es utf-8")
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "11 · CSV PRISMA2020: " in arithmetic.detail
    assert "ilegible" in arithmetic.detail


@pytest.mark.parametrize(
    ("ruta", "relacion"),
    [
        pytest.param(TA, "relaciones del cribado T/A", id="decisiones-ta"),
        pytest.param(FT, "relaciones del texto completo", id="decisiones-ft"),
        pytest.param(
            "05_extraction/extractions.json",
            "10 · claves de 05_extraction/extractions.json",
            id="extracciones",
        ),
        pytest.param(
            "07_rob/assessments.json", "10 · claves de 07_rob/assessments.json", id="evaluaciones"
        ),
        pytest.param(
            "03_screening/exclusions.json",
            "10 · exclusions.total_excluded == excluded_ta + excluded_ft",
            id="exclusiones",
        ),
    ],
)
def test_arithmetic_artefacto_que_el_motor_siempre_escribe_ausente_es_relacion_rota(
    corrida, ruta: str, relacion: str
) -> None:
    (corrida / ruta).unlink()
    assert fila(auditar(corrida), "arithmetic").status == "FAIL"
    detalle = f"{ruta} ausente (el motor siempre lo escribe)"
    assert _relaciones(corrida)[relacion] == (False, detalle)


def test_arithmetic_artefacto_invalido_es_no_verificable(corrida) -> None:
    (corrida / TA).write_text("{}", encoding="utf-8")  # un mapa donde va una lista de decisiones
    ok, detalle = _relaciones(corrida)["relaciones del cribado T/A"]
    assert ok is None
    assert f"{TA} inválido" in detalle


# ── Fail-closed: lo que antes se omitía en silencio ──


def test_arithmetic_identified_by_source_vacio_con_identificados_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["counts"].update(identified_by_source={}))
    assert fila(auditar(corrida), "arithmetic").status == "FAIL"
    assert _relaciones(corrida)[SUMA_POR_BASE][0] is False


def test_arithmetic_identified_by_source_vacio_sin_identificados_se_verifica(tmp_path) -> None:
    run = tmp_path / "runs" / "vacia-20260101-000000"
    run.mkdir(parents=True)
    manifest = {"counts": PrismaCounts().model_dump()}
    (run / "manifest.yml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    assert _relaciones(run)[SUMA_POR_BASE][0] is True


def test_arithmetic_sin_desglose_humano_ia_en_counts_no_es_verificable(corrida) -> None:
    # Un manifiesto anterior al desglose pudo no traerlos: no se puede saber (WARN, no FAIL).
    edit_yaml(corrida / "manifest.yml", _quitar_de_counts("excluded_ta_human", "excluded_ta_ai"))
    report = auditar(corrida)
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "WARN"
    assert f"no verificables: {RELACION_6} (counts sin excluded_ta_human/ai" in arithmetic.detail
    assert _relaciones(corrida)[RELACION_6][0] is None
    exclusions = fila(report, "exclusions")
    assert exclusions.status == "WARN"
    assert "counts sin excluded_ta_human/ai" in exclusions.detail
    assert report.publishable is True


def test_arithmetic_solo_uno_de_los_conteos_humano_ia_falla(corrida) -> None:
    # El motor escribe ambos a la vez: que falte uno es manipulación.
    edit_yaml(corrida / "manifest.yml", _quitar_de_counts("excluded_ta_ai"))
    report = auditar(corrida)
    assert fila(report, "arithmetic").status == "FAIL"
    assert "solo uno de excluded_ta_human/ai" in fila(report, "arithmetic").detail
    assert fila(report, "exclusions").status == "FAIL"
    assert "solo uno de excluded_ta_human/ai" in fila(report, "exclusions").detail


def test_arithmetic_doble_extraccion_declarada_sin_fichero_ni_copia_falla(corrida) -> None:
    # Quitar la copia del manifiesto no puede ser la forma de quitar el fichero.
    (corrida / "05_extraction" / "agreement.json").unlink()
    edit_yaml(corrida / "manifest.yml", _sin_clave("extraction_agreement"))
    report = auditar(corrida)
    assert fila(report, "arithmetic").status == "FAIL"
    assert report.publishable is False
    relaciones = _relaciones(corrida)
    assert relaciones[FICHERO_DOBLE][0] is False
    assert "05_extraction/agreement.json ausente" in relaciones[FICHERO_DOBLE][1]
    assert relaciones[COPIA_DOBLE][0] is False


def test_arithmetic_corrida_v07_con_fulltext_rescued_es_relacion_rota(tmp_path) -> None:
    # Sin run.json el motor es el v0.7 y nunca rescata textos: la corrida v0.7 de referencia
    # (`write_legacy_v07`, la fuente realista de ese motor) no puede declarar rescates.
    run = write_legacy_v07(tmp_path)
    edit_yaml(run / "manifest.yml", lambda m: m["counts"].update(fulltext_rescued=1))
    arithmetic = fila(auditar(run), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "1 relación(es) rota(s)" in arithmetic.detail
    assert f"{RESCATADOS}: 1 ≠ 0" in arithmetic.detail


def test_arithmetic_corrida_v07_fulltext_rescued_no_baja_la_cota_de_llamadas(tmp_path) -> None:
    # Con rescates declarados la cota bajaba y una corrida con llamadas de menos pasaba. Sin
    # run.json (relaciones v0.7) se exige `fulltext_rescued == 0` y la cota no descuenta
    # rescates: la v0.7 de referencia tiene 12 llamadas y 3 textos completos evaluados, así que
    # descontarlos la bajaría a 9 y 11 llamadas pasarían.
    run = write_legacy_v07(tmp_path)
    edit_yaml(
        run / "manifest.yml",
        lambda m: m["counts"].update(fulltext_rescued=m["counts"]["fulltext_assessed"]),
    )
    editar_llamadas(run, lambda calls: calls[:11])
    arithmetic = fila(auditar(run), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert RESCATADOS in arithmetic.detail
    assert "11 llamadas < 12" in arithmetic.detail


@pytest.mark.xfail(
    strict=True,
    reason="Tarea 14: relación 8 (fulltext_rescued frente al ledger) y cota de llamadas",
)
def test_arithmetic_fulltext_rescued_con_run_json_baja_la_cota_y_no_es_publicable(corrida) -> None:
    # Vector abierto en una corrida de la Ola 1 (con run.json): declarar todos los textos
    # completos como rescatados baja la cota de llamadas y una corrida con llamadas de menos
    # pasa. Hoy `arithmetic` es PASS y la corrida es publicable; la relación 8 (los rescates
    # declarados frente a los del ledger) y la cota de llamadas de la Tarea 14 lo cierran.
    edit_yaml(
        corrida / "manifest.yml",
        lambda m: m["counts"].update(fulltext_rescued=m["counts"]["fulltext_assessed"]),
    )
    editar_llamadas(corrida, lambda calls: calls[:23])
    report = auditar(corrida)
    assert report.publishable is False
    assert fila(report, "arithmetic").status == "FAIL"


def test_arithmetic_manifiesto_sin_models_used_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", _sin_clave("models_used"))
    report = auditar(corrida)
    assert fila(report, "arithmetic").status == "FAIL"
    assert report.publishable is False
    ok, detalle = _relaciones(corrida)[MODELOS_USADOS]
    assert ok is False
    assert detalle == "models_used ausente en el manifiesto (el motor siempre lo escribe)"
    # La ausencia no la marca `schemas` (solo valida lo presente): no puede remitir a ella.
    assert fila(report, "schemas").status == "PASS"
    assert "schemas" not in detalle


def test_arithmetic_models_used_de_otro_tipo_es_no_verificable_y_schemas_lo_marca(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(models_used="fake:fake-1"))
    report = auditar(corrida)
    ok, detalle = _relaciones(corrida)[MODELOS_USADOS]
    assert ok is None
    assert "ver `schemas`" in detalle
    assert fila(report, "schemas").status == "FAIL"  # la remisión es cierta


@pytest.mark.parametrize(
    ("clave", "ruta"),
    [
        pytest.param("exclusions", "03_screening/exclusions.json", id="exclusions"),
        pytest.param("risk_of_bias", "07_rob/assessments.json", id="risk_of_bias"),
        pytest.param("verification", "06_synthesis/verification.json", id="verification"),
    ],
)
def test_arithmetic_fichero_y_copia_que_el_motor_siempre_escribe_ausentes_son_relacion_rota(
    corrida, clave: str, ruta: str
) -> None:
    (corrida / ruta).unlink()
    edit_yaml(corrida / "manifest.yml", _sin_clave(clave))
    report = auditar(corrida)
    assert fila(report, "arithmetic").status == "FAIL"
    assert report.publishable is False
    ok, detalle = _relaciones(corrida)[f"§9.3 · copia `{clave}` del manifiesto"]
    assert ok is False
    assert detalle == f"{ruta} y su copia ausentes (el motor siempre lo escribe)"


@pytest.mark.parametrize(
    ("clave", "ruta"),
    [
        pytest.param("screening_metrics", "03_screening/metrics.json", id="screening_metrics"),
        pytest.param("meta_analysis", "08_meta/meta_analysis.json", id="meta_analysis"),
    ],
)
def test_arithmetic_copia_opcional_sin_fichero_ni_copia_no_es_relacion(
    corrida, clave: str, ruta: str
) -> None:
    # Sin gold no hay métricas y sin `effects.yml` no hay metaanálisis: son opcionales.
    (corrida / ruta).unlink()
    edit_yaml(corrida / "manifest.yml", _sin_clave(clave))
    assert f"§9.3 · copia `{clave}` del manifiesto" not in _relaciones(corrida)


# ── _limitar: el sufijo «(+k más)» de una relación sobrevive al recorte ──


def test_limitar_no_parte_el_sufijo_de_ids_dentro_de_una_relacion() -> None:
    relacion = "5 · ensemble_label == recall_biased_label(votes): " + ", ".join(["r" * 60] * 3)
    relacion += " (+4 más)"
    assert len(relacion) > 240
    assert _limitar([relacion]).endswith(" (+4 más)")


def test_limitar_conserva_el_sufijo_de_ids_aunque_le_siga_mas_texto() -> None:
    relacion = "5 · final_label == human_label or ensemble_label: " + ", ".join(["r" * 60] * 3)
    relacion += " (+4 más) (más texto detrás del sufijo)"
    resultado = _limitar([relacion])
    assert "(+4 más)" in resultado
    assert "(+4 …" not in resultado
    assert len(resultado) <= 240


def test_limitar_sigue_acotando_lo_que_no_lleva_sufijo() -> None:
    resultado = _limitar(["x" * 5_000, "corta"])
    assert resultado == "x" * 239 + "…; corta"


def test_limitar_conserva_los_dos_sufijos_de_una_relacion_con_dos_listas() -> None:
    ids = ", ".join(["r" * 58] * 3)
    screeners = ", ".join(["s" * 55] * 3)
    relacion = f"{VOTOS}: {ids} (+3 más) (screeners: {screeners} (+2 más))"
    assert len(relacion) > 240
    resultado = _limitar([relacion])
    assert len(resultado) <= 240
    assert "(+3 más)" in resultado
    assert "(+2 más)" in resultado
    assert "(screeners: " in resultado  # el recorte reparte el espacio: la 2.ª lista no desaparece
    assert re.search(r"\(\+\d+(?!\d| más\))", resultado) is None, resultado


def test_limitar_con_texto_hostil_lleno_de_sufijos_sigue_acotado() -> None:
    resultado = _limitar(["a (+1 más) " * 500])
    assert len(resultado) <= 240


def test_arithmetic_voto_por_screener_conserva_el_sufijo_de_ids_y_el_de_screeners(corrida) -> None:
    def _ids_largos(decisions: list[dict]) -> None:
        for i, decision in enumerate(decisions[:5]):
            decision["record_id"] = f"id-{i}-{'r' * 53}"  # 58 caracteres

    def _cinco_screeners(protocolo: dict) -> None:
        protocolo["ensemble_llm"]["screening_ta"] = [
            {"provider": "fake", "model": f"modelo-{i}-{'m' * 40}", "seed": i} for i in range(5)
        ]

    edit_json(corrida / TA, _ids_largos)
    editar_protocolo(corrida, _cinco_screeners)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert VOTOS in arithmetic.detail
    assert "(+3 más) (screeners: " in arithmetic.detail  # 6 decisiones con voto de más
    assert "(+2 más))" in arithmetic.detail  # 5 screeners
    assert re.search(r"\(\+\d+(?!\d| más\))", arithmetic.detail) is None, arithmetic.detail


def test_arithmetic_ids_enormes_no_dejan_un_sufijo_cortado(corrida) -> None:
    def _hostil(decisions: list[dict]) -> None:
        for i, decision in enumerate(decisions):
            decision["final_label"] = "include"
            decision["ensemble_label"] = "unclear"  # ≠ recall_biased_label(votes) en todas
            decision["record_id"] = f"{'r' * 50_000}-{i}"

    edit_json(corrida / TA, _hostil)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "(+" in arithmetic.detail
    assert re.search(r"\(\+\d+(?!\d| más\))", arithmetic.detail) is None, arithmetic.detail


# ── stage_artifacts ────────────────────────────────────────────────────


def test_stage_artifacts_falta_04_fulltext_falla(corrida) -> None:
    # Síntoma C3: faltaban 01, 02, 04, 05 y 07.
    shutil.rmtree(corrida / "04_fulltext")
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "FAIL"
    assert "screening_ft: 04_fulltext/decisions.json" in stage.detail


def test_stage_artifacts_doble_extraccion_declarada_sin_fichero_falla(corrida) -> None:
    (corrida / "05_extraction" / "agreement.json").unlink()
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "FAIL"
    assert "extraccion: 05_extraction/agreement.json" in stage.detail


def test_stage_artifacts_corrida_real_pasa(corrida) -> None:
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "PASS"
    assert "etapas alcanzadas presentes" in stage.detail


def test_stage_artifacts_en_pausa_solo_exige_las_etapas_alcanzadas(corrida_en_pausa_ft) -> None:
    stage = fila(auditar(corrida_en_pausa_ft), "stage_artifacts")
    assert stage.status == "PASS"
    assert "screening_ta" in stage.detail
    assert "screening_ft" not in stage.detail


def test_stage_artifacts_doble_extraccion_declarada_sin_fichero_ni_copia_falla(corrida) -> None:
    # Quitar también la copia del manifiesto no puede relajar la exigencia: la fija el protocolo.
    (corrida / "05_extraction" / "agreement.json").unlink()
    edit_yaml(corrida / "manifest.yml", _sin_clave("extraction_agreement"))
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "FAIL"
    assert "extraccion: 05_extraction/agreement.json" in stage.detail


def test_stage_artifacts_sin_incluidos_no_exige_la_doble_extraccion(corrida) -> None:
    # El motor solo escribe agreement.json si hay un 2.º extractor e incluidos.
    (corrida / "05_extraction" / "agreement.json").unlink()
    edit_yaml(corrida / "manifest.yml", _sin_clave("extraction_agreement"))
    edit_json(corrida / FT, lambda decisions: decisions.clear())
    assert fila(auditar(corrida), "stage_artifacts").status == "PASS"


# ── exclusions ─────────────────────────────────────────────────────────


def test_exclusions_ausente_falla(corrida) -> None:
    (corrida / "03_screening" / "exclusions.json").unlink()
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert "ausente" in exclusions.detail


def test_exclusions_distinta_del_recalculo_falla(corrida) -> None:
    # Síntoma C3: `excluded_human: 3` que el motor no puede generar.
    edit_json(corrida / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=3))
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert "excluded_human 3 ≠" in exclusions.detail


def test_exclusions_sin_decisiones_no_se_recalcula_y_falla(corrida) -> None:
    (corrida / TA).unlink()
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert "no se puede recalcular" in exclusions.detail


def test_exclusions_conteos_ta_distintos_del_recalculo_falla(corrida) -> None:
    edit_yaml(
        corrida / "manifest.yml",
        lambda m: m["counts"].update(excluded_ta_human=1, excluded_ta_ai=1),
    )
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert "counts.excluded_ta_human/ai 1/1 ≠ 0/2 (solo T/A)" in exclusions.detail


def test_exclusions_json_hostil_se_informa_acotado(corrida) -> None:
    # Un `total_excluded` de 4 000 cifras valida (`int`) y no puede volcarse entero.
    edit_json(
        corrida / "03_screening" / "exclusions.json",
        lambda e: e.update(total_excluded=10**4000, excluded_human=10**4000),
    )
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert len(exclusions.detail) < 1_000


def test_exclusions_json_ilegible_se_informa_acotado(corrida) -> None:
    (corrida / "03_screening" / "exclusions.json").write_text(
        '{"total_excluded": "' + "x" * 50_000 + '"}', encoding="utf-8"
    )
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert len(exclusions.detail) < 1_000


@pytest.mark.parametrize(
    ("aprobados", "rechazar", "estado", "etapa"),
    [
        pytest.param(
            ("screening_ta", "screening_ft"),
            None,
            "paused",
            "extraccion",
            id="pausada-en-extraccion",
        ),
        pytest.param(
            ("screening_ta", "screening_ft", "extraccion"),
            None,
            "paused",
            "rob",
            id="pausada-en-rob",
        ),
        pytest.param(
            ("screening_ta", "screening_ft"),
            "extraccion",
            "rejected",
            "extraccion",
            id="rechazada-en-extraccion",
        ),
    ],
)
def test_exclusions_corrida_detenida_antes_del_reporte_no_exige_el_manifiesto(
    detener_corrida, aprobados, rechazar, estado: str, etapa: str
) -> None:
    # El motor escribe `manifest.yml` al evaluar el gate final: exigirle `counts` a una corrida
    # detenida antes daba un FAIL falso (regresión de la revisión de la Tarea 7).
    run = detener_corrida(aprobados=aprobados, rechazar=rechazar)
    assert not (run / "manifest.yml").exists()
    report = auditar(run)
    assert (report.state.status, report.state.pending_stage) == (estado, etapa)
    exclusions = fila(report, "exclusions")
    assert exclusions.status == "PASS", exclusions.detail
    assert "se verificarán al reanudar" in exclusions.detail  # el PASS no aparenta verlo todo
    assert fila(report, "arithmetic").status == "N/A"
    assert report.publishable is False  # la pausa sigue dejando `final_gate` en FAIL


def test_exclusions_corrida_en_pausa_en_reporte_si_exige_el_manifiesto(detener_corrida) -> None:
    # Desde `reporte` el manifiesto ya existe (se escribe con cualquier resultado del gate final).
    run = detener_corrida(aprobados=("screening_ta", "screening_ft", "extraccion", "rob"))
    assert fila(auditar(run), "exclusions").status == "PASS"
    edit_yaml(run / "manifest.yml", _sin_clave("counts"))
    exclusions = fila(auditar(run), "exclusions")
    assert exclusions.status == "FAIL"
    assert SIN_CONTEOS in exclusions.detail


def test_exclusions_corrida_en_pausa_compara_un_manifiesto_presente(
    detener_corrida, corrida: Path
) -> None:
    """En pausa el auditor no exige el manifiesto, pero si lo hay lo compara con el recálculo.

    La corrida en pausa en `rob` aún no tiene manifiesto: se le copia el de la corrida
    terminada (mismo pipeline, proveedor y búsqueda, así que sus conteos de cribado
    coinciden) y después se altera un conteo de exclusiones.
    """
    run = detener_corrida(aprobados=("screening_ta", "screening_ft", "extraccion"))
    assert not (run / "manifest.yml").exists()
    shutil.copy(corrida / "manifest.yml", run / "manifest.yml")
    assert fila(auditar(run), "exclusions").status != "FAIL"

    edit_yaml(
        run / "manifest.yml",
        lambda m: m["counts"].update(excluded_ta_human=m["counts"]["excluded_ta_human"] + 1),
    )
    exclusions = fila(auditar(run), "exclusions")
    assert exclusions.status == "FAIL"
    assert "excluded_ta_human" in exclusions.detail


# ── deliverable ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "nombre",
    ["checklist_s.md", "checklist_abstracts.md", "interop/prisma2020_flow.csv"],
)
def test_deliverable_exige_checklists_y_csv(corrida, nombre: str) -> None:
    (corrida / "deliverable" / nombre).unlink()
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert f"{nombre} (falta)" in deliverable.detail


def test_deliverable_exige_meta_analisis_si_hubo_efectos(corrida) -> None:
    (corrida / "deliverable" / "meta_analisis.md").unlink()
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert "meta_analisis.md (falta)" in deliverable.detail


def test_deliverable_fichero_vacio_falla(corrida) -> None:
    (corrida / "deliverable" / "metodologia.md").write_text("  \n", encoding="utf-8")
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert "metodologia.md (vacío)" in deliverable.detail


def test_deliverable_fichero_binario_falla_sin_reventar(corrida) -> None:
    (corrida / "deliverable" / "referencias.bib").write_bytes(b"\xff\xfe\x00\x00 no es utf-8")
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert "referencias.bib" in deliverable.detail
    assert "error interno" not in deliverable.detail


def test_deliverable_completo_pasa(corrida) -> None:
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "PASS"
    # Los 11 de siempre + meta_analisis.md + la lista 16b de la Ola 1.
    assert "13 artefactos" in deliverable.detail
