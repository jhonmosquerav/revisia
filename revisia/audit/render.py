"""Informe de auditoría en Markdown (``<run_dir>/audit.md``)."""

from __future__ import annotations

from revisia.audit.model import AuditReport

_STATUS_ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}


def render_audit_md(report: AuditReport) -> str:
    """Renderiza el informe de auditoría como Markdown."""
    verdict = (
        "**APTA para preparar publicación** (sin FAIL; resuelve los WARN y decláralos)."
        if report.publishable
        else "**NO publicable tal cual** (hay verificaciones FAIL)."
    )
    lines = [
        "# Auditoría de corrida · revisia",
        "",
        f"- Corrida: `{report.run_dir}`",
        f"- Resultado: {verdict}",
        f"- Verificaciones: {len(report.checks)} · FAIL={report.n_fail} · WARN={report.n_warn}",
        "",
        "| Verificación | Ítem de reporte | Estado | Evidencia |",
        "|---|---|---|---|",
    ]
    for check in report.checks:
        icon = _STATUS_ICON.get(check.status, "•")
        lines.append(
            f"| {check.check_id} | {check.item_ref} | {icon} {check.status} | {check.detail} |"
        )
    lines += [
        "",
        "> El auditor es determinista: verifica artefactos en disco contra PRISMA 2020, "
        "PRISMA-S y PRISMA-trAIce. Un PASS no sustituye el juicio del revisor humano.",
    ]
    return "\n".join(lines)
