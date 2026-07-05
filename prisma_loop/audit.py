"""Auditoría post-corrida · transparencia metodológica verificable.

``run_audit`` inspecciona una carpeta ``runs/<slug>-<fecha>/`` terminada y
verifica, con evidencia en disco, que la corrida puede defenderse ante los
estándares de reporte que el sistema promete:

- **PRISMA 2020** (selección documentada, flow diagram, registro, datos abiertos)
- **PRISMA-S** (ventana temporal de búsqueda declarada y ejecutada)
- **PRISMA-trAIce** (modelos y versiones, prompts hash-eados, supervisión
  humana, exclusiones IA/humano separadas, evaluación contra gold humano)

Cada verificación produce ``PASS`` (evidencia presente), ``WARN`` (aceptable
pero debe declararse/mejorarse antes de publicar) o ``FAIL`` (la corrida no es
publicable tal cual). El resultado se imprime y se escribe en
``<run_dir>/audit.md`` — el auditor es un agente determinista: lee artefactos,
no opina.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

_STATUS_ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}

# Etapas cuyo juicio exige supervisión humana (Cochrane/JBI 2025).
_JUDGMENT_STAGES = ("screening_ta", "screening_ft", "extraccion", "rob")


@dataclass(frozen=True)
class AuditCheck:
    """Resultado de una verificación puntual de la auditoría."""

    check_id: str
    item_ref: str  # ítem PRISMA / trAIce que respalda la verificación
    status: str  # PASS | WARN | FAIL
    detail: str


@dataclass(frozen=True)
class AuditReport:
    """Informe completo de auditoría de una corrida."""

    run_dir: Path
    checks: list[AuditCheck]

    @property
    def n_fail(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def publishable(self) -> bool:
        return self.n_fail == 0


def _load_manifest(run_dir: Path) -> dict | None:
    path = run_dir / "manifest.yml"
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None


def _read_ledger(run_dir: Path) -> list[dict]:
    path = run_dir / "decisions_ledger.jsonl"
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def run_audit(run_dir: str | Path) -> AuditReport:
    """Audita una corrida terminada y devuelve el informe de verificaciones."""
    run = Path(run_dir)
    checks: list[AuditCheck] = []
    add = checks.append

    # ── 1 · Manifiesto reproducible (trAIce M2: herramienta, modelo, versión) ──
    manifest = _load_manifest(run)
    if manifest is None:
        add(
            AuditCheck(
                "manifest",
                "PRISMA 27 / trAIce M2",
                "FAIL",
                "manifest.yml ausente o ilegible: la corrida no es reproducible.",
            )
        )
    else:
        models = manifest.get("models_used") or []
        calls = manifest.get("llm_calls") or []
        if models and calls:
            add(
                AuditCheck(
                    "manifest",
                    "PRISMA 27 / trAIce M2",
                    "PASS",
                    f"manifest.yml con {len(calls)} llamada(s) IA y modelos: {', '.join(models)}.",
                )
            )
        elif calls or models:
            add(
                AuditCheck(
                    "manifest",
                    "PRISMA 27 / trAIce M2",
                    "WARN",
                    "manifest.yml presente pero con procedencia IA incompleta.",
                )
            )
        else:
            add(
                AuditCheck(
                    "manifest",
                    "PRISMA 27 / trAIce M2",
                    "WARN",
                    "manifest.yml sin llamadas IA registradas (¿corrida determinista/fake?).",
                )
            )

    # ── 2 · Prompts hash-eados por llamada (trAIce M6) ──────────────────────
    if manifest is not None:
        calls = manifest.get("llm_calls") or []
        hashed = [c for c in calls if c.get("prompt_hash")]
        if calls and len(hashed) == len(calls):
            add(
                AuditCheck(
                    "prompts",
                    "trAIce M6",
                    "PASS",
                    f"{len(hashed)}/{len(calls)} llamadas con prompt hash-eado (RunMeta).",
                )
            )
        elif calls:
            add(
                AuditCheck(
                    "prompts",
                    "trAIce M6",
                    "WARN",
                    f"Solo {len(hashed)}/{len(calls)} llamadas llevan prompt_hash.",
                )
            )
        else:
            add(AuditCheck("prompts", "trAIce M6", "WARN", "Sin llamadas IA que auditar."))

    # ── 3 · Ledger de decisiones + supervisión humana (trAIce M8) ───────────
    ledger = _read_ledger(run)
    if not ledger:
        add(
            AuditCheck(
                "ledger",
                "trAIce M8 / PRISMA 8",
                "FAIL",
                "decisions_ledger.jsonl ausente o vacío: sin trazabilidad de decisiones.",
            )
        )
    else:
        human = [e for e in ledger if str(e.get("actor", "")).startswith("human")]
        judgment = [e for e in ledger if e.get("stage") in _JUDGMENT_STAGES]
        judgment_human = [e for e in judgment if str(e.get("actor", "")).startswith("human")]
        if judgment and not judgment_human:
            add(
                AuditCheck(
                    "hitl",
                    "trAIce M8",
                    "WARN",
                    f"{len(ledger)} decisiones registradas, pero NINGUNA humana en etapas de "
                    "juicio (¿--auto-approve?). Apta para demo; NO publicable sin revisión humana.",
                )
            )
        else:
            add(
                AuditCheck(
                    "hitl",
                    "trAIce M8",
                    "PASS",
                    f"{len(ledger)} decisiones en el ledger; {len(human)} humana(s).",
                )
            )

    # ── 4 · Entregables PRISMA completos ────────────────────────────────────
    deliverable = run / "deliverable"
    expected = [
        "documento.md",
        "prisma_flow.md",
        "metodologia.md",
        "tabla_extraccion.md",
        "risk_of_bias.md",
        "referencias.bib",
        "checklist_2020.md",
        "checklist_traice.md",
    ]
    missing = [name for name in expected if not (deliverable / name).exists()]
    if not missing:
        add(
            AuditCheck(
                "deliverable",
                "PRISMA 16/17/18/27",
                "PASS",
                f"Entregable completo ({len(expected)} artefactos).",
            )
        )
    else:
        add(
            AuditCheck(
                "deliverable",
                "PRISMA 16/17/18/27",
                "FAIL",
                "Faltan artefactos del entregable: " + ", ".join(missing) + ".",
            )
        )

    # ── 5 · Exclusiones IA vs humano separadas (trAIce R1) ──────────────────
    if (run / "03_screening" / "exclusions.json").exists():
        add(
            AuditCheck(
                "exclusions",
                "trAIce R1",
                "PASS",
                "Desglose de exclusiones humano/IA presente (03_screening/exclusions.json).",
            )
        )
    else:
        add(
            AuditCheck(
                "exclusions",
                "trAIce R1",
                "WARN",
                "Sin desglose de exclusiones humano vs IA.",
            )
        )

    # ── 6 · Evaluación contra gold humano (trAIce M9/R2) ────────────────────
    metrics_path = run / "03_screening" / "metrics.json"
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            recall = metrics.get("recall")
            kappa = metrics.get("cohen_kappa")
            add(
                AuditCheck(
                    "gold",
                    "trAIce M9/R2",
                    "PASS",
                    f"Métricas vs gold humano: recall={recall} · kappa={kappa} "
                    "(accuracy omitida a propósito).",
                )
            )
        except json.JSONDecodeError:
            add(AuditCheck("gold", "trAIce M9/R2", "WARN", "metrics.json ilegible."))
    else:
        add(
            AuditCheck(
                "gold",
                "trAIce M9/R2",
                "WARN",
                "Sin gold standard: no hay recall/kappa del cribado IA vs humano. "
                "Crea gold.yml (prisma-loop gold-template) antes de publicar.",
            )
        )

    # ── 7 · Verificación anti-alucinación (grounding) ───────────────────────
    verification_path = run / "06_synthesis" / "verification.json"
    if verification_path.exists():
        try:
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            flagged = verification.get("hallucination_flagged")
            status = "WARN" if flagged else "PASS"
            detail = (
                "El verificador marcó citas posiblemente no fundamentadas: revisar antes de usar."
                if flagged
                else "Grounding de citas verificado sin banderas."
            )
            add(AuditCheck("grounding", "trAIce M8/M9", status, detail))
        except json.JSONDecodeError:
            add(AuditCheck("grounding", "trAIce M8/M9", "WARN", "verification.json ilegible."))
    else:
        add(
            AuditCheck(
                "grounding",
                "trAIce M8/M9",
                "WARN",
                "Sin verification.json: la síntesis no pasó por el verificador.",
            )
        )

    # ── 8 · Ventana temporal de búsqueda (PRISMA-S §3) ──────────────────────
    if manifest is not None:
        window = (manifest.get("protocol") or {}).get("search_window") or {}
        if window.get("executed"):
            add(
                AuditCheck(
                    "search_window",
                    "PRISMA-S 3 / trAIce M3",
                    "PASS",
                    f"Búsqueda ejecutada declarada: {window.get('executed')}.",
                )
            )
        else:
            add(
                AuditCheck(
                    "search_window",
                    "PRISMA-S 3 / trAIce M3",
                    "WARN",
                    "search_window.executed vacío: declara cuándo se ejecutó la búsqueda.",
                )
            )

    # ── 9 · Registro del protocolo (PRISMA 24a) ─────────────────────────────
    if manifest is not None:
        registration = (manifest.get("protocol") or {}).get("registration") or {}
        if any(v for v in registration.values()):
            add(
                AuditCheck(
                    "registration",
                    "PRISMA 24a",
                    "PASS",
                    "Registro declarado: "
                    + ", ".join(f"{k}={v}" for k, v in registration.items() if v)
                    + ".",
                )
            )
        else:
            add(
                AuditCheck(
                    "registration",
                    "PRISMA 24a",
                    "WARN",
                    "Sin registro (PROSPERO/OSF): preregistra el protocolo antes de publicar.",
                )
            )

    return AuditReport(run_dir=run, checks=checks)


def render_audit_md(report: AuditReport) -> str:
    """Renderiza el informe de auditoría como Markdown."""
    verdict = (
        "**APTA para preparar publicación** (sin FAIL; resuelve los WARN y decláralos)."
        if report.publishable
        else "**NO publicable tal cual** (hay verificaciones FAIL)."
    )
    lines = [
        "# Auditoría de corrida · prisma-loop",
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
