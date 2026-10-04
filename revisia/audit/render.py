"""Informe de auditoría en Markdown (``<run_dir>/audit.md``)."""

from __future__ import annotations

from revisia.audit.model import STATUS_ICON, AuditReport


def _md_cell(text: object) -> str:
    """Escapa una celda de tabla Markdown.

    Un ``|`` sin escapar o un salto de línea dentro del detalle (p. ej. un
    error de Pydantic o una ruta con ``|``) partirían la fila y cambiarían el
    número de columnas del informe (spec 2026-10-04 §9.1).
    """
    value = str(text).replace("|", "\\|")
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


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
    ]
    if report.state is not None:
        lines.append(f"- Estado deducido: {report.state.describe()}")
    lines += [
        f"- Resultado: {verdict}",
        f"- Verificaciones: {len(report.checks)} · FAIL={report.n_fail} · WARN={report.n_warn}"
        f" · N/A={report.n_na}",
        "",
        "| Verificación | Ítem de reporte | Estado | Evidencia |",
        "|---|---|---|---|",
    ]
    for check in report.checks:
        icon = STATUS_ICON.get(check.status, "•")
        lines.append(
            f"| {_md_cell(check.check_id)} | {_md_cell(check.item_ref)} | "
            f"{icon} {check.status} | {_md_cell(check.detail)} |"
        )
    lines += [
        "",
        "> El auditor es determinista: verifica artefactos en disco contra PRISMA 2020, "
        "PRISMA-S y PRISMA-trAIce. Un PASS no sustituye el juicio del revisor humano. "
        "➖ N/A = la etapa no se alcanzó o su raíz ya falló en otra fila; nunca aparece "
        "sin algún FAIL.",
    ]
    return "\n".join(lines)
