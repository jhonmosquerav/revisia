"""Checks del flujo PRISMA: ``stage_artifacts``, ``arithmetic``, ``exclusions``, ``deliverable``.

Spec 2026-10-04 §4.4 y §9.3 (filas 11-14). Cada caso de ``arithmetic`` rompe
una sola relación de la corrida real y comprueba que el auditor la nombra.
"""

from __future__ import annotations

import csv
import io
import json
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
    pausar_en_screening_ft,
    write_legacy_v07,
)

from revisia.audit import CHECKS

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
    # Un entero de 4 000 cifras sí valida (`int`), pero no puede aparecer entero en el detalle.
    edit_yaml(corrida / "manifest.yml", lambda m: m["counts"].update(identified=10**4000))
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


def test_arithmetic_csv_con_campo_mayor_que_el_limite_es_no_verificable(corrida) -> None:
    # El módulo `csv` rechaza campos de más de 131 072 caracteres con `csv.Error`.
    ruta = corrida / "deliverable" / "interop" / "prisma2020_flow.csv"
    ruta.write_text("data,n\nrecords_screened," + "9" * 200_000 + "\n", encoding="utf-8")
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert "error interno" not in arithmetic.detail
    assert arithmetic.status == "WARN"
    assert "11 · CSV PRISMA2020" in arithmetic.detail


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


def test_stage_artifacts_en_pausa_solo_exige_las_etapas_alcanzadas(corrida) -> None:
    pausar_en_screening_ft(corrida)
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "PASS"
    assert "screening_ta" in stage.detail
    assert "screening_ft" not in stage.detail


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
    assert "12 artefactos" in deliverable.detail  # los 11 de siempre + meta_analisis.md
