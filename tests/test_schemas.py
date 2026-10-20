"""Tests de los schemas Pydantic por etapa."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from revisia.schemas import (
    ExtractionField,
    ExtractionRecord,
    QuestionFramework,
    ResearchQuestion,
    ScreeningVote,
    VerificationReport,
)
from revisia.schemas.rob import RoBAssessment, RoBDomain, RoBTool
from revisia.schemas.verification import CitationCheck, JudgeInfo, UncitedClaim


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


def test_verification_flagged_indices_es_la_regla_unica_de_cita_marcada() -> None:
    # Marcada = inexistente en el corpus o sin respaldo; `recompute_flag` y la solicitud del gate
    # final (`must_adjudicate`) usan esta misma regla.
    report = VerificationReport(
        stage="sintesis",
        checks=[
            CitationCheck(claim="A", cited_id="rec-1", exists_in_corpus=True, grounded=True),
            CitationCheck(claim="B", cited_id="rec-99", exists_in_corpus=False, grounded=True),
            CitationCheck(claim="C", cited_id="rec-2", exists_in_corpus=True, grounded=False),
            CitationCheck(claim="D", cited_id=None),
        ],
    )
    assert report.flagged_indices() == [1, 2, 3]
    assert report.recompute_flag() is True
    assert VerificationReport(stage="sintesis").flagged_indices() == []


def test_extraction_field_v2_final_value_y_coherencia_humana() -> None:
    campo = ExtractionField(value="240")
    assert (campo.quote_status, campo.quote_offset, campo.human_edited) == ("none", None, False)
    assert campo.final_value == "240"
    editado = ExtractionField(
        value="240",
        human_value=236,
        human_reason="tabla 2",
        human_actor="human:ana",
        human_edited=True,
    )
    assert editado.final_value == 236
    with pytest.raises(ValidationError):  # editado sin razón ni actor
        ExtractionField(value="1", human_value="2", human_edited=True)
    with pytest.raises(ValidationError):  # valor humano sin marcar la edición
        ExtractionField(value="1", human_value="2")
    with pytest.raises(ValidationError):
        ExtractionField(value="1", quote_status="maybe")


def test_extraction_record_v1_valida_como_abstract_ok() -> None:
    v1 = {"study_id": "s", "fields": {"n": {"value": "240"}}, "extractor": "agent:extraccion"}
    rec = ExtractionRecord.model_validate(v1)
    assert (rec.schema_version, rec.source_text, rec.text_sha256, rec.truncated, rec.status) == (
        2,
        "abstract",
        None,
        False,
        "ok",
    )
    assert ExtractionRecord(study_id="s", status="failed").fields == {}


def test_rob_tool_sin_grade_y_con_nos_casos_controles() -> None:
    assert set(get_args(RoBTool)) == {
        "RoB2",
        "ROBINS-I",
        "NewcastleOttawa",
        "NewcastleOttawaCaseControl",
        "AMSTAR2",
        "QUADAS-2",
    }
    with pytest.raises(ValidationError):
        RoBAssessment(study_id="s", tool="GRADE")


def test_rob_assessment_v1_valida_y_los_campos_humanos_van_atados() -> None:
    v1 = {
        "study_id": "s",
        "tool": "RoB2",
        "domains": [{"domain": "Proceso de aleatorización", "judgment": "low"}],
        "overall": "low",
    }
    a = RoBAssessment.model_validate(v1)
    assert (a.schema_version, a.tool_version, a.overall_llm, a.overall_algorithm) == (
        2,
        None,
        None,
        None,
    )
    assert a.domains[0].id is None and a.domains[0].quote_status == "none"
    with pytest.raises(ValidationError):
        RoBDomain(domain="D1", judgment="low", human_judgment="high")
    with pytest.raises(ValidationError):
        RoBAssessment(study_id="s", tool="RoB2", overall_human="high")
    ok = RoBAssessment(study_id="s", tool="RoB2", overall_human="high", overall_reason="r")
    assert ok.overall_human == "high"


def test_verification_report_v1_valida_sin_modo_ni_juez() -> None:
    v1 = {
        "stage": "reporte",
        "checks": [{"claim": "A", "cited_id": "rec-1", "exists_in_corpus": True, "grounded": True}],
        "hallucination_flagged": False,
    }
    report = VerificationReport.model_validate(v1)
    assert (report.schema_version, report.mode, report.judge, report.n_claims) == (2, None, None, 0)
    check = report.checks[0]
    assert (check.index, check.source_available, check.numbers_missing, check.quote_status) == (
        None,
        True,
        [],
        "none",
    )


def test_verification_report_v2_coherencia_de_modo_y_cifras_sin_cita() -> None:
    with pytest.raises(ValidationError):  # judge sin juez
        VerificationReport(stage="reporte", mode="judge")
    with pytest.raises(ValidationError):  # contador distinto de la lista
        VerificationReport(stage="reporte", n_uncited_quantitative=1)
    ok = VerificationReport(
        stage="reporte",
        mode="judge",
        judge=JudgeInfo(provider="zai", model="glm"),
        n_uncited_quantitative=1,
        uncited_quantitative=[UncitedClaim(claim_index=3, sentence="El 40 % …", numbers=["40"])],
    )
    assert ok.judge is not None and ok.judge.model == "glm"
    with pytest.raises(ValidationError):
        CitationCheck(claim="x" * 601, cited_id="r")
