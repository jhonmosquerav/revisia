"""Supervisión humana y gate final: ``hitl`` y ``final_gate`` (spec 2026-10-04 §9.3).

D8: ``auto-approve (demo)`` o ``auto-proceed`` en un gate de juicio o en el
final es FAIL. Una etapa de juicio alcanzada sin decisión humana, un gate
saltado o una decisión humana sin su ``review_request.yml`` también.
"""

from __future__ import annotations

import json

import pytest
from audit_fixtures import auditar, edit_json, edit_ledger, fila, pausar_en_screening_ft

from revisia.provenance.ledger import AUTO_APPROVE_ACTOR
from revisia.schemas.artifacts import GATED_STAGES


def _actor(stage: str, actor: str):
    def _editar(entries: list[dict]) -> None:
        for entry in entries:
            if entry["stage"] == stage:
                entry["actor"] = actor

    return _editar


@pytest.mark.parametrize("gate", GATED_STAGES)
def test_hitl_auto_approve_en_cualquier_gate_falla(corrida, gate: str) -> None:
    edit_ledger(corrida, _actor(gate, "auto-approve (demo)"))
    report = auditar(corrida)
    hitl = fila(report, "hitl")
    assert hitl.status == "FAIL"
    assert f"decisiones de `auto-approve (demo)` en {gate}" in hitl.detail
    assert not report.publishable
    if gate == "reporte":
        assert fila(report, "final_gate").status == "FAIL"


def test_hitl_excluded_human_sin_etiquetas_falla(corrida) -> None:
    # Síntoma C3, por una vía que no necesita decisions.json.
    edit_json(corrida / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=3))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "exclusions.json declara 3 exclusiones humanas" in hitl.detail


def test_hitl_etiquetas_exclude_respaldan_exclusiones_humanas(corrida) -> None:
    def _etiqueta(entries: list[dict]) -> list[dict]:
        ta = entries[0]
        label = {
            **ta,
            "action": "label",
            "target": "10.1000/cocina",
            "detail": {"from": "exclude", "to": "exclude", "reason": "fuera de alcance"},
        }
        return [label, *entries]

    edit_ledger(corrida, _etiqueta)
    edit_json(corrida / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=1))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "PASS"
    assert "1 etiqueta(s) por registro" in hitl.detail


# ── Solo cuentan las etiquetas de la decisión efectiva (revisión de la Tarea 8) ──
#
# Tras un fallo y un `decision.yml` cambiado, o tras un rechazo y una nueva decisión
# (D14), el ledger conserva `label` de decisiones sustituidas. Contarlas todas taparía
# una inflación de `excluded_human` tipo C3.

_SOLICITUD = "r" * 64
_DECISION = "d" * 64


def _detalle(
    *, to: str = "exclude", decision: str | None = _DECISION, solicitud=_SOLICITUD
) -> dict:
    detalle: dict = {"from": "include", "to": to, "reason": "fuera de alcance"}
    if decision is not None:
        detalle["decision_sha256"] = decision
        detalle["request_sha256"] = solicitud
    return detalle


def _etiqueta(target: str, **cambios) -> dict:
    return {"target": target, "detail": _detalle(), **cambios}


def _etiquetar(corrida, *etiquetas: dict, excluded_human: int) -> None:
    """La aprobación efectiva de T/A lleva hashes (como en PR-D) y las `label` van antes."""

    def _editar(entries: list[dict]) -> list[dict]:
        i = next(
            i
            for i, e in enumerate(entries)
            if (e["stage"], e["action"]) == ("screening_ta", "approve")
        )
        aprobacion = entries[i]
        aprobacion["detail"] = {"request_sha256": _SOLICITUD, "decision_sha256": _DECISION}
        labels = [{**aprobacion, "action": "label", **etiqueta} for etiqueta in etiquetas]
        return [*entries[:i], *labels, *entries[i:]]

    edit_ledger(corrida, _editar)
    edit_json(
        corrida / "03_screening" / "exclusions.json",
        lambda e: e.update(excluded_human=excluded_human),
    )


def test_hitl_etiquetas_de_la_decision_efectiva_respaldan_las_exclusiones(corrida) -> None:
    _etiquetar(corrida, _etiqueta("10.1000/cocina"), excluded_human=1)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "PASS", hitl.detail
    assert "1 etiqueta(s) por registro" in hitl.detail


@pytest.mark.parametrize(
    ("huerfana", "motivo"),
    [
        pytest.param(
            {"detail": _detalle(decision="o" * 64)},
            "otro decision_sha256",
            id="decision-sustituida",
        ),
        pytest.param(
            {"detail": _detalle(solicitud="s" * 64)}, "otro request_sha256", id="otra-solicitud"
        ),
        pytest.param({"detail": _detalle(decision=None)}, "sin hashes", id="sin-hashes"),
    ],
)
def test_hitl_etiquetas_huerfanas_no_respaldan_exclusiones_humanas(
    corrida, huerfana: dict, motivo: str
) -> None:
    # Una etiqueta válida y otra huérfana (`motivo`); `excluded_human: 2` solo tiene
    # respaldo de una de ellas.
    _etiquetar(
        corrida,
        _etiqueta("10.1000/cocina"),
        {"target": "10.1000/botanica", **huerfana},
        excluded_human=2,
    )
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL", motivo
    assert "exclusions.json declara 2 exclusiones humanas" in hitl.detail
    assert "solo registra 1 etiqueta(s) `exclude`" in hitl.detail
    assert "además, 1 etiqueta(s) `exclude` ajenas a esa decisión no cuentan" in hitl.detail


@pytest.mark.parametrize(
    "etiquetas",
    [
        pytest.param([_etiqueta("10.1000/cocina", actor="agent:cribador")], id="actor-no-humano"),
        pytest.param([_etiqueta("10.1000/cocina", actor=AUTO_APPROVE_ACTOR)], id="auto-approve"),
        pytest.param(
            [{"target": "10.1000/cocina", "detail": _detalle(to="include")}], id="include"
        ),
        pytest.param([_etiqueta("10.1000/cocina", stage="rob")], id="etapa-sin-etiquetas"),
        pytest.param([_etiqueta("10.1000/cocina"), _etiqueta("10.1000/cocina")], id="duplicada"),
    ],
)
def test_hitl_etiquetas_que_no_son_una_exclusion_humana_no_cuentan(corrida, etiquetas) -> None:
    # `duplicada` cuenta una sola vez: la tupla de una etiqueta es única (spec §4.3), y
    # `excluded_human: 2` con un solo registro etiquetado sigue sin respaldo.
    esperado = 2 if len(etiquetas) == 2 else 1
    _etiquetar(corrida, *etiquetas, excluded_human=esperado)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert f"exclusions.json declara {esperado} exclusiones humanas" in hitl.detail


def test_hitl_actor_desconocido_advierte(corrida) -> None:
    edit_ledger(corrida, _actor("screening_ft", "human:desconocido"))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "WARN"
    assert "`screening_ft`: actor `human:desconocido`" in hitl.detail


def test_hitl_gate_saltado_falla(corrida) -> None:
    edit_ledger(corrida, lambda entries: [e for e in entries if e["stage"] != "screening_ft"])
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "gate saltado: `screening_ft` sin decisión y `extraccion` decidida" in hitl.detail


def test_hitl_decision_humana_sin_solicitud_falla(corrida) -> None:
    (corrida / "extraccion" / "review_request.yml").unlink()
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`extraccion`: decisión humana sin solicitud" in hitl.detail


def test_hitl_corrida_real_pasa(corrida) -> None:
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "PASS"
    assert "decisión humana en 4 etapa(s) de juicio" in hitl.detail


def test_hitl_actor_human_sin_dos_puntos_no_es_humano(corrida) -> None:
    # Revisión de la Tarea 5: `human` (sin `:`) no es un `human:<nombre>`; con
    # `startswith("human")` pasaba por humano.
    edit_ledger(corrida, _actor("screening_ft", "human"))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`screening_ft`: decisión efectiva de `human` (approve), no humana" in hitl.detail


def test_final_gate_actor_human_sin_dos_puntos_falla(corrida) -> None:
    edit_ledger(corrida, _actor("reporte", "human"))
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "no lo aprobó un humano: human/approve" in final_gate.detail


def test_hitl_rechazo_no_humano_en_un_gate_intermedio_falla(corrida) -> None:
    # La etapa rechazada no cuenta como "alcanzada" para el estado, pero su decisión
    # efectiva tampoco puede ser de un actor que no sea humano.
    def _rechazar_ft(entries: list[dict]) -> list[dict]:
        ft = next(e for e in entries if (e["stage"], e["action"]) == ("screening_ft", "approve"))
        previas = [e for e in entries if e["stage"] == "screening_ta"]
        return [*previas, {**ft, "action": "reject", "actor": "agent:revisor"}]

    edit_ledger(corrida, _rechazar_ft)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`screening_ft`: decisión efectiva de `agent:revisor` (reject), no humana" in hitl.detail


def test_hitl_volver_a_decidir_tras_un_rechazo_pasa(corrida) -> None:
    # D14: la decisión efectiva es la última; el rechazo previo (humano) no la invalida.
    def _rechazo_y_vuelta(entries: list[dict]) -> list[dict]:
        i = next(
            i
            for i, e in enumerate(entries)
            if (e["stage"], e["action"]) == ("screening_ft", "approve")
        )
        return [*entries[:i], {**entries[i], "action": "reject"}, *entries[i:]]

    edit_ledger(corrida, _rechazo_y_vuelta)
    report = auditar(corrida)
    assert fila(report, "hitl").status == "PASS"
    assert fila(report, "final_gate").status == "PASS"


def test_hitl_acota_los_textos_hostiles_del_ledger(corrida) -> None:
    # Etapa y actor son texto libre del ledger: ni se copian enteros ni rompen el
    # ordenado por `STAGES` (`.index` de una etapa que no existe lanzaría).
    enorme = "x" * 10_000

    def _hostil(entries: list[dict]) -> None:
        entries[0]["stage"] = enorme
        entries[0]["actor"] = AUTO_APPROVE_ACTOR
        entries[1]["actor"] = enorme  # screening_ft

    edit_ledger(corrida, _hostil)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "error interno" not in hitl.detail
    assert len(hitl.detail) < 1_500
    assert enorme not in hitl.detail


def test_hitl_lista_acotada_de_etapas_con_auto_approve(corrida) -> None:
    def _muchas_etapas(entries: list[dict]) -> None:
        for i in range(12):
            entries.append({**entries[0], "stage": f"etapa-{i:02d}", "actor": AUTO_APPROVE_ACTOR})

    edit_ledger(corrida, _muchas_etapas)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "(+7 más)" in hitl.detail
    assert "etapa-11" not in hitl.detail  # solo se listan las primeras


def test_hitl_sin_ninguna_decision_de_juicio_es_na_y_el_gate_final_falla(corrida) -> None:
    # Un ledger sin decisiones de gate (solo una etiqueta suelta): ninguna etapa de juicio
    # que evaluar, no un PASS vacío. El N/A lo respalda el FAIL de `final_gate` (§9.2).
    def _solo_una_etiqueta(entries: list[dict]) -> list[dict]:
        etiqueta = {"target": "10.1000/cocina", "detail": _detalle(decision=None)}
        return [{**entries[0], "action": "label", **etiqueta}]

    edit_ledger(corrida, _solo_una_etiqueta)
    report = auditar(corrida)
    hitl = fila(report, "hitl")
    assert hitl.status == "N/A"
    assert "en pausa en `screening_ta`" in hitl.detail
    assert fila(report, "final_gate").status == "FAIL"


# ── Estado de la corrida y gate final ─────────────────────────────────


def test_pausa_en_screening_ft_final_gate_falla_y_hitl_pasa_en_ta(corrida) -> None:
    pausar_en_screening_ft(corrida)
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert final_gate.detail == "corrida en pausa en `screening_ft`: sin decisión final."
    hitl = fila(report, "hitl")
    assert hitl.status == "PASS"
    assert "decisión humana en 1 etapa(s)" in hitl.detail
    for check_id in ("arithmetic", "deliverable", "grounding", "exclusions"):
        assert fila(report, check_id).status == "N/A"


def test_corrida_interrumpida_sin_solicitud_falla_el_gate_final(corrida) -> None:
    pausar_en_screening_ft(corrida)
    (corrida / "screening_ft" / "review_request.yml").unlink()
    report = auditar(corrida)
    assert report.state is not None and report.state.status == "interrupted"
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "corrida interrumpida en `screening_ft`" in final_gate.detail


def test_rechazo_en_un_gate_intermedio_falla_el_gate_final(corrida) -> None:
    def _rechazar_ft(entries: list[dict]) -> list[dict]:
        ft = next(e for e in entries if (e["stage"], e["action"]) == ("screening_ft", "approve"))
        previas = [e for e in entries if e["stage"] == "screening_ta"]
        return [*previas, {**ft, "action": "reject"}]

    edit_ledger(corrida, _rechazar_ft)
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "corrida rechazada en `screening_ft` por human:revisora" in final_gate.detail


def test_final_gate_aprobacion_sin_solicitud_falla(corrida) -> None:
    # Síntoma C3: un `approve` humano de reporte que no pasó por el gate.
    (corrida / "reporte" / "review_request.yml").unlink()
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "falta `reporte/review_request.yml`" in final_gate.detail


@pytest.mark.parametrize(
    "linea",
    [
        pytest.param('{"stage": "reporte", "action": "reject"\n', id="json-truncado"),
        pytest.param(
            json.dumps({"stage": "reporte", "autonomy": "A1", "action": "reject", "detail": {}})
            + "\n",
            id="sin-actor",
        ),
    ],
)
def test_linea_ilegible_tras_la_aprobacion_final_no_deja_pasar_el_gate_final(
    corrida, linea: str
) -> None:
    # Revisión de la Tarea 5: tras una aprobación válida de `reporte`, una línea que no se
    # puede leer puede ser un `reject`. Ni `final_gate` ni `hitl` pueden dar PASS mientras
    # `ledger` da FAIL: la decisión efectiva no es verificable.
    with (corrida / "decisions_ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(linea)
    report = auditar(corrida)
    assert fila(report, "ledger").status == "FAIL"
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "1 línea(s) ilegible(s)" in final_gate.detail
    assert fila(report, "hitl").status == "FAIL"
    assert not report.publishable
