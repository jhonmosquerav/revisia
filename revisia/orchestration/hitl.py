"""Checkpoint humano (HITL) reproducible y SIN servidor.

En lugar de depender del pause server de Prefect (que exigiría infraestructura
y rompería el "clónalo y córrelo"), el gate es file-based:

  * Escribe ``<stage>/review_request.yml`` con lo que el humano debe revisar.
  * Si existe ``<stage>/decision.yml`` con ``approved: true`` (o ``--auto-approve``),
    continúa y registra la decisión en el ledger.
  * Si no, devuelve estado ``paused``: el orquestador se detiene e indica al
    humano que edite el archivo de decisión y reanude.

Las decisiones quedan en el ledger → reproducibilidad "a nivel decisión".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import DecisionEntry

GateStatus = Literal["approved", "paused", "rejected"]


@dataclass(slots=True)
class GateResult:
    status: GateStatus
    message: str


def review_gate(
    *,
    stage: str,
    autonomy: str,
    run_ctx: RunContext,
    review_payload: dict,
    auto_approve: bool,
) -> GateResult:
    """Aplica el checkpoint humano de una etapa según su autonomía.

    A2/A3 no pausan (registran y continúan). A0/A1 requieren aprobación humana:
    si hay ``decision.yml`` aprobado o ``auto_approve``, continúan; si no, pausan.
    """
    stage_dir = run_ctx.stage_dir(stage)

    if autonomy in {"A2", "A3"}:
        run_ctx.ledger.append(
            DecisionEntry(
                stage=stage,
                actor=f"agent:{stage}",
                autonomy=autonomy,
                action="auto-proceed",
                detail={"reason": f"autonomía {autonomy}: ejecuta y notifica"},
            )
        )
        return GateResult("approved", f"{stage}: auto-proceed ({autonomy}).")

    # A0/A1 → requiere humano.
    request_path = stage_dir / "review_request.yml"
    request_path.write_text(
        yaml.safe_dump(review_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    decision = _read_decision(stage_dir / "decision.yml")
    if decision is None and auto_approve:
        decision = {"approved": True, "actor": "auto-approve (demo)"}

    if decision is None:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}' ({autonomy}). Revisa "
                f"{request_path} y crea {stage_dir / 'decision.yml'} con "
                f"`approved: true` (o vuelve a correr con --auto-approve)."
            ),
        )

    approved = bool(decision.get("approved"))
    actor = str(decision.get("actor", "human:desconocido"))
    run_ctx.ledger.append(
        DecisionEntry(
            stage=stage,
            actor=actor,
            autonomy=autonomy,
            action="approve" if approved else "reject",
            detail={k: v for k, v in decision.items() if k not in {"approved", "actor"}},
        )
    )
    if approved:
        return GateResult("approved", f"{stage}: aprobado por {actor}.")
    return GateResult("rejected", f"{stage}: rechazado por {actor}.")


def _read_decision(path: Path) -> dict | None:
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
