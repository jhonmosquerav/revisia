"""Decisiones de screening (título/abstract y full-text).

Modela el patrón de la §5 del documento canónico: dos revisores independientes
+ resolución de desacuerdos. Aquí los "revisores" pueden ser varios modelos
(ensemble) y un humano; el voto del ensemble está **sesgado a recall** (incluir
si cualquier modelo incluye) para minimizar falsos negativos / lost-evidence.
La decisión final es siempre del humano.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ScreeningLabel = Literal["include", "exclude", "unclear"]


class ScreeningVote(BaseModel):
    """Voto de un único revisor (modelo) sobre un registro.

    Attributes:
        model: identificador del modelo que emitió el voto.
        label: decisión propuesta.
        confidence: confianza en [0, 1].
        rationale: justificación breve.
        criteria_violated: criterios de exclusión que el registro incumple.
    """

    model: str
    label: ScreeningLabel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    criteria_violated: list[str] = Field(default_factory=list)


class ScreeningDecision(BaseModel):
    """Decisión agregada para un registro, con trazabilidad completa.

    Attributes:
        record_id: id del registro evaluado.
        phase: ``"title_abstract"`` o ``"fulltext"``.
        votes: votos individuales del ensemble.
        ensemble_label: resultado del voto (sesgado a recall).
        human_label: decisión del revisor humano (HITL), si ya se tomó.
        final_label: decisión final aplicada (== humana cuando existe).
        citations_checked: ids verificados contra el corpus (anti-alucinación).
    """

    record_id: str
    phase: Literal["title_abstract", "fulltext"] = "title_abstract"
    votes: list[ScreeningVote] = Field(default_factory=list)
    ensemble_label: ScreeningLabel | None = None
    human_label: ScreeningLabel | None = None
    final_label: ScreeningLabel | None = None
    citations_checked: list[str] = Field(default_factory=list)
