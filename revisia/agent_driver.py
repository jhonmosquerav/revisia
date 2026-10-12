"""Conducir revisia **en proceso** desde la sesión de un agente.

Entrypoint de conveniencia para el proveedor ``agent``: registra el callback de
razonamiento, crea la corrida y ejecuta el pipeline real (búsqueda, gates HITL,
verificador, exportadores y manifiesto), de modo que el agente que orquesta sirve
de motor LLM sin API key ni ``claude -p`` headless.

Úsalo cuando ya estás dentro de una sesión de agente (p. ej. Claude Code) y el
``protocol.yml`` declara ``provider: agent`` en sus etapas. Para corridas CLI
desatendidas usa ``revisia.orchestration.flow.run_review`` con un proveedor
de API (gemini/openai/anthropic/claude_code).
"""

from __future__ import annotations

from pathlib import Path

from revisia.config import load_protocol
from revisia.llm.providers.agent import AgentCallback, use_agent_callback
from revisia.orchestration.pipeline import (
    FetchFn,
    PipelineResult,
    SearchFn,
    run_pipeline,
)
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import SNAPSHOT_DIR


def run_review_with_agent(
    protocol_dir: str | Path | None,
    callback: AgentCallback,
    *,
    timestamp: str | None = None,
    runs_root: str | Path = "runs",
    max_results: int = 25,
    auto_approve: bool = True,
    mailto: str | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    run_dir: str | Path | None = None,
) -> PipelineResult:
    """Ejecuta el pipeline usando ``callback`` como motor de razonamiento.

    Args:
        protocol_dir: carpeta del protocolo (con ``protocol.yml``); puede ser
            ``None`` al reanudar con ``run_dir``.
        callback: función ``(LLMRequest, schema|None) -> objeto|dict|str`` que el
            proveedor ``agent`` invoca por etapa; el agente la implementa leyendo
            ``req.prompt`` y devolviendo algo que cumpla ``schema``.
        timestamp: marca de tiempo de una corrida nueva
            (``runs/<slug>-<timestamp>/``); obligatoria si no se pasa ``run_dir``.
        auto_approve: por defecto ``True`` (el agente conduce y aprueba los
            checkpoints); pon ``False`` para pausar en cada gate HITL.
        search_fn / fetch_fn: inyecciones opcionales (tests / corpus fijado).
        run_dir: carpeta de una corrida existente para reanudarla (Ola 1, D3):
            el protocolo sale de su ``00_protocol/`` y ``timestamp`` se ignora.

    Returns:
        El :class:`PipelineResult` de la corrida.
    """
    if run_dir is not None:
        ctx = RunContext.open(run_dir)
        protocol = load_protocol(ctx.run_dir / SNAPSHOT_DIR, default_slug=ctx.slug)
    else:
        if timestamp is None or protocol_dir is None:
            raise ValueError("una corrida nueva necesita protocol_dir y timestamp (o run_dir)")
        protocol = load_protocol(protocol_dir)
        ctx = RunContext(protocol.slug, runs_root, timestamp)
    with use_agent_callback(callback):
        return run_pipeline(
            protocol,
            protocol_dir,
            ctx,
            max_results=max_results,
            auto_approve=auto_approve,
            mailto=mailto,
            search_fn=search_fn,
            fetch_fn=fetch_fn,
        )
