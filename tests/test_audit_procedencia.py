"""Checks de procedencia y ledger: ``manifest``, ``schemas``, ``prompts``, ``ledger``.

Spec 2026-10-04 §9.3 (filas 1, 3, 5 y 7) y §9.4 (familias robustez, ``schemas``
y ``ledger``). Cada test rompe una sola cosa de la corrida real.
"""

from __future__ import annotations

import pytest
from audit_fixtures import (
    auditar,
    edit_json,
    edit_ledger,
    edit_yaml,
    editar_llamadas,
    fila,
    reetiquetar_llamadas,
)

from revisia.audit import CHECKS
from revisia.config import STAGES

ARTEFACTOS_JSON = (
    "03_screening/decisions.json",
    "03_screening/metrics.json",
    "03_screening/exclusions.json",
    "04_fulltext/decisions.json",
    "05_extraction/extractions.json",
    "05_extraction/agreement.json",
    "06_synthesis/verification.json",
    "07_rob/assessments.json",
    "08_meta/meta_analysis.json",
)

# ── manifest ───────────────────────────────────────────────────────────


def test_manifest_yaml_invalido_falla(corrida) -> None:
    (corrida / "manifest.yml").write_text("slug: [sin cerrar\n", encoding="utf-8")
    manifest = fila(auditar(corrida), "manifest")
    assert manifest.status == "FAIL"
    assert "ilegible (YAML inválido" in manifest.detail


def test_manifest_sin_llamadas_advierte(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(llm_calls=[], models_used=[]))
    manifest = fila(auditar(corrida), "manifest")
    assert manifest.status == "WARN"
    assert "sin llamadas IA" in manifest.detail


def test_manifest_proveedor_real_pasa(corrida) -> None:
    reetiquetar_llamadas(corrida, provider="gemini", deterministic=False)
    manifest = fila(auditar(corrida), "manifest")
    assert manifest.status == "PASS"
    assert "gemini:fake-a" in manifest.detail


def test_manifest_con_miles_de_modelos_largos_se_acota(corrida) -> None:
    # `models_used` de un manifiesto editado a mano: se listan los primeros y se cuenta el resto,
    # y cada nombre va recortado (diez nombres de 120 caracteres ya pasaban de 1 000).
    reetiquetar_llamadas(corrida, provider="gemini", deterministic=False)
    modelos = [f"proveedor:modelo-{i}-" + "x" * 500 for i in range(2_000)]
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(models_used=modelos))
    manifest = fila(auditar(corrida), "manifest")
    assert manifest.status == "PASS"
    assert "(+1990 más)" in manifest.detail
    assert manifest.detail.count("proveedor:modelo-") == 10
    assert len(manifest.detail) < 1_000


# ── schemas y robustez ────────────────────────────────────────────────


def test_schemas_corrida_real_pasa(corrida) -> None:
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "PASS"
    assert "artefactos validan su modelo" in schemas.detail


@pytest.mark.parametrize("rel", ARTEFACTOS_JSON)
def test_artefacto_json_invalido_falla_schemas(corrida, rel: str) -> None:
    (corrida / rel).write_text("{no es json", encoding="utf-8")
    report = auditar(corrida)
    schemas = fila(report, "schemas")
    assert schemas.status == "FAIL"
    assert f"{rel}: JSON inválido" in schemas.detail
    assert len(report.checks) == len(CHECKS)


def test_schemas_metricas_sin_matriz_falla(corrida) -> None:
    # La forma exacta del metrics.json de la reconstrucción C3.
    edit_json(
        corrida / "03_screening" / "metrics.json",
        lambda _m: {"n": 47, "recall": 1.0, "mcc": 0.71, "cohen_kappa": 0.75},
    )
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "03_screening/metrics.json: tp: Field required" in schemas.detail


def test_schemas_llamada_sin_response_sha256_falla(corrida) -> None:
    editar_llamadas(corrida, lambda calls: calls[0].pop("response_sha256"))
    report = auditar(corrida)
    assert "manifest.yml#llm_calls: 0.response_sha256" in fila(report, "schemas").detail
    assert fila(report, "schemas").status == "FAIL"
    assert fila(report, "prompts").status == "WARN"


def test_schemas_verificacion_sin_stage_falla(corrida) -> None:
    edit_json(corrida / "06_synthesis" / "verification.json", lambda v: v.pop("stage"))
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "06_synthesis/verification.json: stage: Field required" in schemas.detail


def test_schemas_herramienta_rob_desconocida_falla(corrida) -> None:
    def _herramienta(assessments: dict) -> None:
        for assessment in assessments.values():
            assessment["tool"] = "Cochrane-RoB"

    edit_json(corrida / "07_rob" / "assessments.json", _herramienta)
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "07_rob/assessments.json" in schemas.detail


def test_schemas_decision_con_approved_no_booleano_falla(corrida) -> None:
    (corrida / "screening_ta" / "decision.yml").write_text(
        'approved: "sí"\nactor: human:revisora\n', encoding="utf-8"
    )
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "screening_ta/decision.yml:" in schemas.detail
    assert "approved: Input should be a valid boolean" in schemas.detail


def test_schemas_acota_el_detalle_ante_claves_hostiles(corrida) -> None:
    """Una clave de 10 000 caracteres acaba en el ``loc`` del error: no llena el detalle."""
    edit_json(corrida / "05_extraction" / "extractions.json", lambda _e: {"k" * 10_000: {}})
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "05_extraction/extractions.json" in schemas.detail
    assert len(schemas.detail) < 1_000


def test_schemas_distingue_errores_de_un_artefacto_y_artefactos_con_error(corrida) -> None:
    # Dos "(+N más)" distintos en la misma fila (los errores que `format_validation` no lista de
    # un artefacto y los artefactos que no caben en la fila) eran indistinguibles.
    edit_json(
        corrida / "05_extraction" / "extractions.json", lambda _e: {f"k{i}": {} for i in range(9)}
    )
    for rel in ARTEFACTOS_JSON[:7]:
        if rel != "05_extraction/extractions.json":
            (corrida / rel).write_text("{no es json", encoding="utf-8")
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "errores más" in schemas.detail  # los de `extractions.json`: 9 errores, se listan 3
    assert "(+2 artefactos más)" in schemas.detail  # 7 artefactos con error, se listan 5
    assert "(+2 más)" not in schemas.detail
    assert len(schemas.detail) < 1_500


# ── ledger ─────────────────────────────────────────────────────────────


def test_ledger_linea_corrupta_falla_con_numero_de_linea(corrida) -> None:
    path = corrida / "decisions_ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.insert(1, '{"stage": "screening_ft", "actor": ')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = auditar(corrida)
    ledger = fila(report, "ledger")
    assert ledger.status == "FAIL"
    assert "línea 2: JSON inválido" in ledger.detail
    # Con el ledger ilegible no se relaja nada: se exigen todas las etapas.
    assert report.state is not None and report.state.reached == frozenset(STAGES)


def test_ledger_linea_que_no_valida_decision_entry_falla(corrida) -> None:
    edit_ledger(corrida, lambda entries: entries[0].pop("actor"))
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "línea 1: actor: Field required" in ledger.detail


def test_ledger_rechazo_malformado_tras_una_aprobacion_falla(corrida) -> None:
    """Una línea inválida no se descarta en silencio: antes, ``ledger`` y ``final_gate``
    daban PASS aunque tras una aprobación válida hubiera un ``reject`` ilegible."""

    def _rechazo_sin_actor(entries: list[dict]) -> list[dict]:
        aprobacion = next(
            e for e in reversed(entries) if (e["stage"], e["action"]) == ("reporte", "approve")
        )
        rechazo = {k: v for k, v in aprobacion.items() if k != "actor"}
        rechazo["action"] = "reject"
        i = entries.index(aprobacion) + 1
        return [*entries[:i], rechazo, *entries[i:]]

    edit_ledger(corrida, _rechazo_sin_actor)
    report = auditar(corrida)
    ledger = fila(report, "ledger")
    assert ledger.status == "FAIL"
    assert "actor: Field required" in ledger.detail
    assert not report.publishable


@pytest.mark.parametrize("accion", ["propose", "exclude", "verify"])
def test_ledger_acciones_que_el_motor_no_emite_fallan(corrida, accion: str) -> None:
    def _insertar(entries: list[dict]) -> None:
        entries.insert(0, {**entries[0], "action": accion, "actor": "agent:opus+sonnet"})

    edit_ledger(corrida, _insertar)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert f"línea 1: acción `{accion}` que el motor no emite" in ledger.detail


def test_ledger_etapa_desconocida_falla(corrida) -> None:
    edit_ledger(corrida, lambda entries: entries[0].update(stage="cribado"))
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "etapa desconocida `cribado`" in ledger.detail


def test_ledger_etapas_desordenadas_falla(corrida) -> None:
    edit_ledger(corrida, lambda entries: [entries[-1], *entries[:-1]])
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "gates fuera del orden de STAGES: reporte → screening_ta" in ledger.detail


def test_ledger_autonomia_distinta_de_la_efectiva_falla(corrida) -> None:
    def _autonomia(entries: list[dict]) -> None:
        for entry in entries:
            if entry["stage"] == "screening_ft":
                entry["autonomy"] = "A1"

    edit_ledger(corrida, _autonomia)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "autonomía A1 en `screening_ft`, la efectiva es A0" in ledger.detail


def test_ledger_acota_los_textos_hostiles_de_las_entradas(corrida) -> None:
    """Etapa, acción, autonomía y actor son texto libre del ledger: ningún detalle los copia
    enteros (misma disciplina que con los valores del manifiesto)."""
    enorme = "x" * 10_000

    def _hostil(entries: list[dict]) -> None:
        entries[0]["stage"] = enorme
        entries[1]["action"] = enorme
        entries[2]["autonomy"] = enorme
        entries[-1]["actor"] = enorme  # el último es la decisión sobre `reporte`

    edit_ledger(corrida, _hostil)
    report = auditar(corrida)
    assert fila(report, "ledger").status == "FAIL"
    assert fila(report, "final_gate").status == "FAIL"  # antes WARN: el actor no es humano (D8)
    for check_id in ("ledger", "hitl", "final_gate"):
        assert len(fila(report, check_id).detail) < 1_500, check_id


def test_ledger_volver_a_decidir_tras_un_rechazo_es_valido(corrida) -> None:
    # D14: se puede reanudar después de un reject; queda rastro de ambas.
    def _rechazo_y_vuelta(entries: list[dict]) -> list[dict]:
        def _gate(stage: str) -> dict:
            return next(e for e in entries if (e["stage"], e["action"]) == (stage, "approve"))

        ta, ft = _gate("screening_ta"), _gate("screening_ft")
        rechazo = {
            **ft,
            "action": "reject",
            "detail": {**ft["detail"], "decision_sha256": "0" * 64},
        }
        otra_ta = {**ta, "detail": {**ta["detail"], "decision_sha256": "1" * 64, "reason": "otra"}}
        i = entries.index(ta) + 1
        return [*entries[:i], rechazo, otra_ta, *entries[i:]]

    edit_ledger(corrida, _rechazo_y_vuelta)
    report = auditar(corrida)
    assert fila(report, "ledger").status == "PASS"
    assert fila(report, "final_gate").status == "PASS"
