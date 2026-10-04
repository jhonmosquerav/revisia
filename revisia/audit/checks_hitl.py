"""Checks del ledger y de la supervisión humana: ``ledger``, ``hitl``, ``final_gate``.

El ledger es entrada no confiable como el manifiesto: los textos que trae (etapa,
acción, actor…) se acotan con ``short_text`` antes de entrar en un detalle.
"""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext, short_text
from revisia.audit.model import Verdict
from revisia.config import JUDGMENT_STAGES, STAGES
from revisia.provenance.ledger import GATE_DECISION_ACTIONS, HUMAN_ACTOR_PREFIX, LEDGER_ACTIONS
from revisia.schemas.artifacts import GATED_STAGES

_NA_LEDGER = "no aplica: sin ledger legible (ver `ledger`)."
_MAX_PROBLEMAS = 5
_LIMITE_PROBLEMA = 300  # caracteres por problema mostrado


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
                    f"`{entry.stage}`, la efectiva es {expected}"
                )

    if problems:
        return "FAIL", f"{len(problems)} problema(s) en el ledger: {_limitar(problems)}."
    note = "" if autonomy is not None else " (autonomía no verificable: sin protocolo legible)"
    return "PASS", f"{len(view.entries)} entradas válidas, en orden{note}."


def check_hitl(ctx: AuditContext) -> Verdict:
    """trAIce M8: decisiones humanas en las etapas de juicio."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    ledger = ctx.ledger.decisions
    human = [e for e in ledger if e.actor.startswith(HUMAN_ACTOR_PREFIX)]
    judgment = [e for e in ledger if e.stage in JUDGMENT_STAGES]
    judgment_human = [e for e in judgment if e.actor.startswith(HUMAN_ACTOR_PREFIX)]
    if judgment and not judgment_human:
        return "WARN", (
            f"{len(ledger)} decisiones registradas, pero NINGUNA humana en etapas de "
            "juicio (¿--auto-approve?). Apta para demo; NO publicable sin revisión humana."
        )
    return "PASS", f"{len(ledger)} decisiones en el ledger; {len(human)} humana(s)."


def check_final_gate(ctx: AuditContext) -> Verdict:
    """Gate de honestidad: decisión humana sobre el reporte final."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    reporte = [e for e in ctx.ledger.decisions if e.stage == "reporte"]
    if not reporte:
        return "FAIL", "Sin decisión sobre el reporte final: la corrida está pausada o incompleta."
    last = reporte[-1]
    actor, action = short_text(last.actor), short_text(last.action)
    if last.action == "approve" and last.actor.startswith(HUMAN_ACTOR_PREFIX):
        return "PASS", f"Reporte final aprobado por humano ({actor})."
    if last.action in ("approve", "auto-proceed"):
        return "WARN", f"El reporte final no lo aprobó un humano: {actor}/{action}."
    if last.action == "reject":
        return "FAIL", f"El reporte final fue rechazado por {actor}."
    return "FAIL", f"Acción desconocida {action} en la decisión final."
