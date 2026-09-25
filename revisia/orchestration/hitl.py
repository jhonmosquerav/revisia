"""Checkpoint humano (HITL) reproducible y SIN servidor.

En lugar de depender del pause server de Prefect (que exigiría infraestructura
y rompería el "clónalo y córrelo"), el gate es file-based:

  * Escribe ``<stage>/review_request.yml`` con lo que el humano debe revisar.
  * Si existe ``<stage>/decision.yml`` con ``approved: true`` (o ``--auto-approve``),
    continúa y registra la decisión en el ledger (validado: `approved` booleano
    estricto; un fichero inválido detiene la corrida con un mensaje accionable).
  * Si no, devuelve estado ``paused``: el orquestador se detiene e indica al
    humano que edite el archivo de decisión y reanude.

Las decisiones quedan en el ledger → reproducibilidad "a nivel decisión".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import DecisionEntry

GateStatus = Literal["approved", "paused", "rejected"]


@dataclass(slots=True)
class GateResult:
    status: GateStatus
    message: str


class DecisionFileError(ValueError):
    """``decision.yml`` ilegible o inválido: mensaje accionable, no traceback."""


class HumanDecision(BaseModel):
    """Contenido validado de ``<stage>/decision.yml`` (auditoría 2026-09-03, C1).

    ``approved`` es un booleano YAML estricto: la cadena ``"false"`` ya no
    aprueba (``bool("false")`` es ``True``). Los campos extra se conservan y
    viajan al ``detail`` del ledger.
    """

    model_config = ConfigDict(extra="allow")

    approved: StrictBool
    actor: str = "human:desconocido"
    reason: str | None = None


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
        decision = HumanDecision(approved=True, actor="auto-approve (demo)")

    if decision is None:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}' ({autonomy}). Revisa "
                f"{request_path} y crea {stage_dir / 'decision.yml'} con "
                f"`approved: true` (o vuelve a correr con --auto-approve)."
            ),
        )

    run_ctx.ledger.append(
        DecisionEntry(
            stage=stage,
            actor=decision.actor,
            autonomy=autonomy,
            action="approve" if decision.approved else "reject",
            detail=decision.model_dump(exclude={"approved", "actor"}, exclude_none=True),
        )
    )
    if decision.approved:
        return GateResult("approved", f"{stage}: aprobado por {decision.actor}.")
    return GateResult("rejected", f"{stage}: rechazado por {decision.actor}.")


_DECISION_HINT = (
    "Se espera un mapa YAML con `approved: true` o `approved: false` (booleano, sin "
    "comillas) y, opcionalmente, `actor: human:<nombre>` y `reason: <texto>`."
)


def _read_decision(path: Path) -> HumanDecision | None:
    """Lee y valida ``decision.yml``; ``None`` si no existe.

    Raises:
        DecisionFileError: si el fichero está vacío, no es YAML válido, su raíz
            no es un mapa o ``approved`` no es un booleano.
    """
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DecisionFileError(f"{path}: YAML inválido ({exc}). {_DECISION_HINT}") from exc
    if raw is None:
        raise DecisionFileError(f"{path}: está vacío. {_DECISION_HINT}")
    if not isinstance(raw, dict):
        raise DecisionFileError(
            f"{path}: la raíz es {type(raw).__name__}, no un mapa. {_DECISION_HINT}"
        )
    try:
        return HumanDecision.model_validate(raw)
    except ValidationError as exc:
        detalle = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise DecisionFileError(
            f"{path}: decisión inválida ({detalle}). `approved` debe ser un booleano "
            f"YAML. {_DECISION_HINT}"
        ) from exc
