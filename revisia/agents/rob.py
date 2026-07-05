"""Agente de riesgo de sesgo / calidad (🤖 razonamiento · §7 del doc canónico).

La herramienta es configurable por revisión; cada una define sus dominios. El
LLM juzga cada dominio con una cita de soporte y propone un juicio global. El
estado del arte da ~72% de acuerdo IA-humano: por eso la autonomía es A0 (el
experto humano confirma o corrige cada juicio).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from revisia.llm.base import LLMProvider, LLMRequest
from revisia.prompts import load_prompt
from revisia.provenance.runmeta import RunMeta
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.records import SearchRecord
from revisia.schemas.rob import RoBAssessment, RoBDomain, RoBJudgment, RoBTool

_SYSTEM = "Eres un metodólogo experto en evaluación de riesgo de sesgo (Cochrane/JBI)."

# Dominios por herramienta (los nombres se inyectan en el prompt y se esperan de vuelta).
TOOL_DOMAINS: dict[RoBTool, list[str]] = {
    "RoB2": [
        "Proceso de aleatorización",
        "Desviaciones de las intervenciones previstas",
        "Datos de resultado faltantes",
        "Medición del resultado",
        "Selección del resultado reportado",
    ],
    "ROBINS-I": [
        "Confusión",
        "Selección de participantes",
        "Clasificación de las intervenciones",
        "Desviaciones de las intervenciones previstas",
        "Datos faltantes",
        "Medición de los resultados",
        "Selección del resultado reportado",
    ],
    "NewcastleOttawa": ["Selección", "Comparabilidad", "Resultado/Exposición"],
    "AMSTAR2": [
        "Protocolo registrado a priori",
        "Búsqueda exhaustiva",
        "Selección y extracción por duplicado",
        "Riesgo de sesgo de estudios incluidos",
        "Métodos de síntesis apropiados",
        "Evaluación del sesgo de publicación",
    ],
    "QUADAS-2": [
        "Selección de pacientes",
        "Prueba índice",
        "Estándar de referencia",
        "Flujo y tiempos",
    ],
    "GRADE": [
        "Riesgo de sesgo",
        "Inconsistencia",
        "Evidencia indirecta",
        "Imprecisión",
        "Sesgo de publicación",
    ],
}


class _RoBDomainOut(BaseModel):
    domain: str
    judgment: RoBJudgment
    rationale: str = ""
    support_quote: str | None = None


class _RoBOut(BaseModel):
    domains: list[_RoBDomainOut] = Field(default_factory=list)
    overall: RoBJudgment = "unclear"


def assess_rob(
    provider: LLMProvider,
    *,
    tool: RoBTool,
    record: SearchRecord,
    extraction: ExtractionRecord | None = None,
    text: str | None = None,
    temperature: float = 0.0,
    seed: int | None = None,
) -> tuple[RoBAssessment, RunMeta]:
    """Evalúa el riesgo de sesgo de un estudio con la herramienta dada."""
    domains = TOOL_DOMAINS.get(tool, [])
    extracted_desc = ""
    if extraction:
        extracted_desc = "; ".join(
            f"{k}={v.value}" for k, v in extraction.fields.items() if v.value
        )
    prompt = load_prompt("rob").format(
        tool=tool,
        title=record.title,
        text=text or record.abstract or "(sin texto disponible)",
        extracted=extracted_desc or "(sin extracción)",
        domains="\n".join(f"- {d}" for d in domains),
    )
    req = LLMRequest(prompt=prompt, system=_SYSTEM, temperature=temperature, seed=seed)
    out, meta = provider.structured(req, _RoBOut)
    assessment = RoBAssessment(
        study_id=record.record_id,
        tool=tool,
        domains=[
            RoBDomain(
                domain=d.domain,
                judgment=d.judgment,
                rationale=d.rationale,
                support_quote=d.support_quote,
            )
            for d in out.domains
        ],
        overall=out.overall,
    )
    return assessment, meta
