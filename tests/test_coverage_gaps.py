"""Tests de exclusiones humano/IA, acuerdo de extracción y metodologia.md."""

from __future__ import annotations

from revisia.config import ReviewProtocol
from revisia.exclusions import compute_exclusion_breakdown, compute_ft_excluded
from revisia.exports import (
    PrismaCounts,
    render_excluded_reports,
    render_methods,
    render_prisma_2020_checklist,
)
from revisia.extraction_agreement import (
    compute_extraction_agreement,
    select_double_extraction_subset,
)
from revisia.schemas.extraction import ExtractionField, ExtractionRecord
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision, ScreeningVote

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


def test_acuerdo_extraccion_sin_pares_kappa_none() -> None:
    agr = compute_extraction_agreement({}, {})
    assert agr.presence_kappa is None
    assert agr.value_agreement is None


def test_acuerdo_extraccion_kappa_indefinido_no_revienta() -> None:
    # Todos los campos presentes en ambos extractores: κ de presencia indefinido.
    # Antes cohen_kappa devolvía 0.0; con None, el modelo debe aceptarlo.
    def ext(rid: str) -> ExtractionRecord:
        return ExtractionRecord(study_id=rid, fields={"d": ExtractionField(value="RCT")})

    agr = compute_extraction_agreement({"a": ext("a")}, {"a": ext("a")})
    assert agr.presence_kappa is None


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


def test_methods_reporta_buscados_y_no_recuperados() -> None:
    protocol = ReviewProtocol.model_validate(
        {
            "slug": "demo",
            "title": "Demo",
            "question": {"text": "¿X afecta Y?", "framework": "PEO", "components": {"P": "x"}},
        }
    )
    counts = PrismaCounts(
        identified=50,
        screened=40,
        fulltext_sought=12,
        fulltext_not_retrieved=4,
        fulltext_assessed=8,
        included=5,
    )
    md = render_methods(protocol=protocol, counts=counts, models=["fake:fake-1"])
    assert "buscados a texto completo=12" in md
    assert "no recuperados=4" in md
    assert "evaluados para elegibilidad=8" in md
    assert "texto completo=8 " not in md  # la cifra ambigua de antes


def test_excluidos_16b_con_razon_y_origen() -> None:
    def ft(rid: str, ia: str, violados: list[str], humano=None, razon=None):
        return ScreeningDecision(
            record_id=rid,
            phase="fulltext",
            fulltext_status="retrieved",
            votes=[
                ScreeningVote(model="fake:x", label=ia, confidence=0.9, criteria_violated=violados)
            ],
            ensemble_label=ia,
            human_label=humano,
            human_reason=razon,
            final_label=humano or ia,
        )

    records = [
        SearchRecord(record_id="10.1/a", title="Estudio A | piloto", year=2021, doi="10.1/a"),
        SearchRecord(record_id="b", title="Estudio B"),
        SearchRecord(record_id="c", title="Estudio C"),
        SearchRecord(record_id="d", title="Estudio D"),
    ]
    decisions = [
        ft("10.1/a", "exclude", ["población incorrecta", "diseño"]),  # IA, primer criterio
        ft("b", "exclude", []),  # IA sin criterio
        ft("c", "include", [], humano="exclude", razon="sin grupo control"),  # humano
        ft("d", "include", []),  # incluido: no aparece
        ScreeningDecision(record_id="e", phase="fulltext", fulltext_status="not_retrieved"),
    ]
    reports = compute_ft_excluded(decisions, records)
    assert [(r.record_id, r.reason, r.reason_source) for r in reports] == [
        ("10.1/a", "población incorrecta", "ai"),
        ("b", "criterio no especificado", "ai"),
        ("c", "sin grupo control", "human"),
    ]
    assert (reports[0].year, reports[0].doi) == (2021, "10.1/a")

    md = render_excluded_reports(reports)
    assert "PRISMA 2020, ítem 16b" in md
    assert "| Estudio A \\| piloto (`10.1/a`) | 2021 | 10.1/a | población incorrecta | IA |" in md
    assert "| Estudio C (`c`) | — | — | sin grupo control | humano |" in md
    assert "ningún informe excluido" in render_excluded_reports([])
    assert "excluidos_texto_completo.md (16b)" in render_prisma_2020_checklist()
