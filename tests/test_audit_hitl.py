"""Supervisión humana y gate final: ``hitl`` y ``final_gate`` (spec 2026-10-04 §9.3).

D8: ``auto-approve (demo)`` o ``auto-proceed`` en un gate de juicio o en el
final es FAIL. Una etapa de juicio alcanzada sin decisión humana, un gate
saltado o una decisión humana sin su ``review_request.yml`` también.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from audit_fixtures import auditar, edit_json, edit_ledger, fila

from revisia.audit.artifacts import AuditContext, load_run
from revisia.audit.checks_hitl import check_final_gate, de_la_decision_efectiva
from revisia.audit.state import RunState
from revisia.config import STAGES
from revisia.provenance.ledger import AUTO_APPROVE_ACTOR, DecisionEntry
from revisia.schemas.artifacts import GATED_STAGES, GateSummary

# La corrida real ya trae etiquetas por registro: en el texto completo (A0) la revisora etiqueta
# los 4 recuperados y excluye uno ("secundario"). Esa `label` respalda la exclusión humana que
# declara exclusions.json; los tests que añaden etiquetas suman las suyas a esa.
_ETIQUETAS_FT = 4
_EXCLUSIONES_FT = 1


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
    # La revisora excluyó "secundario" a texto completo (A0): la exclusión
    # humana de exclusions.json tiene su `label` con `to: exclude` en el ledger.
    exclusions = json.loads((corrida / "03_screening" / "exclusions.json").read_text("utf-8"))
    assert exclusions["excluded_human"] == _EXCLUSIONES_FT
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "PASS"
    assert f"{_ETIQUETAS_FT} etiqueta(s) por registro" in hitl.detail


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
    """Etiquetas de T/A ante una aprobación efectiva con hashes conocidos; las `label` van antes.

    ``excluded_human`` es el total que declara exclusions.json (incluida la exclusión humana a
    texto completo de la corrida real, ``_EXCLUSIONES_FT``).
    """

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
    _etiquetar(corrida, _etiqueta("10.1000/cocina"), excluded_human=_EXCLUSIONES_FT + 1)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "PASS", hitl.detail
    assert f"{_ETIQUETAS_FT + 1} etiqueta(s) por registro" in hitl.detail


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
    # Una etiqueta válida y otra huérfana (`motivo`) en T/A, más la exclusión a texto completo
    # de la corrida: `excluded_human` las cuenta todas y la huérfana no tiene respaldo.
    declaradas = _EXCLUSIONES_FT + 2
    _etiquetar(
        corrida,
        _etiqueta("10.1000/cocina"),
        {"target": "10.1000/botanica", **huerfana},
        excluded_human=declaradas,
    )
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL", motivo
    assert f"exclusions.json declara {declaradas} exclusiones humanas" in hitl.detail
    assert f"solo registra {declaradas - 1} etiqueta(s) `exclude`" in hitl.detail
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
    # dos exclusiones de T/A con un solo registro etiquetado siguen sin respaldo. La exclusión a
    # texto completo de la corrida sí lo tiene (y se suma a lo declarado).
    esperado = _EXCLUSIONES_FT + (2 if len(etiquetas) == 2 else 1)
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
        for entry in entries:  # la decisión de screening_ft (y sus etiquetas)
            if entry["stage"] == "screening_ft":
                entry["actor"] = enorme

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
    # Sin la etiqueta FT de la corrida, su exclusión humana ya no tiene respaldo: eso es otro
    # FAIL de `hitl` (C3), no lo que se prueba aquí.
    edit_json(corrida / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=0))
    report = auditar(corrida)
    hitl = fila(report, "hitl")
    assert hitl.status == "N/A"
    assert "en pausa en `screening_ta`" in hitl.detail
    assert fila(report, "final_gate").status == "FAIL"


# ── Estado de la corrida y gate final ─────────────────────────────────


def test_pausa_en_screening_ft_final_gate_falla_y_hitl_pasa_en_ta(corrida_en_pausa_ft) -> None:
    report = auditar(corrida_en_pausa_ft)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert final_gate.detail == "corrida en pausa en `screening_ft`: sin decisión final."
    hitl = fila(report, "hitl")
    assert hitl.status == "PASS"
    assert "decisión humana en 1 etapa(s)" in hitl.detail
    for check_id in ("arithmetic", "deliverable", "grounding", "exclusions"):
        assert fila(report, check_id).status == "N/A"


def test_corrida_interrumpida_sin_solicitud_falla_el_gate_final(corrida_en_pausa_ft) -> None:
    (corrida_en_pausa_ft / "screening_ft" / "review_request.yml").unlink()
    report = auditar(corrida_en_pausa_ft)
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


# ── de_la_decision_efectiva (pública: la usan hitl y grounding) ───────────


def _contexto(**hashes: str | None) -> SimpleNamespace:
    """Un contexto con la decisión efectiva de ``screening_ta`` (solo ``gates`` se consulta)."""
    gate = GateSummary(
        stage="screening_ta",
        action="approve",
        actor="human:ana",
        autonomy="A1",
        timestamp_utc="2026-10-04T12:00:00+00:00",
        **hashes,
    )
    return SimpleNamespace(gates={"screening_ta": gate})


def _label(stage: str = "screening_ta", **detalle: str) -> DecisionEntry:
    return DecisionEntry(
        stage=stage, actor="human:ana", autonomy="A1", action="label", target="r1", detail=detalle
    )


@pytest.mark.parametrize(
    ("hashes", "detalle", "esperado"),
    [
        pytest.param(
            {"decision_sha256": "d", "request_sha256": "r"},
            {"decision_sha256": "d", "request_sha256": "r"},
            True,
            id="mismos-hashes",
        ),
        pytest.param(
            {"decision_sha256": "d", "request_sha256": "r"},
            {"decision_sha256": "otra", "request_sha256": "r"},
            False,
            id="otra-decision",
        ),
        # Exige también el `request_sha256`: no basta el `decision_sha256` (como `n_labels`).
        pytest.param(
            {"decision_sha256": "d", "request_sha256": "r"},
            {"decision_sha256": "d", "request_sha256": "otra"},
            False,
            id="otra-solicitud",
        ),
        pytest.param(
            {"decision_sha256": "d", "request_sha256": "r"},
            {"decision_sha256": "d"},
            False,
            id="sin-solicitud",
        ),
        pytest.param({"decision_sha256": "d", "request_sha256": "r"}, {}, False, id="sin-hashes"),
        # Ledger anterior a PR-D: ni la aprobación ni las `label` llevan hashes y cuentan todas...
        pytest.param({}, {}, True, id="pre-PR-D-ambos-sin-hash"),
        # ... pero una `label` con hash frente a una aprobación sin él es de otra decisión.
        pytest.param({}, {"decision_sha256": "d"}, False, id="pre-PR-D-label-con-hash"),
    ],
)
def test_de_la_decision_efectiva_compara_decision_y_solicitud(
    hashes: dict, detalle: dict, esperado: bool
) -> None:
    assert de_la_decision_efectiva(_contexto(**hashes), _label(**detalle)) is esperado


def test_de_la_decision_efectiva_de_una_etapa_sin_decision_es_falso() -> None:
    assert de_la_decision_efectiva(_contexto(), _label(stage="rob")) is False


# ── Ramas defensivas y fallback anterior a PR-D, de punta a punta ─────────


def test_hitl_etiqueta_con_hash_frente_a_una_aprobacion_sin_hash_no_respalda(corrida) -> None:
    # Sentido inverso del fallback anterior a PR-D: con una aprobación de T/A sin hashes (como en
    # un ledger de la fase 1), una `label` que sí lleva `decision_sha256` es de otra decisión.
    def _etiqueta_con_hash(entries: list[dict]) -> list[dict]:
        aprobacion = entries[0]
        assert (aprobacion["stage"], aprobacion["action"]) == ("screening_ta", "approve")
        aprobacion["detail"] = {}
        etiqueta = {**aprobacion, "action": "label", "target": "10.1000/cocina"}
        return [{**etiqueta, "detail": _detalle()}, *entries]

    declaradas = _EXCLUSIONES_FT + 1
    edit_ledger(corrida, _etiqueta_con_hash)
    edit_json(
        corrida / "03_screening" / "exclusions.json",
        lambda e: e.update(excluded_human=declaradas),
    )
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert f"exclusions.json declara {declaradas} exclusiones humanas" in hitl.detail
    assert "además, 1 etiqueta(s) `exclude` ajenas a esa decisión no cuentan" in hitl.detail


def test_hitl_con_el_estado_desconocido_exige_cada_etapa_de_juicio(corrida) -> None:
    # Con una línea ilegible y sin run.json el estado queda en `unknown` y se exige todo: las
    # etapas de juicio sin decisión (y sin otra posterior decidida) son «alcanzadas sin
    # decisión». La corrida de la Ola 1 tiene run.json: se quita (como en una anterior).
    (corrida / "run.json").unlink()
    edit_ledger(corrida, lambda entries: [e for e in entries if e["stage"] == "screening_ta"])
    with (corrida / "decisions_ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("esto no es json\n")
    report = auditar(corrida)
    assert report.state is not None and report.state.status == "unknown"
    hitl = fila(report, "hitl")
    assert hitl.status == "FAIL"
    for etapa in ("screening_ft", "extraccion", "rob"):
        assert f"`{etapa}` alcanzada sin decisión" in hitl.detail
    assert "gate saltado" not in hitl.detail


def test_final_gate_rechazo_sin_decision_efectiva_nombra_un_actor_desconocido(corrida) -> None:
    # Rama defensiva: `state` sale de `gates`, así que un rechazo siempre tiene decisión. Con un
    # estado inyectado que no la tiene, el detalle no revienta ni inventa un actor.
    ctx = AuditContext(load_run(corrida))
    ctx.__dict__["state"] = RunState("rejected", frozenset(STAGES), "reporte")
    ctx.__dict__["gates"] = {}
    status, detalle = check_final_gate(ctx)
    assert status == "FAIL"
    assert detalle == "El reporte final fue rechazado por un actor desconocido."
    ctx.__dict__["state"] = RunState("rejected", frozenset(STAGES), "rob")
    status, detalle = check_final_gate(ctx)
    assert status == "FAIL"
    assert "por un actor desconocido: sin decisión final" in detalle
