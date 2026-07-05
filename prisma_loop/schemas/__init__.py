"""Structured output (Pydantic) por etapa del pipeline PRISMA.

Cada agente produce y consume estos modelos; los proveedores LLM los usan como
``response_schema`` para forzar salida válida (sin texto a parsear a mano).
"""

from __future__ import annotations

from prisma_loop.schemas.extraction import ExtractionField, ExtractionRecord
from prisma_loop.schemas.question import QuestionFramework, ResearchQuestion
from prisma_loop.schemas.records import SearchRecord
from prisma_loop.schemas.rob import RoBAssessment, RoBDomain
from prisma_loop.schemas.screening import ScreeningDecision, ScreeningVote
from prisma_loop.schemas.verification import CitationCheck, VerificationReport

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
