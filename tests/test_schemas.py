"""Tests de los schemas Pydantic por etapa."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from revisia.schemas import (
    ExtractionField,
    QuestionFramework,
    ResearchQuestion,
    ScreeningVote,
    VerificationReport,
)
from revisia.schemas.verification import CitationCheck


def test_research_question_framework_enum() -> None:
    q = ResearchQuestion(
        text="¿Funciona X en Y?",
        framework=QuestionFramework.PICO,
        components={"Population": "Y", "Intervention": "X"},
    )
    assert q.framework is QuestionFramework.PICO
    assert q.framework.value == "PICO"


def test_screening_vote_acota_confianza() -> None:
    ScreeningVote(model="m", label="include", confidence=0.9)
    with pytest.raises(ValidationError):
        ScreeningVote(model="m", label="include", confidence=1.5)


def test_extraction_field_default_needs_review() -> None:
    field = ExtractionField(value="156")
    assert field.status == "needs_review"
    assert field.confidence == 0.0


def test_verification_recompute_flag() -> None:
    report = VerificationReport(
        stage="sintesis",
        checks=[
            CitationCheck(claim="A", cited_id="rec-1", exists_in_corpus=True, grounded=True),
            CitationCheck(claim="B", cited_id="rec-99", exists_in_corpus=False, grounded=False),
        ],
    )
    assert report.recompute_flag() is True

    clean = VerificationReport(
        stage="sintesis",
        checks=[CitationCheck(claim="A", cited_id="rec-1", exists_in_corpus=True, grounded=True)],
    )
    assert clean.recompute_flag() is False
