"""Helpers de test del HITL por fichero (Ola 1, spec 2026-10-04 §7).

Los usan los tests de reanudación (PR-C), de HITL por registro (PR-D) y del
auditor (PR-E). Hacen lo que haría un humano: leer la solicitud vigente y
escribir ``decision.yml`` con su ``request_sha256``; ``correr_hasta`` encadena
"correr → pausa → decidir → reanudar" hasta que la corrida termina.

Uso (``tests/`` está en ``sys.path``)::

    from hitl_helpers import correr_hasta, responder_gate
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml

from revisia.config import ReviewProtocol
from revisia.orchestration.pipeline import FetchFn, PipelineResult, SearchFn, run_pipeline
from revisia.orchestration.run_context import RunContext


def leer_solicitud(run_dir: Path, stage: str) -> dict:
    """``<run_dir>/<stage>/review_request.yml`` como mapa."""
    path = Path(run_dir) / stage / "review_request.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def responder_gate(
    run_dir: Path,
    stage: str,
    *,
    approved: bool = True,
    actor: str = "human:revisora",
    reason: str | None = None,
    records: dict[str, dict] | None = None,
    flags: dict[str, dict] | None = None,
) -> Path:
    """Escribe ``decision.yml`` para la solicitud vigente de ``stage``.

    Toma el ``request_sha256`` de ``review_request.yml``. ``records`` va tal
    cual (``{id: {label, reason}}``, cribado por registro) y ``flags`` también
    (``{índice: {verdict, reason}}``, citas marcadas del reporte; PR-D).
    """
    decision: dict = {
        "request_sha256": leer_solicitud(run_dir, stage)["request_sha256"],
        "approved": approved,
        "actor": actor,
    }
    if reason is not None:
        decision["reason"] = reason
    if records is not None:
        decision["records"] = records
    if flags is not None:
        decision["flags"] = flags
    path = Path(run_dir) / stage / "decision.yml"
    path.write_text(yaml.safe_dump(decision, allow_unicode=True, sort_keys=False), "utf-8")
    return path


def aceptar_lo_obligatorio(stage: str, solicitud: dict) -> dict | None:
    """Etiqueta lo obligatorio de un gate de cribado con la propuesta de la IA.

    Responde como una revisora que revisa cada registro de ``must_label`` y
    ``must_resolve`` y coincide con la IA; un ``unclear`` (o un registro sin
    propuesta) lo incluye. Sin nada obligatorio, ``None`` (aprobar sin más).
    """
    obligatorios = sorted(
        set(solicitud.get("must_label", [])) | set(solicitud.get("must_resolve", []))
    )
    if not obligatorios:
        return None
    propuestas = {r["record_id"]: r.get("proposal") for r in solicitud.get("records", [])}
    return {
        "records": {
            rid: {
                "label": p if (p := propuestas.get(rid)) in ("include", "exclude") else "include",
                "reason": "revisado: de acuerdo con la propuesta",
            }
            for rid in obligatorios
        }
    }


def correr_hasta(
    protocol: ReviewProtocol,
    protocol_dir: Path,
    ctx: RunContext,
    *,
    search_fn: SearchFn,
    fetch_fn: FetchFn | None = None,
    etiquetar: Callable[[str, dict], dict | None] | None = None,
    parar_en: str | None = None,
    max_vueltas: int = 10,
) -> PipelineResult:
    """Corre el pipeline y responde a cada pausa como un humano, hasta terminar.

    En cada pausa (salvo en ``parar_en``, donde devuelve el resultado) escribe
    ``decision.yml`` con ``responder_gate``. ``etiquetar(stage, solicitud)``
    devuelve los argumentos extra de ``responder_gate`` para ese gate
    (``{"records": …}``, ``{"approved": False, "reason": …}``…) o ``None``; con
    ``None`` (o sin ``etiquetar``) se responde con ``aceptar_lo_obligatorio``,
    que etiqueta lo que el gate exige y, si no exige nada, aprueba sin más. La
    primera vuelta usa ``ctx``; las siguientes reabren la carpeta con
    ``RunContext.open``, como ``revisia run --resume``.

    Raises:
        AssertionError: si la corrida no termina en ``max_vueltas``.
    """
    contexto = ctx
    for _ in range(max_vueltas):
        result = run_pipeline(
            protocol, protocol_dir, contexto, search_fn=search_fn, fetch_fn=fetch_fn
        )
        if result.status != "paused" or result.stage == parar_en:
            return result
        solicitud = leer_solicitud(ctx.run_dir, result.stage)
        extra = etiquetar(result.stage, solicitud) if etiquetar else None
        if extra is None:
            extra = aceptar_lo_obligatorio(result.stage, solicitud)
        responder_gate(ctx.run_dir, result.stage, **(extra or {}))
        contexto = RunContext.open(ctx.run_dir)
    raise AssertionError(f"la corrida no terminó en {max_vueltas} vueltas")
