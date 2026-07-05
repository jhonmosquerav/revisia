"""Evaluación de riesgo de sesgo / calidad (§7 del documento canónico).

La herramienta es configurable por revisión (RoB2 para ensayos, ROBINS-I /
Newcastle-Ottawa para observacionales, AMSTAR-2 para umbrella, QUADAS-2 para
diagnóstico, GRADE para certeza agregada). El estado del arte indica ~72% de
acuerdo IA-humano: por eso esta etapa es A0 (juicio final del experto humano).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RoBTool = Literal["RoB2", "ROBINS-I", "NewcastleOttawa", "AMSTAR2", "QUADAS-2", "GRADE"]
RoBJudgment = Literal["low", "some_concerns", "high", "unclear"]


class RoBDomain(BaseModel):
    """Juicio de un dominio de sesgo con su evidencia textual."""

    domain: str
    judgment: RoBJudgment
    rationale: str = ""
    support_quote: str | None = None


class RoBAssessment(BaseModel):
    """Evaluación de riesgo de sesgo de un estudio.

    Attributes:
        study_id: id del estudio evaluado.
        tool: herramienta usada (debe coincidir con el diseño del estudio).
        domains: juicios por dominio.
        overall: juicio global propuesto (lo confirma el humano).
    """

    study_id: str
    tool: RoBTool
    domains: list[RoBDomain] = Field(default_factory=list)
    overall: RoBJudgment | None = None
