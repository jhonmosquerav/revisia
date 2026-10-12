"""Entrypoints de ejecución del pipeline.

``run_review`` es el entrypoint plano (sin Prefect): lo usan el CLI y los tests,
y corre con dependencias mínimas — clave para "clónalo y córrelo". ``prefect_review_flow``
lo envuelve en un ``@flow`` de Prefect para corridas observables/programables
(import perezoso: Prefect solo se exige si se usa este wrapper). ``resume_review``
reanuda una corrida existente desde su carpeta (Ola 1, D3).
"""

from __future__ import annotations

from pathlib import Path

from revisia.config import load_protocol
from revisia.orchestration.pipeline import PipelineResult, run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import SNAPSHOT_DIR


def run_review(
    protocol_dir: str | Path,
    *,
    timestamp: str,
    runs_root: str | Path = "runs",
    max_results: int = 25,
    auto_approve: bool = False,
    mailto: str | None = None,
) -> PipelineResult:
    """Carga el protocolo, crea la corrida y ejecuta el pipeline (sin Prefect)."""
    protocol = load_protocol(protocol_dir)
    ctx = RunContext(protocol.slug, runs_root, timestamp)
    return run_pipeline(
        protocol,
        protocol_dir,
        ctx,
        max_results=max_results,
        auto_approve=auto_approve,
        mailto=mailto,
    )


def resume_review(
    run_dir: str | Path,
    *,
    protocol_dir: str | Path | None = None,
    auto_approve: bool = False,
    mailto: str | None = None,
) -> PipelineResult:
    """Reanuda una corrida desde su carpeta (D3, D14).

    El protocolo sale de ``00_protocol/`` con el slug de ``run.json`` (un demo
    sin ``slug`` declarado no pasa a llamarse ``00_protocol``) y ``max_results``
    también de ``run.json``. Si se pasa ``protocol_dir``, su huella se compara
    con la de la corrida.

    Raises:
        LegacyRunError: la carpeta no tiene ``run.json`` (corrida anterior a la
            Ola 1, D13).
    """
    ctx = RunContext.open(run_dir)
    protocol = load_protocol(ctx.run_dir / SNAPSHOT_DIR, default_slug=ctx.slug)
    return run_pipeline(protocol, protocol_dir, ctx, auto_approve=auto_approve, mailto=mailto)


def prefect_review_flow(
    protocol_dir: str | Path,
    *,
    timestamp: str,
    runs_root: str | Path = "runs",
    max_results: int = 25,
    auto_approve: bool = False,
    mailto: str | None = None,
) -> PipelineResult:
    """Wrapper Prefect del pipeline (observabilidad/scheduling). Requiere ``prefect``."""
    from prefect import flow, get_run_logger

    @flow(name="revisia-review", log_prints=True)
    def _flow() -> PipelineResult:
        logger = get_run_logger()
        logger.info("Iniciando revisión: %s", protocol_dir)
        result = run_review(
            protocol_dir,
            timestamp=timestamp,
            runs_root=runs_root,
            max_results=max_results,
            auto_approve=auto_approve,
            mailto=mailto,
        )
        logger.info("Estado: %s · %s", result.status, result.message)
        return result

    return _flow()
