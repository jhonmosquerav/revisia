"""Tests de los exports de interoperabilidad (robvis, metafor, PRISMA2020)."""

from __future__ import annotations

from prisma_loop.exports import (
    PrismaCounts,
    render_metafor_csv,
    render_prisma2020_flow_csv,
    render_prisma_abstracts_checklist,
    render_robvis_csv,
)
from prisma_loop.meta_analysis import meta_analyze
from prisma_loop.schemas.effects import EffectInput
from prisma_loop.schemas.rob import RoBAssessment, RoBDomain


def test_robvis_csv_una_fila_por_estudio() -> None:
    assessments = {
        "10.1/a": RoBAssessment(
            study_id="10.1/a",
            tool="RoB2",
            domains=[
                RoBDomain(domain="D1 aleatorización", judgment="low"),
                RoBDomain(domain="D2 desviaciones", judgment="some_concerns"),
            ],
            overall="some_concerns",
        ),
        "10.2/b": RoBAssessment(
            study_id="10.2/b",
            tool="RoB2",
            domains=[RoBDomain(domain="D1 aleatorización", judgment="high")],
            overall="high",
        ),
    }
    csv_text = render_robvis_csv(assessments)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "Study,D1 aleatorización,D2 desviaciones,Overall"
    assert lines[1] == "10.1/a,Low,Some concerns,Some concerns"
    # dominio ausente → "No information" (vocabulario robvis)
    assert lines[2] == "10.2/b,High,No information,High"


def test_metafor_csv_trae_yi_vi() -> None:
    result = meta_analyze(
        [
            EffectInput(study_id="s1", yi=0.2, vi=0.04),
            EffectInput(study_id="s2", yi=0.5, vi=0.09),
        ],
        measure="precomputed",
    )
    csv_text = render_metafor_csv(result)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "study_id,label,measure,yi,vi"
    assert lines[1].startswith("s1,")
    assert ",precomputed," in lines[1]
    assert "0.2" in lines[1] and "0.04" in lines[1]


def test_prisma2020_flow_csv_conteos() -> None:
    counts = PrismaCounts(
        identified=100,
        duplicates_removed=20,
        screened=80,
        excluded_ta=60,
        fulltext_assessed=20,
        excluded_ft=5,
        included=15,
    )
    csv_text = render_prisma2020_flow_csv(counts)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "phase,box,n"
    assert "identification,Records identified from databases,100" in lines
    assert "included,Studies included in review,15" in lines


def test_checklist_abstracts_prerellena_evidencia() -> None:
    counts = PrismaCounts(included=7)
    markdown = render_prisma_abstracts_checklist(
        counts=counts,
        databases=["OpenAlex", "Crossref"],
        search_window={"from": "2015-01-01", "to": "2026-12-31", "executed": "2026-07-05"},
        registration={"prospero": "CRD42026XXXXXX"},
    )
    assert "Checklist PRISMA 2020 · resúmenes" in markdown
    assert markdown.count("- [ ]") == 12
    assert "OpenAlex, Crossref" in markdown
    assert "2026-07-05" in markdown
    assert "7 estudios incluidos" in markdown
    assert "CRD42026XXXXXX" in markdown


def test_checklist_abstracts_sin_datos_deja_completar() -> None:
    markdown = render_prisma_abstracts_checklist()
    assert markdown.count("_(completar)_") == 12
