"""Tests del agente de riesgo de sesgo (offline · proveedor fake)."""

from __future__ import annotations

from prisma_loop.agents.rob import TOOL_DOMAINS, assess_rob
from prisma_loop.llm.providers.fake import FakeProvider
from prisma_loop.schemas.records import SearchRecord


def test_cada_herramienta_tiene_dominios() -> None:
    for tool in ("RoB2", "ROBINS-I", "NewcastleOttawa", "AMSTAR2", "QUADAS-2", "GRADE"):
        assert len(TOOL_DOMAINS[tool]) >= 3


def test_assess_rob_produce_assessment() -> None:
    record = SearchRecord(record_id="rec-1", title="Un ensayo", abstract="RCT con 200 sujetos.")
    assessment, meta = assess_rob(FakeProvider(), tool="RoB2", record=record)
    assert assessment.study_id == "rec-1"
    assert assessment.tool == "RoB2"
    assert assessment.overall in {"low", "some_concerns", "high", "unclear"}
    assert meta.provider == "fake"
