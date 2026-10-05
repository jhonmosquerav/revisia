"""Calidad: ``thresholds`` (D7), ``grounding`` (D8), ``search_window`` y ``registration``.

Spec 2026-10-04 §9.3 (filas 16, 17, 19, 20) y §9.4 (familias ``thresholds`` y
``grounding``). La corrida real tiene ``recall_target: 0.95`` y un gold de 4
positivos (recall 1.0): sin potencia, así que su ``thresholds`` es WARN.

Los artefactos y el protocolo son entrada no confiable: un umbral ``nan``/``inf``/
negativo/``> 1`` o una métrica absurda no pueden lanzar ni llenar el detalle.
"""

from __future__ import annotations

import math

import pytest
from audit_fixtures import (
    auditar,
    edit_json,
    edit_ledger,
    editar_protocolo,
    escribir_metricas,
    fila,
    metricas_validas,
    write_legacy_v07,
)

from revisia.audit import checks_quality
from revisia.audit.artifacts import AuditContext, load_run
from revisia.audit.checks_quality import potencia_minima

# ── thresholds (D7) ────────────────────────────────────────────────────


def test_potencia_minima_del_gold() -> None:
    assert potencia_minima(0.95) == 20
    assert potencia_minima(0.9) == 10
    assert potencia_minima(0.8) == 5
    assert potencia_minima(1.0) is None


@pytest.mark.parametrize(
    "umbral",
    [math.nan, math.inf, -math.inf, 0.0, -0.5, 1.5, 2.0],
    ids=["nan", "inf", "-inf", "cero", "negativo", "1.5", "2"],
)
def test_potencia_minima_de_un_umbral_no_medible_es_none_y_no_lanza(umbral: float) -> None:
    # `1 / (1 - 1.0)` era un ZeroDivisionError y `nan` un ValueError en `math.ceil`.
    assert potencia_minima(umbral) is None


def test_thresholds_recall_bajo_umbral_con_exclusiones_ia_sin_revisar_falla(corrida) -> None:
    escribir_metricas(corrida, metricas_validas(18, 0, 2, 10))
    report = auditar(corrida)
    thresholds = fila(report, "thresholds")
    assert thresholds.status == "FAIL"
    assert "recall 0.90 [IC95 0.70–0.97] < 0.95 con 20 positivos" in thresholds.detail
    assert "2 exclusiones IA de T/A sin etiqueta humana" in thresholds.detail
    assert "screening_ta/decision.yml" in thresholds.detail
    assert not report.publishable


def test_thresholds_kappa_cero_bajo_kappa_min_advierte_nunca_pasa(corrida) -> None:
    # El caso exacto de A11: κ = 0.0 daba PASS. Con recall alto y gold
    # suficiente, un κ bajo es sobreinclusión: desviación a declarar (WARN).
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kappa_min": 0.6})
    )
    escribir_metricas(corrida, metricas_validas(20, 5, 0, 0))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "κ 0.00 < 0.60: desviación del protocolo, decláralo (PRISMA 24c)" in thresholds.detail
    assert "recall 1.00 [IC95 0.84–1.00] ≥ 0.95 con 20 positivos" in thresholds.detail


def test_thresholds_recall_igual_al_umbral_con_gold_suficiente_pasa(corrida) -> None:
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kappa_min": 0.6})
    )
    escribir_metricas(corrida, metricas_validas(19, 0, 1, 10))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "PASS"
    assert thresholds.detail == (
        "recall 0.95 [IC95 0.76–0.99] ≥ 0.95 con 20 positivos; κ 0.93 ≥ 0.60."
    )


def test_thresholds_recall_perfecto_con_pocos_positivos_advierte(corrida) -> None:
    escribir_metricas(corrida, metricas_validas(5, 0, 0, 5))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "recall 1.00 [IC95 0.57–1.00] ≥ 0.95 con solo 5 positivos" in thresholds.detail
    assert "con menos de 20 un solo fallo ya baja del umbral" in thresholds.detail


def test_thresholds_recall_bajo_con_gold_pequeno_sigue_fallando(corrida) -> None:
    # Un recall por debajo nunca se excusa por gold pequeño (D7).
    escribir_metricas(corrida, metricas_validas(3, 0, 1, 4))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "FAIL"
    assert "recall 0.75 [IC95 0.30–0.95] < 0.95 con 4 positivos" in thresholds.detail


def test_thresholds_declarado_sin_gold_advierte(corrida) -> None:
    (corrida / "03_screening" / "metrics.json").unlink()
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "recall_target 0.95 no medible (sin gold)" in thresholds.detail


def test_thresholds_clave_desconocida_advierte(corrida) -> None:
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kapa_min": 0.6})
    )
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "clave(s) desconocida(s) en thresholds: `kapa_min`" in thresholds.detail


def test_thresholds_sin_umbrales_advierte(corrida) -> None:
    editar_protocolo(corrida, lambda p: p.update(thresholds={}))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "ningún umbral declarado" in thresholds.detail


# Un umbral del protocolo que no es un número en rango no se puede medir: WARN con un detalle
# acotado, nunca un ZeroDivisionError/ValueError («error interno») ni un PASS vacuo.
@pytest.mark.parametrize(
    "umbral",
    [math.nan, math.inf, -0.5, 1.5, 0.0],
    ids=["nan", "inf", "negativo", "mayor-que-1", "cero"],
)
def test_thresholds_recall_target_no_medible_advierte_sin_lanzar(corrida, umbral: float) -> None:
    editar_protocolo(corrida, lambda p: p.update(thresholds={"recall_target": umbral}))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "recall_target" in thresholds.detail
    assert "no medible (debe ser un número en (0, 1])" in thresholds.detail
    assert "error interno" not in thresholds.detail
    assert len(thresholds.detail) < 300


@pytest.mark.parametrize(
    "umbral",
    [math.nan, math.inf, -0.1, 1.5],
    ids=["nan", "inf", "negativo", "mayor-que-1"],
)
def test_thresholds_kappa_min_no_medible_advierte_sin_lanzar(corrida, umbral: float) -> None:
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kappa_min": umbral})
    )
    escribir_metricas(corrida, metricas_validas(20, 5, 0, 5))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "kappa_min" in thresholds.detail
    assert "no medible (debe ser un número en [0, 1])" in thresholds.detail
    assert "error interno" not in thresholds.detail
    assert len(thresholds.detail) < 400


def test_thresholds_decide_con_el_recall_de_la_matriz_y_no_con_el_guardado(corrida) -> None:
    # Revisión de la fase 1 de PR-E: el IC de Wilson y los positivos ya salían de la matriz, pero
    # la decisión usaba el `recall` de `metrics.json`: un 1.0 guardado con una matriz que da 0.25
    # (tp=1, fn=3) pasaba el umbral sobre una cifra que el propio detalle desmentía.
    escribir_metricas(corrida, {**metricas_validas(1, 0, 3, 10), "recall": 1.0})
    report = auditar(corrida)
    thresholds = fila(report, "thresholds")
    assert thresholds.status == "FAIL"
    assert "recall 0.25 [IC95 0.05–0.70] < 0.95 con 4 positivos" in thresholds.detail
    assert "recall 1.00" not in thresholds.detail
    assert fila(report, "arithmetic").status == "FAIL"  # la discrepancia la marca `arithmetic`
    assert not report.publishable


@pytest.mark.parametrize(
    "recall", [math.nan, math.inf, 1.5, -0.2], ids=["nan", "inf", "1.5", "-0.2"]
)
def test_thresholds_con_un_recall_guardado_absurdo_decide_con_la_matriz(corrida, recall) -> None:
    # El recall guardado ya no entra en la decisión: la matriz (20 positivos, recall 1.0) manda y
    # `arithmetic` marca que `metrics.json` no cuadra consigo mismo.
    escribir_metricas(corrida, {**metricas_validas(20, 5, 0, 5), "recall": recall})
    report = auditar(corrida)
    thresholds = fila(report, "thresholds")
    assert thresholds.status == "PASS", thresholds.detail
    assert thresholds.detail == "recall 1.00 [IC95 0.84–1.00] ≥ 0.95 con 20 positivos."
    assert fila(report, "arithmetic").status == "FAIL"
    assert not report.publishable


def test_thresholds_matriz_con_celdas_negativas_advierte_sin_lanzar(corrida) -> None:
    # Pydantic admite `tp < 0`: Wilson daría `sqrt` de un negativo (ValueError).
    escribir_metricas(corrida, {**metricas_validas(5, 0, 5, 10), "tp": -5})
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "no medible (matriz de confusión fuera de rango" in thresholds.detail
    assert "error interno" not in thresholds.detail


@pytest.mark.parametrize("kappa", [1e308, 2.0, -1.5], ids=["1e308", "2", "menos-1.5"])
def test_thresholds_kappa_fuera_de_su_rango_no_es_verificable(corrida, kappa: float) -> None:
    # κ ∈ [-1, 1]: fuera de ese intervalo es un dato corrupto, no un PASS. Con 1e308, además,
    # `:.2f` escribía 313 caracteres en el detalle.
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kappa_min": 0.6})
    )
    escribir_metricas(corrida, {**metricas_validas(20, 5, 0, 5), "cohen_kappa": kappa})
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "κ" in thresholds.detail and "fuera de [-1, 1]: no verificable" in thresholds.detail
    assert len(thresholds.detail) < 300


def test_thresholds_kappa_en_el_limite_con_redondeo_no_se_marca_fuera_de_rango(corrida) -> None:
    # Un MCC o un κ calculado en coma flotante puede salir 1.0000000000000002: no es un dato
    # corrupto. La holgura es de 1e-9; `arithmetic` ya compara con esa misma tolerancia.
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kappa_min": 0.6})
    )
    escribir_metricas(corrida, {**metricas_validas(20, 5, 0, 5), "cohen_kappa": 1.0000000000000002})
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "PASS", thresholds.detail
    assert "κ 1.00 ≥ 0.60" in thresholds.detail


def test_gold_con_cifras_enormes_o_fuera_de_rango_va_acotado(corrida) -> None:
    # `fmt_metric` de 1e308 daba 313 caracteres por cifra.
    escribir_metricas(corrida, {**metricas_validas(20, 5, 0, 5), "recall": 1e308})
    gold = fila(auditar(corrida), "gold")
    assert "e+308" in gold.detail
    assert len(gold.detail) < 300
    escribir_metricas(
        corrida, {**metricas_validas(20, 5, 0, 5), "cohen_kappa": 1e308, "mcc": -1e308}
    )
    gold = fila(auditar(corrida), "gold")
    assert gold.status == "WARN"
    assert "kappa y MCC fuera de [-1, 1]: no verificable" in gold.detail
    assert len(gold.detail) < 300


def test_thresholds_kappa_no_finito_es_indefinido(corrida) -> None:
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kappa_min": 0.6})
    )
    escribir_metricas(corrida, {**metricas_validas(20, 5, 0, 5), "cohen_kappa": math.nan})
    report = auditar(corrida)
    thresholds = fila(report, "thresholds")
    assert thresholds.status == "WARN"
    assert "kappa_min 0.60 no medible (κ indefinido)" in thresholds.detail  # `nan < 0.6` es falso
    gold = fila(report, "gold")
    assert gold.status == "WARN"
    assert "no calculable" in gold.detail


def test_thresholds_enteros_enormes_no_desbordan_wilson_ni_el_detalle(corrida) -> None:
    # Un entero de 4 000 cifras carga en JSON; `z²/n` no cabe en un float (OverflowError).
    enorme = 10**4000
    escribir_metricas(
        corrida, {**metricas_validas(1, 0, 0, 1), "tp": enorme, "n": enorme + 1, "recall": 1.0}
    )
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "PASS"
    assert "recall 1.00 [IC95 no calculable] ≥ 0.95" in thresholds.detail
    assert "error interno" not in thresholds.detail
    assert len(thresholds.detail) < 300


def test_thresholds_suma_de_positivos_que_no_se_convierte_a_texto_no_lanza(corrida) -> None:
    # Dos enteros de 4 300 cifras caben en JSON; su suma (4 301) ya no se convierte a `str`.
    limite = 10**4300 - 1
    escribir_metricas(
        corrida, {**metricas_validas(1, 0, 1, 1), "tp": limite, "fn": limite, "recall": 0.5}
    )
    report = auditar(corrida)
    for check_id in ("thresholds", "gold"):
        assert "error interno" not in fila(report, check_id).detail
    thresholds = fila(report, "thresholds")
    assert thresholds.status == "FAIL"
    assert "con (valor fuera de rango) positivos" in thresholds.detail
    assert len(thresholds.detail) < 500


def test_thresholds_claves_desconocidas_largas_y_numerosas_se_acotan(corrida) -> None:
    claves = {f"kapa_{i}_" + "x" * 500: 0.6 for i in range(20)}
    editar_protocolo(corrida, lambda p: p.update(thresholds={"recall_target": 0.95, **claves}))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "(+15 más)" in thresholds.detail
    assert thresholds.detail.count("kapa_") == 5
    assert "error interno" not in thresholds.detail
    assert len(thresholds.detail) < 1000


# ── grounding (D8) ─────────────────────────────────────────────────────


def _citas(*checks: dict, flagged: bool | None = None):
    def _editar(verification: dict) -> None:
        verification["checks"] = list(checks)
        verification["hallucination_flagged"] = (
            any(not c["exists_in_corpus"] or not c["grounded"] for c in checks)
            if flagged is None
            else flagged
        )

    return _editar


def _cita(cited_id: str, *, existe: bool = True, fundamentada: bool = True) -> dict:
    return {
        "claim": f"Afirmación que cita [{cited_id}].",
        "cited_id": cited_id,
        "exists_in_corpus": existe,
        "grounded": fundamentada,
        "note": None if existe else "id citado no está en el corpus",
    }


VERIFICATION = "06_synthesis/verification.json"
DECISION = "d" * 64  # `decision_sha256` de la aprobación efectiva de `reporte` en estos tests
SOLICITUD = "r" * 64  # su `request_sha256`


def _revision(
    indice: int = 0,
    actor: str = "human:revisora",
    *,
    verdict: str = "false_positive",
    reason: object = "es un año",
    decision: str = DECISION,
    solicitud: str | None = SOLICITUD,
    target: str | None = None,
) -> dict:
    """Los campos de una ``flag_review`` (sobre la plantilla de la aprobación de ``reporte``)."""
    detail: dict = {
        "cited_id": "2019",
        "verdict": verdict,
        "reason": reason,
        "decision_sha256": decision,
    }
    if solicitud is not None:
        detail["request_sha256"] = solicitud
    return {
        "actor": actor,
        "action": "flag_review",
        "target": f"flag:{indice}" if target is None else target,
        "detail": detail,
    }


def _con_adjudicaciones(*revisiones: dict):
    """Fija los hashes de la aprobación efectiva de ``reporte`` y añade las ``flag_review``."""

    def _editar(entries: list[dict]) -> list[dict]:
        *previas, reporte = entries
        reporte["detail"] = {"decision_sha256": DECISION, "request_sha256": SOLICITUD}
        return [*previas, *({**reporte, **r} for r in revisiones), reporte]

    return _editar


def test_grounding_sin_citas_con_incluidos_advierte(corrida) -> None:
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "WARN"
    assert "la síntesis no cita ningún estudio (3 incluidos)" in grounding.detail


def test_grounding_citas_fundamentadas_pasa(corrida) -> None:
    edit_json(corrida / VERIFICATION, _citas(_cita("10.1000/llm-1"), _cita("10.1000/asreview")))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "PASS"
    assert grounding.detail == "2 citas, ninguna marcada; 2/3 incluidos citados."


def test_grounding_marca_sin_adjudicar_falla(corrida) -> None:
    # `[2019]` es el falso positivo conocido del verificador (C2): sin
    # adjudicación humana, la corrida no es publicable (D8).
    edit_json(corrida / VERIFICATION, _citas(_cita("10.1000/llm-1"), _cita("2019", existe=False)))
    report = auditar(corrida)
    grounding = fila(report, "grounding")
    assert grounding.status == "FAIL"
    assert "1 cita(s) marcada(s) sin adjudicar por un humano (D8): índices [1]" in grounding.detail
    assert not report.publishable


def test_grounding_adjudicacion_de_actor_no_humano_falla(corrida) -> None:
    edit_json(corrida / VERIFICATION, _citas(_cita("2019", existe=False)))
    edit_ledger(corrida, _con_adjudicaciones(_revision(0, "agent:verificador")))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "adjudicación de un actor no humano: agent:verificador" in grounding.detail


def test_grounding_adjudicada_por_un_humano_advierte_y_no_bloquea(corrida) -> None:
    edit_json(corrida / VERIFICATION, _citas(_cita("2019", existe=False)))
    edit_ledger(corrida, _con_adjudicaciones(_revision(0)))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "WARN"
    assert grounding.detail == (
        "1 citas marcadas, adjudicadas como falsos positivos por human:revisora: decláralo."
    )


@pytest.mark.parametrize(
    "revision",
    [
        pytest.param(_revision(0, decision="o" * 64), id="decision-sustituida-huerfana"),
        pytest.param(_revision(0, solicitud="q" * 64), id="solicitud-de-otra-decision"),
        pytest.param(_revision(0, solicitud=None), id="sin-request_sha256"),
        pytest.param(_revision(0, verdict="hallucination"), id="veredicto-distinto"),
        pytest.param(_revision(0, reason=""), id="razon-vacia"),
        pytest.param(_revision(0, reason="   "), id="razon-en-blanco"),
        pytest.param(_revision(0, reason=["es", "un", "año"]), id="razon-que-no-es-texto"),
        pytest.param(_revision(1), id="indice-de-otra-cita"),
        pytest.param(_revision(target="flag:" + chr(0xB2)), id="indice-superindice"),
        pytest.param(_revision(target="flag:" + "9" * 5_000), id="indice-de-5000-cifras"),
        pytest.param(_revision(target="cita:0"), id="objetivo-que-no-es-una-bandera"),
    ],
)
def test_grounding_adjudicacion_que_no_cuenta_deja_la_marca_sin_adjudicar(
    corrida, revision: dict
) -> None:
    # Una `flag_review` solo cuenta si es de la decisión efectiva (mismo `decision_sha256` y
    # `request_sha256`): las de una decisión sustituida (D14) son huérfanas y no adjudican.
    edit_json(corrida / VERIFICATION, _citas(_cita("2019", existe=False)))
    edit_ledger(corrida, _con_adjudicaciones(revision))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "1 cita(s) marcada(s) sin adjudicar por un humano (D8): índices [0]" in grounding.detail
    assert "error interno" not in grounding.detail


def test_grounding_adjudicacion_huerfana_no_tapa_a_la_efectiva_de_otra_cita(corrida) -> None:
    edit_json(
        corrida / VERIFICATION,
        _citas(_cita("2019", existe=False), _cita("2020", existe=False)),
    )
    edit_ledger(corrida, _con_adjudicaciones(_revision(0, decision="o" * 64), _revision(1)))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "1 cita(s) marcada(s) sin adjudicar por un humano (D8): índices [0]" in grounding.detail


def test_grounding_sin_decision_efectiva_con_hash_no_hay_adjudicacion(corrida) -> None:
    # Ledger anterior a la Ola 1: la aprobación no lleva `decision_sha256`.
    edit_json(corrida / VERIFICATION, _citas(_cita("2019", existe=False)))

    def _sin_hashes(entries: list[dict]) -> list[dict]:
        *previas, reporte = entries
        reporte["detail"] = {}
        return [*previas, {**reporte, **_revision(0)}, reporte]

    edit_ledger(corrida, _sin_hashes)
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "sin adjudicar por un humano" in grounding.detail


def test_grounding_bandera_inconsistente_falla(corrida) -> None:
    edit_json(corrida / VERIFICATION, _citas(_cita("2019", existe=False), flagged=False))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "bandera inconsistente: hallucination_flagged=False" in grounding.detail


def test_grounding_existe_en_el_corpus_un_id_que_no_esta_incluido_falla(corrida) -> None:
    edit_json(corrida / VERIFICATION, _citas(_cita("10.9999/fantasma")))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "exists_in_corpus: true para ids que no están entre los incluidos: 0" in (
        grounding.detail
    )


def test_grounding_muchas_marcas_y_ids_enormes_se_acotan(corrida) -> None:
    fantasmas = [_cita("10.9999/" + "x" * 500 + str(i)) for i in range(10)]
    marcadas = [_cita(f"20{i}", existe=False) for i in range(30)]
    edit_json(corrida / VERIFICATION, _citas(*fantasmas, *marcadas))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "30 cita(s) marcada(s) sin adjudicar por un humano (D8): índices [10, 11, 12" in (
        grounding.detail
    )
    assert "(+25 más)" in grounding.detail  # índices
    assert "(+7 más)" in grounding.detail  # fantasmas
    assert "error interno" not in grounding.detail
    assert len(grounding.detail) < 1000


def test_grounding_sin_decisiones_ft_legibles_no_afirma_lo_que_no_sabe(corrida) -> None:
    # Sin `04_fulltext/decisions.json` no se pueden contrastar los ids: ni «ninguna marcada»
    # ni «0 incluidos» son verdad comprobada. `stage_artifacts` da el FAIL de la ausencia.
    (corrida / "04_fulltext" / "decisions.json").unlink()
    report = auditar(corrida)
    grounding = fila(report, "grounding")
    assert grounding.status == "WARN"
    assert "no se pueden contrastar con los incluidos" in grounding.detail
    assert fila(report, "stage_artifacts").status == "FAIL"


def test_grounding_sin_verification_no_aplica(corrida) -> None:
    (corrida / VERIFICATION).unlink()
    report = auditar(corrida)
    grounding = fila(report, "grounding")
    assert grounding.status == "N/A"
    assert "ausente" in grounding.detail
    assert fila(report, "stage_artifacts").status == "FAIL"


def test_grounding_no_muta_el_informe_compartido_con_otros_checks(corrida) -> None:
    # `recompute_flag` reescribe `hallucination_flagged`: sobre el modelo del contexto
    # taparía la inconsistencia a los demás checks.
    edit_json(corrida / VERIFICATION, _citas(_cita("2019", existe=False), flagged=False))
    ctx = AuditContext(load_run(corrida))
    status, _ = checks_quality.check_grounding(ctx)
    assert status == "FAIL"
    assert ctx.art.artifact(VERIFICATION).value.hallucination_flagged is False


# ── search_window y registration ──────────────────────────────────────


def test_search_window_fecha_tecleada_solo_advierte(tmp_path) -> None:
    # Síntoma C3: el auditor anterior daba PASS porque el humano tecleó una fecha.
    # Sin 01_search/log.json (corrida v0.7) nadie más la registró.
    window = fila(auditar(write_legacy_v07(tmp_path)), "search_window")
    assert window.status == "WARN"
    assert "fecha tecleada (`executed: 2026-09-20`), no registrada por el motor" in window.detail


def test_search_window_completa_con_fecha_tecleada_sigue_en_warn(corrida) -> None:
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "fecha tecleada (`executed: 2026-06-26`)" in window.detail
    assert "ventana sin" not in window.detail


def test_search_window_sin_from_to_advierte(corrida) -> None:
    editar_protocolo(corrida, lambda p: p.update(search_window={}))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "ventana sin `from` ni `to`" in window.detail
    assert "sin fecha de ejecución: ni `executed` ni 01_search/log.json" in window.detail


def test_search_window_con_fecha_enorme_se_acota(corrida) -> None:
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed="2026-" + "9" * 5_000))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert len(window.detail) < 400


def test_registration_sin_registro_advierte(corrida) -> None:
    editar_protocolo(corrida, lambda p: p.update(registration={}))
    registration = fila(auditar(corrida), "registration")
    assert registration.status == "WARN"
    assert "Sin registro" in registration.detail


def test_registration_con_miles_de_claves_se_acota(corrida) -> None:
    # El detalle de un manifiesto editado a mano no puede crecer con el número de claves (2 000
    # claves daban ~50 KB): se listan las primeras y se cuenta el resto.
    registro = {f"registro{i}": f"valor{i}" for i in range(2_000)}
    editar_protocolo(corrida, lambda p: p.update(registration=registro))
    registration = fila(auditar(corrida), "registration")
    assert registration.status == "PASS"
    assert "(+1990 más)" in registration.detail
    assert registration.detail.count("registro") == 10
    assert len(registration.detail) < 1_000


def test_registration_con_claves_y_valores_enormes_se_acota(corrida) -> None:
    registro = {f"r{i}_" + "k" * 500: "v" * 500 for i in range(30)}
    editar_protocolo(corrida, lambda p: p.update(registration=registro))
    registration = fila(auditar(corrida), "registration")
    assert registration.status == "PASS"
    assert "(+20 más)" in registration.detail
    assert len(registration.detail) < 1_000


def test_search_window_con_una_fecha_yaml_sin_comillas_se_muestra_en_iso(corrida) -> None:
    # PyYAML carga `executed: 2026-06-26` como `datetime.date`: sin `isoformat()` el detalle
    # decía `executed: datetime.date(2026, 6, 26)`.
    manifiesto = corrida / "manifest.yml"
    texto = manifiesto.read_text(encoding="utf-8")
    assert "executed: '2026-06-26'" in texto
    manifiesto.write_text(
        texto.replace("executed: '2026-06-26'", "executed: 2026-06-26"), encoding="utf-8"
    )
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "fecha tecleada (`executed: 2026-06-26`)" in window.detail
