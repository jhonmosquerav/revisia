"""Evaluación de riesgo de sesgo / calidad (§7 del documento canónico).

La herramienta es configurable por revisión (RoB2 para ensayos, ROBINS-I /
Newcastle-Ottawa para observacionales, AMSTAR-2 para umbrella, QUADAS-2 para
diagnóstico). GRADE ya no es una herramienta de sesgo: califica la certeza por
desenlace y vuelve como etapa propia (D5). El estado del arte indica ~72% de
acuerdo IA-humano: por eso esta etapa es A0 (juicio final del experto humano).

v2 (Ola 2): ``judgment`` es ``str`` porque la escala la valida la especificación de la
herramienta y no el modelo, de modo que una evaluación 0.8 siga cargando (§19, fila 2).
``RoBDomain.id`` es opcional en el esquema: el agente lo rellena siempre y el auditor da
FAIL si falta.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from revisia.schemas.artifacts import ARTIFACT_SCHEMA_VERSION, QuoteStatus, RecordStatus, SourceText

RoBTool = Literal[
    "RoB2",
    "ROBINS-I",
    "NewcastleOttawa",
    "NewcastleOttawaCaseControl",
    "AMSTAR2",
    "QUADAS-2",
]
# Alias que aún usa el agente (``_RoBDomainOut``) hasta PR-E; ningún modelo de aquí lo exige.
RoBJudgment = Literal["low", "some_concerns", "high", "unclear"]


class RoBDomain(BaseModel):
    """Juicio de un dominio de sesgo con su evidencia textual.

    Attributes:
        domain: nombre legible del dominio.
        id: id oficial en la especificación de la herramienta (opcional en el esquema).
        judgment: juicio del modelo; la escala válida la fija la herramienta.
        answers: respuestas a las preguntas señalizadoras, por id de pregunta.
        human_judgment: juicio del experto, si corrigió; exige razón y actor.
    """

    domain: str
    id: str | None = None
    judgment: str
    rationale: str = ""
    support_quote: str | None = None
    quote_status: QuoteStatus = "none"
    answers: dict[str, str] = Field(default_factory=dict)
    human_judgment: str | None = None
    human_reason: str | None = None
    human_actor: str | None = None

    @model_validator(mode="after")
    def _humano_atado(self) -> RoBDomain:
        """Un juicio humano sin razón ni actor no es auditable."""
        if self.human_judgment is not None and (
            self.human_reason is None or self.human_actor is None
        ):
            raise ValueError("human_judgment exige human_reason y human_actor")
        return self


class RoBApplicability(BaseModel):
    """Preocupación de aplicabilidad de un dominio (QUADAS-2)."""

    id: str
    judgment: str
    rationale: str = ""


class RoBAssessment(BaseModel):
    """Evaluación de riesgo de sesgo de un estudio.

    Attributes:
        study_id: id del estudio evaluado.
        tool: herramienta usada (debe coincidir con el diseño del estudio).
        tool_version: versión de la herramienta aplicada.
        domains: juicios por dominio.
        applicability: preocupaciones de aplicabilidad (QUADAS-2).
        overall_llm: juicio global propuesto por el modelo.
        overall_algorithm: juicio global derivado por el algoritmo de la herramienta.
        overall_human: juicio global del experto; exige ``overall_reason``.
        overall: juicio global final (hoy el agente lo fija directamente).
    """

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    study_id: str
    tool: RoBTool
    tool_version: str | None = None
    domains: list[RoBDomain] = Field(default_factory=list)
    applicability: list[RoBApplicability] = Field(default_factory=list)
    overall_llm: str | None = None
    overall_algorithm: str | None = None
    overall_human: str | None = None
    overall_reason: str | None = None
    overall: str | None = None
    source_text: SourceText = "abstract"
    status: RecordStatus = "ok"

    @model_validator(mode="after")
    def _global_humano_atado(self) -> RoBAssessment:
        """El juicio global del experto exige su razón."""
        if self.overall_human is not None and self.overall_reason is None:
            raise ValueError("overall_human exige overall_reason")
        return self
