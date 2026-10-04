"""Checks del flujo PRISMA: ``exclusions``, ``deliverable``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict

DELIVERABLE_FILES: tuple[str, ...] = (
    "documento.md",
    "prisma_flow.md",
    "metodologia.md",
    "tabla_extraccion.md",
    "risk_of_bias.md",
    "referencias.bib",
    "checklist_2020.md",
    "checklist_traice.md",
)


def check_exclusions(ctx: AuditContext) -> Verdict:
    """trAIce R1: exclusiones humano/IA separadas."""
    if ctx.art.exists("03_screening/exclusions.json"):
        return "PASS", "Desglose de exclusiones humano/IA presente (03_screening/exclusions.json)."
    return "WARN", "Sin desglose de exclusiones humano vs IA."


def check_deliverable(ctx: AuditContext) -> Verdict:
    """PRISMA 16/17/18/27: entregable completo."""
    missing = [name for name in DELIVERABLE_FILES if not ctx.art.exists(f"deliverable/{name}")]
    if not missing:
        return "PASS", f"Entregable completo ({len(DELIVERABLE_FILES)} artefactos)."
    return "FAIL", "Faltan artefactos del entregable: " + ", ".join(missing) + "."
