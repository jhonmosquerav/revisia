"""Campos y constantes aditivos de PR-0: no cambian el comportamiento (spec §4.5)."""

from __future__ import annotations

from pathlib import Path

from revisia.config import KNOWN_THRESHOLDS, load_protocol
from revisia.exports import PrismaCounts
from revisia.schemas.screening import ScreeningDecision

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"


def test_known_thresholds_cubre_la_plantilla_y_el_pipeline() -> None:
    assert set(KNOWN_THRESHOLDS) == {"kappa_min", "recall_target", "wmcc_fn_weight"}
    assert set(load_protocol(TEMPLATE_DIR).thresholds) <= KNOWN_THRESHOLDS


def test_screening_decision_campos_nuevos_opcionales() -> None:
    antigua = {"record_id": "a", "ensemble_label": "include", "final_label": "include"}
    decision = ScreeningDecision.model_validate(antigua)
    assert decision.fulltext_status is None
    assert decision.human_reason is None and decision.human_actor is None
    no_recuperado = ScreeningDecision(
        record_id="b", phase="fulltext", fulltext_status="not_retrieved"
    )
    assert no_recuperado.votes == [] and no_recuperado.ensemble_label is None


def test_prisma_counts_campos_nuevos_valen_cero() -> None:
    counts = PrismaCounts(identified=10, screened=8, included=2)
    assert (
        counts.fulltext_sought,
        counts.fulltext_not_retrieved,
        counts.fulltext_rescued,
        counts.excluded_ft_human,
        counts.excluded_ft_ai,
    ) == (0, 0, 0, 0, 0)
    assert PrismaCounts.model_validate(counts.model_dump()) == counts
