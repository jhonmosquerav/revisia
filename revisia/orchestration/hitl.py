"""Checkpoint humano (HITL) reproducible y SIN servidor.

En lugar de depender del pause server de Prefect (que exigiría infraestructura
y rompería el "clónalo y córrelo"), el gate es file-based:

  * Escribe ``<stage>/review_request.yml`` con lo que el humano debe revisar y su
    ``request_sha256`` (hash canónico del contenido), y a su lado
    ``decision.template.yml``, la decisión a medio rellenar.
  * Si existe ``<stage>/decision.yml`` con el ``request_sha256`` de la solicitud
    vigente (o ``--auto-approve``), aplica la decisión y la registra en el ledger
    (validado: ``approved`` booleano estricto; un fichero inválido detiene la
    corrida con un mensaje accionable). Una decisión que responde a otra
    solicitud pausa sin aplicar nada.
  * Si no, devuelve estado ``paused``: el orquestador se detiene e indica al
    humano cómo rellenar la decisión y reanudar.

El ledger manda (Ola 1, spec 2026-10-04 §4.3): registrar es idempotente al
reanudar y, sin ``decision.yml``, la decisión ya registrada para la solicitud
vigente se reutiliza (``decision.yml`` es solo el canal de entrada). Las
decisiones quedan en el ledger → reproducibilidad "a nivel decisión".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import AUTO_APPROVE_ACTOR, DecisionEntry, summarize_gates
from revisia.provenance.runmeta import canonical_sha256
from revisia.schemas.artifacts import ARTIFACT_SCHEMA_VERSION

GateStatus = Literal["approved", "paused", "rejected"]

REQUEST_FILE = "review_request.yml"
TEMPLATE_FILE = "decision.template.yml"
DECISION_FILE = "decision.yml"


@dataclass(slots=True)
class GateResult:
    """Resultado de un gate.

    Attributes:
        status: ``approved`` | ``paused`` | ``rejected``.
        message: texto para el humano (pausa: qué revisar y cómo reanudar).
        request_sha256: hash de la solicitud vigente.
        actor: quién decidió (``None`` en una pausa).
    """

    status: GateStatus
    message: str
    request_sha256: str | None = None
    actor: str | None = None


class DecisionFileError(ValueError):
    """``decision.yml`` ilegible o inválido: mensaje accionable, no traceback."""


class HumanDecision(BaseModel):
    """Contenido validado de ``<stage>/decision.yml`` (auditoría 2026-09-03, C1).

    ``request_sha256`` ata la decisión a la solicitud que el humano revisó
    (D4): si la solicitud cambia, una decisión vieja no se aplica.
    ``approved`` es un booleano YAML estricto: la cadena ``"false"`` ya no
    aprueba (``bool("false")`` es ``True``). Los campos extra se conservan y
    viajan al ``detail`` del ledger.
    """

    model_config = ConfigDict(extra="allow")

    request_sha256: str
    approved: StrictBool
    actor: str = "human:desconocido"
    reason: str | None = None


def render_decision_template(*, stage: str, autonomy: str, request_sha256: str) -> str:
    """``decision.template.yml``: la decisión a medio rellenar (D4).

    ``approved: null`` la hace inválida tal cual: aprobar tiene que ser un acto
    deliberado. Las cadenas van entre comillas dobles (JSON es YAML válido).
    """
    lines = [
        f"# Decisión humana del gate '{stage}' (autonomía {autonomy}).",
        "#",
        "# 1. Revisa review_request.yml, en esta misma carpeta.",
        "# 2. Copia este fichero como decision.yml y pon `approved: true` (aprobar)",
        "#    o `approved: false` (rechazar). Tal cual NO es válido: `approved: null`",
        "#    no aprueba ni rechaza.",
        "# 3. Pon tu nombre en `actor` (human:<nombre>) y, si quieres, una razón.",
        "# 4. Reanuda: revisia run --resume <carpeta de esta corrida>",
        "#",
        "# `request_sha256` ata la decisión a esta solicitud: si la solicitud cambia,",
        "# una decisión vieja no se aplica y la corrida vuelve a pausar.",
        f"request_sha256: {json.dumps(request_sha256)}",
        "approved: null",
        'actor: "human:desconocido"',
        "reason: null",
    ]
    return "\n".join(lines) + "\n"


def _recorded(
    entries: list[DecisionEntry],
    *,
    stage: str,
    action: str,
    target: str | None,
    request_sha256: str,
    decision_sha256: str | None,
) -> bool:
    """¿Ya está en el ledger la tupla ``(stage, action, target, request, decision)``?"""
    return any(
        (
            e.stage,
            e.action,
            e.target,
            e.detail.get("request_sha256"),
            e.detail.get("decision_sha256"),
        )
        == (stage, action, target, request_sha256, decision_sha256)
        for e in entries
    )


def _register(
    run_ctx: RunContext,
    entries: list[DecisionEntry],
    *,
    stage: str,
    autonomy: str,
    decision: HumanDecision,
    request_sha256: str,
) -> None:
    """Registra la decisión en el ledger, una sola vez (idempotente al reanudar)."""
    decision_sha256 = canonical_sha256(decision.model_dump(mode="json"))
    action = "approve" if decision.approved else "reject"
    effective = summarize_gates(entries).get(stage)
    if effective is not None and (
        effective.action,
        effective.request_sha256,
        effective.decision_sha256,
    ) == (action, request_sha256, decision_sha256):
        return  # ya es la decisión efectiva: reanudar no la duplica
    if _recorded(
        entries,
        stage=stage,
        action=action,
        target=None,
        request_sha256=request_sha256,
        decision_sha256=decision_sha256,
    ):
        raise DecisionFileError(
            f"{stage}: esta misma decisión ya se registró antes y después se cambió; para "
            "volver a ella, cambia `reason` en decision.yml (el ledger no repite una "
            "decisión idéntica)."
        )
    detail = {
        **decision.model_dump(exclude={"approved", "actor", "request_sha256"}, exclude_none=True),
        "request_sha256": request_sha256,
        "decision_sha256": decision_sha256,
        "n_labels": 0,
        "forced_human": False,
    }
    run_ctx.ledger.append(
        DecisionEntry(
            stage=stage, actor=decision.actor, autonomy=autonomy, action=action, detail=detail
        )
    )


def review_gate(
    *,
    stage: str,
    autonomy: str,
    run_ctx: RunContext,
    review_payload: dict,
    auto_approve: bool,
) -> GateResult:
    """Aplica el checkpoint humano de una etapa según su autonomía.

    La solicitud es ``{schema_version, stage, autonomy, **review_payload}`` y su
    ``request_sha256`` es ``canonical_sha256`` de ese contenido: sin rutas
    absolutas ni horas, para que sea estable entre reanudaciones (spec §4.3).

    A2/A3 no pausan (registran ``auto-proceed`` y continúan). A0/A1 requieren
    una decisión: ``decision.yml`` con el hash vigente, la ya registrada en el
    ledger para esa solicitud, o ``auto_approve``; si no hay ninguna, pausan.
    """
    payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "stage": stage,
        "autonomy": autonomy,
        **review_payload,
    }
    request_sha256 = canonical_sha256(payload)
    entries = run_ctx.ledger.read_all()

    if autonomy in {"A2", "A3"}:
        if not _recorded(
            entries,
            stage=stage,
            action="auto-proceed",
            target=None,
            request_sha256=request_sha256,
            decision_sha256=None,
        ):
            run_ctx.ledger.append(
                DecisionEntry(
                    stage=stage,
                    actor=f"agent:{stage}",
                    autonomy=autonomy,
                    action="auto-proceed",
                    detail={
                        "reason": f"autonomía {autonomy}: ejecuta y notifica",
                        "request_sha256": request_sha256,
                    },
                )
            )
        return GateResult(
            "approved", f"{stage}: auto-proceed ({autonomy}).", request_sha256, f"agent:{stage}"
        )

    # A0/A1 → requiere humano.
    stage_dir = run_ctx.stage_dir(stage)
    run_ctx.write_text(
        f"{stage}/{REQUEST_FILE}",
        yaml.safe_dump(
            {"request_sha256": request_sha256, **payload}, allow_unicode=True, sort_keys=False
        ),
    )
    run_ctx.write_text(
        f"{stage}/{TEMPLATE_FILE}",
        render_decision_template(stage=stage, autonomy=autonomy, request_sha256=request_sha256),
    )
    request_path = stage_dir / REQUEST_FILE
    decision_path = stage_dir / DECISION_FILE
    resume = f"Reanuda con: revisia run --resume {run_ctx.run_dir}"

    decision = _read_decision(decision_path)
    if decision is not None and decision.request_sha256 != request_sha256:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}': {decision_path} responde a otra solicitud "
                f"(request_sha256 {decision.request_sha256[:12]}…; la vigente es "
                f"{request_sha256[:12]}…). No se aplicó nada: revisa {request_path} y "
                f"rellena de nuevo la decisión desde {stage_dir / TEMPLATE_FILE}. {resume}"
            ),
            request_sha256,
        )
    if decision is None:
        effective = summarize_gates(entries).get(stage)
        if effective is not None and effective.request_sha256 == request_sha256:
            # El ledger manda: la decisión de esta solicitud ya está registrada.
            approved = effective.action != "reject"
            return GateResult(
                "approved" if approved else "rejected",
                f"{stage}: {'aprobado' if approved else 'rechazado'} por {effective.actor} "
                "(decisión registrada en el ledger).",
                request_sha256,
                effective.actor,
            )
        if auto_approve:
            decision = HumanDecision(
                request_sha256=request_sha256, approved=True, actor=AUTO_APPROVE_ACTOR
            )
    if decision is None:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}' ({autonomy}). Revisa {request_path}, rellena "
                f"{stage_dir / TEMPLATE_FILE} y guárdalo como {decision_path} (o vuelve a "
                f"correr con --auto-approve). {resume}"
            ),
            request_sha256,
        )

    _register(
        run_ctx,
        entries,
        stage=stage,
        autonomy=autonomy,
        decision=decision,
        request_sha256=request_sha256,
    )
    if decision.approved:
        return GateResult(
            "approved", f"{stage}: aprobado por {decision.actor}.", request_sha256, decision.actor
        )
    return GateResult(
        "rejected", f"{stage}: rechazado por {decision.actor}.", request_sha256, decision.actor
    )


_DECISION_HINT = (
    "Se espera un mapa YAML con `request_sha256` (el de review_request.yml; parte de "
    "decision.template.yml), `approved: true` o `approved: false` (booleano, sin "
    "comillas) y, opcionalmente, `actor: human:<nombre>` y `reason: <texto>`."
)


def _read_decision(path: Path) -> HumanDecision | None:
    """Lee y valida ``decision.yml``; ``None`` si no existe.

    Raises:
        DecisionFileError: si el fichero está vacío, no es YAML válido, su raíz
            no es un mapa, falta ``request_sha256`` o ``approved`` no es un
            booleano.
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
        raise DecisionFileError(f"{path}: decisión inválida ({detalle}). {_DECISION_HINT}") from exc
