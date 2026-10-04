"""Checks del ledger y de la supervisión humana: ``ledger``, ``hitl``, ``final_gate``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.config import JUDGMENT_STAGES

_NA_LEDGER = "no aplica: sin ledger legible (ver `ledger`)."


def check_ledger(ctx: AuditContext) -> Verdict:
    """trAIce M8: el ledger de decisiones existe y tiene entradas."""
    if not ctx.ledger.entries:
        return "FAIL", "decisions_ledger.jsonl ausente o vacío: sin trazabilidad de decisiones."
    return "PASS", f"{len(ctx.ledger.entries)} decisiones en el ledger."


def check_hitl(ctx: AuditContext) -> Verdict:
    """trAIce M8: decisiones humanas en las etapas de juicio."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    ledger = ctx.ledger.decisions
    human = [e for e in ledger if e.actor.startswith("human")]
    judgment = [e for e in ledger if e.stage in JUDGMENT_STAGES]
    judgment_human = [e for e in judgment if e.actor.startswith("human")]
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
    if last.action == "approve" and last.actor.startswith("human"):
        return "PASS", f"Reporte final aprobado por humano ({last.actor})."
    if last.action in ("approve", "auto-proceed"):
        return "WARN", f"El reporte final no lo aprobó un humano: {last.actor}/{last.action}."
    if last.action == "reject":
        return "FAIL", f"El reporte final fue rechazado por {last.actor}."
    return "FAIL", f"Acción desconocida {last.action} en la decisión final."
