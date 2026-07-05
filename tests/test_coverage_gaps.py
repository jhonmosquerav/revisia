"""Tests de exclusiones humano/IA, acuerdo de extracción y metodologia.md."""

from __future__ import annotations

from prisma_loop.config import ReviewProtocol
from prisma_loop.exclusions import compute_exclusion_breakdown
from prisma_loop.exports import PrismaCounts, render_methods
from prisma_loop.extraction_agreement import (
    compute_extraction_agreement,
    select_double_extraction_subset,
)
from prisma_loop.schemas.extraction import ExtractionField, ExtractionRecord
from prisma_loop.schemas.records import SearchRecord
from prisma_loop.schemas.screening import ScreeningDecision

# ── Exclusiones humano vs IA ───────────────────────────────────────────


def _dec(rid: str, ens: str, human: str | None = None) -> ScreeningDecision:
    return ScreeningDecision(
        record_id=rid, ensemble_label=ens, human_label=human, final_label=human or ens
    )


def test_exclusiones_atribuye_origen() -> None:
    decisions = [
        _dec("a", "exclude"),  # IA excluye
        _dec("b", "exclude", "include"),  # rescate humano
        _dec("c", "include", "exclude"),  # corte humano
        _dec("d", "include"),  # incluido
    ]
    b = compute_exclusion_breakdown(decisions)
    assert b.total_excluded == 2  # a (IA) + c (humano)
    assert b.excluded_ai == 1
    assert b.excluded_human == 1
    assert b.overridden_to_include == 1
    assert b.overridden_to_exclude == 1


# ── Doble extracción ───────────────────────────────────────────────────


def _rec(rid: str) -> SearchRecord:
    return SearchRecord(record_id=rid, title=f"t{rid}")


def test_subset_doble_extraccion_minimo_20pct() -> None:
    included = [_rec(f"r{i:02d}") for i in range(10)]
    subset = select_double_extraction_subset(included)
    assert len(subset) == 2  # ceil(0.2*10)
    # Determinista: misma entrada, mismo subconjunto.
    assert subset == select_double_extraction_subset(included)


def test_acuerdo_extraccion_valor_y_kappa() -> None:
    def ext(rid: str, val: str | None) -> ExtractionRecord:
        return ExtractionRecord(study_id=rid, fields={"d": ExtractionField(value=val)})

    primary = {"a": ext("a", "RCT"), "b": ext("b", "cohorte")}
    secondary = {"a": ext("a", "rct"), "b": ext("b", "RCT")}  # 'a' coincide (norm), 'b' no
    agr = compute_extraction_agreement(primary, secondary)
    assert agr.n_studies == 2
    assert agr.n_field_pairs == 2
    assert agr.n_value_match == 1  # solo 'a'
    assert agr.value_agreement == 0.5


# ── metodologia.md ─────────────────────────────────────────────────────


def test_render_methods_incluye_secciones_clave() -> None:
    protocol = ReviewProtocol.model_validate(
        {
            "slug": "demo",
            "title": "Demo",
            "question": {"text": "¿X afecta Y?", "framework": "PEO", "components": {"P": "x"}},
            "databases": ["OpenAlex", "Crossref"],
            "rob_tool": "RoB2",
            "registration": {"osf": "ABC"},
            "search_window": {"from": "2000", "to": "2026", "executed": "2026-06-27"},
        }
    )
    counts = PrismaCounts(identified=10, included=3)
    md = render_methods(protocol=protocol, counts=counts, models=["fake:fake-1"], quantitative=True)
    assert "## Método" in md
    assert "PEO" in md
    assert "OpenAlex, Crossref" in md
    assert "RoB2" in md
    assert "cuantitativa" in md  # quantitative=True
    assert "OSF: ABC" in md
    assert "executed: 2026-06-27" in md
