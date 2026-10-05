"""Auditoría post-corrida · transparencia metodológica verificable.

``run_audit`` inspecciona una carpeta ``runs/<slug>-<fecha>/`` y verifica, con
evidencia en disco, que la corrida puede defenderse ante los estándares de
reporte que el sistema promete:

- **PRISMA 2020** (selección documentada, flow diagram, registro, datos abiertos)
- **PRISMA-S** (ventana temporal de búsqueda declarada y ejecutada)
- **PRISMA-trAIce** (modelos y versiones, prompts hash-eados, supervisión
  humana, exclusiones IA/humano separadas, evaluación contra gold humano,
  procedencia de la corrida (pipeline vs reconstrucción), decisión humana
  sobre el reporte final)

Cada verificación produce ``PASS`` (evidencia presente y coherente), ``WARN``
(aceptable pero debe declararse/mejorarse antes de publicar), ``FAIL`` (la
corrida no es publicable tal cual) o ``N/A`` (la etapa no se alcanzó o la raíz
del check ya falló; nunca sin algún FAIL). El resultado se imprime y se
escribe en ``<run_dir>/audit.md``: el auditor es un agente determinista, lee
artefactos, no opina.

Estructura (spec 2026-10-04 §9.1): ``model`` (informe), ``artifacts`` (carga
que nunca lanza), ``state`` (estado de la corrida), ``checks_*`` (un módulo
por familia) y ``render`` (Markdown). Aquí vive el registro ordenado de checks
y ``_run_one``, que hace al auditor *fail-closed*: un check que revienta es un
FAIL, no un traceback ni un PASS.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from revisia.audit import (
    checks_flow,
    checks_hitl,
    checks_provenance,
    checks_quality,
    checks_search,
    checks_timing,
)
from revisia.audit.artifacts import AuditContext, load_run
from revisia.audit.model import AuditCheck, AuditReport, Verdict
from revisia.audit.render import render_audit_md

__all__ = ["AuditCheck", "AuditReport", "CheckSpec", "CHECKS", "render_audit_md", "run_audit"]


@dataclass(frozen=True)
class CheckSpec:
    """Un check registrado.

    Attributes:
        check_id: id estable de la fila del informe.
        item_ref: ítem PRISMA / trAIce que respalda la verificación.
        stage: etapa de ``config.STAGES`` a partir de la cual el check aplica;
            si la corrida no la alcanzó, la fila sale ``N/A``. ``None`` =
            siempre aplica (los checks "por etapa" miran el estado ellos mismos).
        fn: la verificación; devuelve ``(estado, evidencia)``.
    """

    check_id: str
    item_ref: str
    stage: str | None
    fn: Callable[[AuditContext], Verdict]


# Orden del informe (spec §9.3). Una fila por check, siempre.
CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec("manifest", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_manifest),
    CheckSpec("provenance", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_provenance),
    CheckSpec("schemas", "PRISMA 27 / trAIce M5", None, checks_provenance.check_schemas),
    CheckSpec("prompts", "trAIce M6", "reporte", checks_provenance.check_prompts),
    CheckSpec("timing", "PRISMA 27 / trAIce M2", None, checks_timing.check_timing),
    CheckSpec("ledger", "trAIce M8 / PRISMA 8", None, checks_hitl.check_ledger),
    CheckSpec("hitl", "trAIce M8/R1 / PRISMA 8", None, checks_hitl.check_hitl),
    CheckSpec("final_gate", "trAIce M8", None, checks_hitl.check_final_gate),
    CheckSpec("stage_artifacts", "PRISMA 16/27", None, checks_flow.check_stage_artifacts),
    CheckSpec("arithmetic", "PRISMA 16 / trAIce R1", "reporte", checks_flow.check_arithmetic),
    CheckSpec("exclusions", "trAIce R1", "screening_ft", checks_flow.check_exclusions),
    CheckSpec("deliverable", "PRISMA 16/16b/17/18/27", "reporte", checks_flow.check_deliverable),
    CheckSpec("gold", "trAIce M9/R2", "screening_ta", checks_quality.check_gold),
    CheckSpec(
        "thresholds",
        "trAIce M9/R2 / PRISMA 8, 24c",
        "screening_ta",
        checks_quality.check_thresholds,
    ),
    CheckSpec("grounding", "trAIce M8/M9", "sintesis", checks_quality.check_grounding),
    CheckSpec("search_window", "PRISMA-S 9/13", "busqueda", checks_search.check_search_window),
    CheckSpec("registration", "PRISMA 24a", None, checks_search.check_registration),
    CheckSpec("response_overlap", "trAIce M2", "reporte", checks_timing.check_response_overlap),
)


def _run_one(spec: CheckSpec, ctx: AuditContext) -> AuditCheck:
    """Ejecuta un check: ``N/A`` si su etapa no se alcanzó; FAIL si revienta."""
    if spec.stage is not None and spec.stage not in ctx.state.reached:
        return AuditCheck(spec.check_id, spec.item_ref, "N/A", ctx.state.na_detail())
    try:
        status, detail = spec.fn(ctx)
    except Exception as exc:  # fail-closed: un check roto no verifica nada
        return AuditCheck(
            spec.check_id,
            spec.item_ref,
            "FAIL",
            f"error interno del auditor ({type(exc).__name__}): {exc} — la corrida no se "
            "considera verificada.",
        )
    return AuditCheck(spec.check_id, spec.item_ref, status, detail)


def _enforce_invariant(checks: list[AuditCheck]) -> list[AuditCheck]:
    """Invariante ``N/A ⇒ FAIL``: si un N/A apareciera sin ningún FAIL (un defecto
    del auditor), se convierte en FAIL; un N/A nunca puede dejar publicable una
    corrida que no se verificó entera (spec §9.2)."""
    if any(c.status == "FAIL" for c in checks) or all(c.status != "N/A" for c in checks):
        return checks
    result: list[AuditCheck] = []
    for check in checks:
        if check.status == "N/A":
            check = AuditCheck(
                check.check_id,
                check.item_ref,
                "FAIL",
                f"error interno del auditor: N/A sin ningún FAIL que lo justifique "
                f"({check.detail}) — la corrida no se considera verificada.",
            )
        result.append(check)
    return result


def run_audit(run_dir: str | Path) -> AuditReport:
    """Audita una corrida y devuelve el informe (una fila por check registrado)."""
    run = Path(run_dir)
    ctx = AuditContext(load_run(run))
    checks = _enforce_invariant([_run_one(spec, ctx) for spec in CHECKS])
    return AuditReport(run_dir=run, checks=checks, state=ctx.state)
