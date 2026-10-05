"""Checks del ledger y de la supervisión humana: ``ledger``, ``hitl``, ``final_gate``.

El ledger es entrada no confiable como el manifiesto: los textos que trae (etapa,
acción, actor…) se acotan con ``short_text`` antes de entrar en un detalle.

Antes de la Ola 1, ``hitl`` nunca daba FAIL y una aprobación de ``--auto-approve``
en el gate final solo era WARN: una corrida sin ninguna decisión humana salía
"APTA para preparar publicación" (auditoría 2026-09-03, C1/A11). Ahora una etapa
de juicio sin decisión humana, un ``auto-approve`` en cualquier gate (D8) o un
gate final sin aprobación humana son FAIL.
"""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext, short_text
from revisia.audit.model import Verdict
from revisia.config import JUDGMENT_STAGES, STAGES
from revisia.orchestration.hitl import HumanDecision
from revisia.provenance.ledger import (
    AUTO_APPROVE_ACTOR,
    GATE_DECISION_ACTIONS,
    HUMAN_ACTOR_PREFIX,
    LEDGER_ACTIONS,
    DecisionEntry,
)
from revisia.schemas.artifacts import GATED_STAGES, GateSummary

_NA_LEDGER = "no aplica: sin ledger legible (ver `ledger`)."
_MAX_PROBLEMAS = 5
_LIMITE_PROBLEMA = 300  # caracteres por problema mostrado
_MAX_LISTADOS = 5  # etapas o actores que se listan dentro de un problema
# Gates donde el motor escribe una `label` por registro etiquetado (spec §4.3).
_ETAPAS_DE_CRIBADO = tuple(s for s in GATED_STAGES if s.startswith("screening_"))
# Actor de un `decision.yml` que no declara `actor:`: un humano sin nombre.
_ACTOR_POR_DEFECTO: str = HumanDecision.model_fields["actor"].default


def effective_autonomy(ctx: AuditContext) -> dict[str, str] | None:
    """Autonomía efectiva de cada gate según el protocolo registrado.

    ``None`` si no hay protocolo legible (sin manifiesto, o corrida en pausa
    antes de escribirlo).
    """
    if ctx.protocol is None:
        return None
    return {gate: ctx.protocol.autonomy_for(gate) for gate in GATED_STAGES}


def _limitar(problems: list[str]) -> str:
    shown = "; ".join(short_text(p, limit=_LIMITE_PROBLEMA) for p in problems[:_MAX_PROBLEMAS])
    more = len(problems) - _MAX_PROBLEMAS
    return shown + (f" (+{more} más)" if more > 0 else "")


def check_ledger(ctx: AuditContext) -> Verdict:
    """trAIce M8 / PRISMA 8: ledger legible, con lo que el motor escribe y en orden.

    Una línea corrupta ya no se descarta en silencio (antes, ``audit.py:85-86``)
    y una acción que ``review_gate`` nunca emite (``propose``/``exclude``/
    ``verify`` en la reconstrucción C3) delata un ledger escrito a mano.
    """
    view = ctx.ledger
    if not view.present:
        return "FAIL", "decisions_ledger.jsonl ausente: sin trazabilidad de decisiones."
    if view.read_error:
        return "FAIL", f"decisions_ledger.jsonl ilegible ({view.read_error})."
    if not view.entries and not view.errors:
        return "FAIL", "decisions_ledger.jsonl vacío: sin trazabilidad de decisiones."

    problems = list(view.errors)
    for number, entry in view.entries:
        if entry.stage not in STAGES:
            problems.append(f"línea {number}: etapa desconocida `{short_text(entry.stage)}`")
        if entry.action not in LEDGER_ACTIONS:
            problems.append(
                f"línea {number}: acción `{short_text(entry.action)}` que el motor no emite"
            )

    # Los gates se deciden por primera vez en el orden de STAGES; tras un
    # rechazo se puede volver a decidir una etapa anterior (D14).
    first: dict[str, int] = {}
    for number, entry in view.entries:
        if entry.action in GATE_DECISION_ACTIONS and entry.stage in STAGES:
            first.setdefault(entry.stage, number)
    ordered = sorted(first, key=first.__getitem__)
    if ordered != sorted(ordered, key=STAGES.index):
        problems.append("gates fuera del orden de STAGES: " + " → ".join(ordered))

    autonomy = effective_autonomy(ctx)
    if autonomy is not None:
        for number, entry in view.entries:
            expected = autonomy.get(entry.stage)
            if expected is not None and entry.autonomy != expected:
                problems.append(
                    f"línea {number}: autonomía {short_text(entry.autonomy)} en "
                    f"`{short_text(entry.stage)}`, la efectiva es {short_text(expected)}"
                )

    if problems:
        return "FAIL", f"{len(problems)} problema(s) en el ledger: {_limitar(problems)}."
    note = "" if autonomy is not None else " (autonomía no verificable: sin protocolo legible)"
    return "PASS", f"{len(view.entries)} entradas válidas, en orden{note}."


def _orden_etapa(stage: str) -> tuple[int, str]:
    """Clave de orden por ``STAGES``; una etapa desconocida (ledger hostil) va al final."""
    return (STAGES.index(stage), "") if stage in STAGES else (len(STAGES), stage)


def _listar(items: list[str]) -> str:
    """Hasta ``_MAX_LISTADOS`` elementos del ledger, acotados, y cuántos no se muestran."""
    shown = ", ".join(short_text(item) for item in items[:_MAX_LISTADOS])
    more = len(items) - _MAX_LISTADOS
    return shown + (f" (+{more} más)" if more > 0 else "")


def _excluded_human(ctx: AuditContext) -> int | None:
    """``excluded_human`` declarado (el fichero o, si no se lee, la copia del manifiesto)."""
    loaded = ctx.art.artifact("03_screening/exclusions.json")
    if loaded.ok:
        return loaded.value.excluded_human
    copy = ctx.manifest_section("exclusions")
    return copy.value.excluded_human if copy.ok else None


def de_la_decision_efectiva(ctx: AuditContext, entry: DecisionEntry) -> bool:
    """La ``label`` o ``flag_review`` ``entry`` pertenece a la decisión efectiva de su etapa.

    Tras un fallo con el ``decision.yml`` cambiado, o tras un rechazo y una nueva
    decisión (D14), el ledger conserva las entradas de las decisiones sustituidas: cuentan
    solo las que llevan el ``decision_sha256`` **y** el ``request_sha256`` de la aprobación
    efectiva. Es la regla de ``n_labels`` de ``summarize_gates`` (mismo ``decision_sha256``)
    más una exigencia: ``summarize_gates`` no mira la solicitud y el auditor sí. Sin decisión
    efectiva en la etapa, ninguna cuenta. Lo usan ``hitl`` (etiquetas por registro) y
    ``grounding`` (adjudicaciones de citas), para que una sola regla evite que se contradigan.
    """
    gate = ctx.gates.get(entry.stage)
    if gate is None:
        return False
    decision = entry.detail.get("decision_sha256")
    if gate.decision_sha256 is None:
        # Ledger anterior a PR-D (fase 1): ni la aprobación ni las `label` llevan hashes y no
        # hay cómo distinguir decisiones, así que cuentan todas las de la etapa. Una `label`
        # con hash frente a una aprobación sin él es de otra decisión.
        return decision is None
    return (
        decision == gate.decision_sha256
        and entry.detail.get("request_sha256") == gate.request_sha256
    )


def _etiquetas_de_cribado(ctx: AuditContext) -> tuple[list[DecisionEntry], list[DecisionEntry]]:
    """``label`` de los gates de cribado: (las de la decisión efectiva, las ajenas a ella)."""
    propias: list[DecisionEntry] = []
    ajenas: list[DecisionEntry] = []
    for entry in ctx.ledger.decisions:
        if entry.action == "label" and entry.stage in _ETAPAS_DE_CRIBADO:
            (propias if de_la_decision_efectiva(ctx, entry) else ajenas).append(entry)
    return propias, ajenas


def _es_exclusion_humana(label: DecisionEntry) -> bool:
    """La ``label`` excluye el registro y la puso un humano (``human:<nombre>``).

    Solo estas respaldan el ``excluded_human`` de ``exclusions.json`` (C3): una ``label`` de un
    agente o de ``auto-approve (demo)``, o una que incluye, no cuenta como exclusión humana.
    """
    return label.detail.get("to") == "exclude" and label.actor.startswith(HUMAN_ACTOR_PREFIX)


def check_hitl(ctx: AuditContext) -> Verdict:
    """trAIce M8/R1 / PRISMA 8: decide un humano en cada etapa de juicio.

    Una etapa de juicio con decisión efectiva debe tenerla de un actor ``human:`` y con
    su ``review_request.yml`` (si no, no pasó por el gate: así era la reconstrucción
    C3); si falta una y hay otra posterior, se saltó un gate. Cualquier
    ``auto-approve (demo)`` del ledger es FAIL (D8). Además, las exclusiones humanas
    que declara ``exclusions.json`` no pueden superar las ``label`` ``exclude`` de la
    decisión efectiva de cada gate de cribado: la vía contra el ``excluded_human: 3``
    de C3, que funciona aunque falte ``decisions.json``.
    """
    view = ctx.ledger
    if not view.entries:
        return "N/A", _NA_LEDGER
    fails: list[str] = []
    warns: list[str] = []

    if view.errors:
        # Una línea ilegible puede ser un `reject` o un `auto-approve`: la decisión
        # efectiva no es verificable (la causa está en `ledger`).
        fails.append(
            f"{len(view.errors)} línea(s) ilegible(s) en el ledger: no se puede saber quién decidió"
        )

    auto = sorted(
        {e.stage for e in view.decisions if e.actor == AUTO_APPROVE_ACTOR}, key=_orden_etapa
    )
    if auto:
        fails.append(
            f"decisiones de `{AUTO_APPROVE_ACTOR}` en {_listar(auto)} "
            "(D8: --auto-approve no es revisión humana)"
        )

    humanas: list[GateSummary] = []
    for stage in JUDGMENT_STAGES:
        gate = ctx.gates.get(stage)
        if gate is None:
            later = [g for g in GATED_STAGES[GATED_STAGES.index(stage) + 1 :] if g in ctx.gates]
            if later:
                fails.append(f"gate saltado: `{stage}` sin decisión y `{later[0]}` decidida")
            elif stage in ctx.state.reached:
                fails.append(f"`{stage}` alcanzada sin decisión")
            continue
        if not gate.actor.startswith(HUMAN_ACTOR_PREFIX):
            fails.append(
                f"`{stage}`: decisión efectiva de `{short_text(gate.actor)}` "
                f"({short_text(gate.action)}), no humana"
            )
            continue
        humanas.append(gate)
        if stage not in ctx.requests:
            fails.append(
                f"`{stage}`: decisión humana sin solicitud (falta `{stage}/review_request.yml`)"
            )
        elif gate.actor == _ACTOR_POR_DEFECTO:
            warns.append(
                f"`{stage}`: actor `{_ACTOR_POR_DEFECTO}` (declara `actor:` en decision.yml)"
            )

    propias, ajenas = _etiquetas_de_cribado(ctx)
    declared = _excluded_human(ctx)
    # Registros distintos: la tupla de una etiqueta es única en una decisión (spec §4.3).
    respaldadas = len(
        {(e.stage, e.target) for e in propias if _es_exclusion_humana(e) and e.target}
    )
    if declared is not None and declared > respaldadas:
        otras = sum(1 for e in ajenas if e.detail.get("to") == "exclude")
        fails.append(
            f"exclusions.json declara {short_text(declared)} exclusiones humanas "
            f"y el ledger solo registra {respaldadas} etiqueta(s) `exclude` de la decisión "
            "efectiva de cada gate de cribado"
            + (
                f" (además, {otras} etiqueta(s) `exclude` ajenas a esa decisión no cuentan)"
                if otras
                else ""
            )
        )

    if fails:
        return "FAIL", f"{_limitar(fails)}."
    if warns:
        return "WARN", f"{_limitar(warns)}."
    if not humanas:
        # Ni una etapa de juicio decidida (una corrida que se detuvo en el primer gate):
        # `final_gate` da el FAIL de la pausa.
        return "N/A", ctx.state.na_detail()
    actores = sorted({g.actor for g in humanas})
    return "PASS", (
        f"decisión humana en {len(humanas)} etapa(s) de juicio alcanzada(s) "
        f"({_listar(actores)}); {len(propias)} etiqueta(s) por registro."
    )


def check_final_gate(ctx: AuditContext) -> Verdict:
    """trAIce M8: el reporte final lo aprueba un humano, a través de su gate.

    Con D8, ``auto-approve`` y ``auto-proceed`` dejan de ser un WARN que no bloquea la
    publicación: son FAIL, igual que una corrida en pausa, interrumpida o rechazada y
    una aprobación humana sin ``reporte/review_request.yml`` (la decisión no pasó por
    el gate).
    """
    view = ctx.ledger
    if not view.entries:
        return "N/A", _NA_LEDGER
    if view.errors:
        # Tras una aprobación válida, una línea ilegible puede ser un `reject`: dar PASS
        # contradeciría el FAIL de `ledger` (revisión de la Tarea 5).
        return "FAIL", (
            f"{len(view.errors)} línea(s) ilegible(s) en decisions_ledger.jsonl: la decisión "
            "final no es verificable (ver `ledger`)."
        )
    reporte = [e for e in view.decisions if e.stage == "reporte"]
    if reporte and reporte[-1].action not in GATE_DECISION_ACTIONS | {"flag_review"}:
        last = reporte[-1]
        return "FAIL", (
            f"Acción desconocida `{short_text(last.action)}` en la decisión final "
            f"({short_text(last.actor)})."
        )

    state = ctx.state
    if state.status in ("paused", "interrupted"):
        return "FAIL", f"corrida {state.describe()}: sin decisión final."
    if state.status == "rejected":
        rejected = ctx.gates.get(state.pending_stage or "")
        actor = short_text(rejected.actor) if rejected is not None else "un actor desconocido"
        if state.pending_stage == "reporte":
            return "FAIL", f"El reporte final fue rechazado por {actor}."
        return "FAIL", f"corrida {state.describe()} por {actor}: sin decisión final."

    gate = ctx.gates.get("reporte")
    if gate is None:
        return "FAIL", "Sin decisión sobre el reporte final."
    if gate.action != "approve" or not gate.actor.startswith(HUMAN_ACTOR_PREFIX):
        return "FAIL", (
            f"El reporte final no lo aprobó un humano: {short_text(gate.actor)}/"
            f"{short_text(gate.action)} (D8: el gate final exige una decisión humana)."
        )
    if "reporte" not in ctx.requests:
        return "FAIL", (
            "aprobación humana sin solicitud: falta `reporte/review_request.yml` "
            "(la decisión no pasó por el gate)."
        )
    return "PASS", f"Reporte final aprobado por humano ({short_text(gate.actor)})."
