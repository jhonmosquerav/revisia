"""Tests del grounding por juicio de modelo (anti-alucinación sin vectores)."""

from __future__ import annotations

from revisia.agents import verificador
from revisia.llm import ProviderConfig, build_provider
from revisia.rag.grounding import GroundingVerdict, make_provider_judge


def test_make_provider_judge_con_fake_devuelve_veredicto() -> None:
    provider = build_provider(ProviderConfig(provider="fake", model="fake-1"))
    judge = make_provider_judge(provider, "fake:fake-1")
    verdict = judge("afirmación", "fuente que respalda")
    assert isinstance(verdict, GroundingVerdict)
    assert verdict.grounded is True  # el proveedor fake fabrica bool=True


def test_verify_narrative_usa_el_juez_y_marca_no_grounded() -> None:
    text = "La IA reduce la carga del cribado [estudio-1] pero no la elimina [estudio-2]."
    sources = {"estudio-1": "fuente uno", "estudio-2": "fuente dos"}

    # Juez de prueba: decide por la FUENTE (respalda "fuente uno", refuta el resto).
    def judge(claim: str, source: str) -> GroundingVerdict:
        if "uno" in source:
            return GroundingVerdict(grounded=True, support_quote="cita de soporte")
        return GroundingVerdict(grounded=False, reason="la fuente no lo respalda")

    report = verificador.verify_narrative(
        "reporte",
        text,
        ["estudio-1", "estudio-2"],
        sources=sources,
        judge=judge,
    )
    by_id = {c.cited_id: c for c in report.checks}
    assert by_id["estudio-1"].grounded is True
    assert "soporte" in (by_id["estudio-1"].note or "")
    assert by_id["estudio-2"].grounded is False
    assert report.hallucination_flagged is True


def test_juez_tiene_prioridad_sobre_embedder() -> None:
    # Con juez Y embedder, manda el juez.
    from revisia.rag.embed import HashEmbedder

    def judge(claim: str, source: str) -> GroundingVerdict:
        return GroundingVerdict(grounded=True, support_quote="ok")

    report = verificador.verify_narrative(
        "reporte",
        "Afirmación [x].",
        ["x"],
        sources={"x": "texto en otro idioma sin solape léxico"},
        embedder=HashEmbedder(),
        judge=judge,
    )
    assert report.checks[0].grounded is True
    assert report.hallucination_flagged is False
