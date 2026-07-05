"""Tests del verificador anti-alucinación (golden test del grounding)."""

from __future__ import annotations

from prisma_loop.agents.verificador import extract_citations, verify_narrative


def test_extrae_citas_sin_duplicar() -> None:
    assert extract_citations("foo [rec-1] bar [rec-2] baz [rec-1]") == ["rec-1", "rec-2"]


def test_narrativa_grounded_no_marca() -> None:
    report = verify_narrative("reporte", "El estudio [rec-1] reporta X.", ["rec-1", "rec-2"])
    assert report.hallucination_flagged is False


def test_cita_fabricada_se_marca() -> None:
    # Golden test: una cita a un id que NO está en el corpus debe bloquear.
    report = verify_narrative("reporte", "Según [rec-999], el efecto es grande.", ["rec-1"])
    assert report.hallucination_flagged is True
    assert any(c.cited_id == "rec-999" and not c.exists_in_corpus for c in report.checks)
