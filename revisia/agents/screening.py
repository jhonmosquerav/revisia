"""Agente de screening título/abstract (🤖 razonamiento).

Evalúa cada registro contra la pregunta y los criterios I/E. Soporta **ensemble
multi-modelo**: varios revisores (modelos) votan y se combinan con voto sesgado
a recall (ver :mod:`revisia.llm.ensemble`). Con un solo miembro se comporta
como un revisor único. La decisión final SIEMPRE es del humano (A1): este agente
solo propone.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from revisia.llm.base import LLMProvider, LLMRequest
from revisia.llm.ensemble import recall_biased_label
from revisia.prompts import load_prompt
from revisia.provenance.runmeta import RunMeta
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision, ScreeningLabel, ScreeningVote

_SYSTEM = "Eres un asistente metodológico riguroso para revisiones sistemáticas PRISMA."


class _ScreeningOut(BaseModel):
    """Salida estructurada que el LLM debe producir por registro."""

    label: ScreeningLabel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    criteria_violated: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class ScreenerMember:
    """Un revisor del ensemble: un proveedor con su etiqueta y sus parámetros."""

    provider: LLMProvider
    model_name: str
    temperature: float = 0.0
    seed: int | None = None


def screen_record(
    members: list[ScreenerMember],
    *,
    question: str,
    criteria: str,
    record: SearchRecord,
) -> tuple[ScreeningDecision, list[RunMeta]]:
    """Criba un registro con uno o varios modelos y agrega los votos.

    Returns:
        Tupla ``(decisión, lista_de_RunMeta)`` — un RunMeta por miembro.
    """
    prompt = load_prompt("screening").format(
        question=question,
        criteria=criteria,
        title=record.title,
        abstract=record.abstract or "(sin abstract disponible)",
    )
    votes: list[ScreeningVote] = []
    metas: list[RunMeta] = []
    for member in members:
        req = LLMRequest(
            prompt=prompt,
            system=_SYSTEM,
            temperature=member.temperature,
            seed=member.seed,
        )
        out, meta = member.provider.structured(req, _ScreeningOut)
        votes.append(
            ScreeningVote(
                model=member.model_name,
                label=out.label,
                confidence=out.confidence,
                rationale=out.rationale,
                criteria_violated=out.criteria_violated,
            )
        )
        metas.append(meta)

    decision = ScreeningDecision(
        record_id=record.record_id,
        phase="title_abstract",
        votes=votes,
        ensemble_label=recall_biased_label([v.label for v in votes]),
        citations_checked=[record.record_id],
    )
    return decision, metas
