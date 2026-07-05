"""Structured output (Pydantic) por etapa del pipeline PRISMA.

Cada agente produce y consume estos modelos; los proveedores LLM los usan como
``response_schema`` para forzar salida válida (sin texto a parsear a mano).
"""

from __future__ import annotations

from revisia.schemas.extraction import ExtractionField, ExtractionRecord
from revisia.schemas.question import QuestionFramework, ResearchQuestion
from revisia.schemas.records import SearchRecord
from revisia.schemas.rob import RoBAssessment, RoBDomain
from revisia.schemas.screening import ScreeningDecision, ScreeningVote
from revisia.schemas.verification import CitationCheck, VerificationReport

__all__ = [
    "QuestionFramework",
    "ResearchQuestion",
    "SearchRecord",
    "ScreeningVote",
    "ScreeningDecision",
    "ExtractionField",
    "ExtractionRecord",
    "RoBDomain",
    "RoBAssessment",
    "CitationCheck",
    "VerificationReport",
]
