"""Agente de cribado a texto completo (🤖 razonamiento · §5 fase 2).

Evalúa los registros que pasaron título/abstract contra TODOS los criterios,
usando el texto completo cuando está disponible (ver :mod:`prisma_loop.agents.fulltext`).
Etapa no resuelta sin humano según el estado del arte → autonomía A0.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from prisma_loop.llm.base import LLMProvider, LLMRequest
from prisma_loop.prompts import load_prompt
from prisma_loop.provenance.runmeta import RunMeta
from prisma_loop.schemas.records import SearchRecord
from prisma_loop.schemas.screening import ScreeningDecision, ScreeningLabel, ScreeningVote

_SYSTEM = "Eres un asistente metodológico riguroso para revisiones sistemáticas PRISMA."


class _FullTextOut(BaseModel):
    label: ScreeningLabel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    criteria_violated: list[str] = Field(default_factory=list)


def screen_fulltext(
    provider: LLMProvider,
    model_name: str,
    *,
    question: str,
    criteria: str,
    record: SearchRecord,
    text: str,
    temperature: float = 0.0,
    seed: int | None = None,
) -> tuple[ScreeningDecision, RunMeta]:
    """Criba un estudio a texto completo y devuelve la decisión + procedencia."""
    prompt = load_prompt("screening_ft").format(
        question=question,
        criteria=criteria,
        title=record.title,
        text=text or "(texto completo no disponible; se usó el abstract)",
    )
    req = LLMRequest(prompt=prompt, system=_SYSTEM, temperature=temperature, seed=seed)
    out, meta = provider.structured(req, _FullTextOut)
    vote = ScreeningVote(
        model=model_name,
        label=out.label,
        confidence=out.confidence,
        rationale=out.rationale,
        criteria_violated=out.criteria_violated,
    )
    decision = ScreeningDecision(
        record_id=record.record_id,
        phase="fulltext",
        votes=[vote],
        ensemble_label=out.label,
        citations_checked=[record.record_id],
    )
    return decision, meta
