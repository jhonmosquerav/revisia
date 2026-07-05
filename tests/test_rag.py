"""Tests de grounding semántico (embedder portátil + verificador)."""

from __future__ import annotations

from prisma_loop.agents.verificador import verify_narrative
from prisma_loop.rag.embed import HashEmbedder
from prisma_loop.rag.store import cosine, semantic_similarity


def test_hash_embedder_determinista() -> None:
    e = HashEmbedder()
    assert e.embed("hola mundo") == e.embed("hola mundo")


def test_cosine_de_vector_consigo_mismo_es_uno() -> None:
    v = HashEmbedder().embed("machine learning systematic review")
    assert abs(cosine(v, v) - 1.0) < 1e-9


def test_similitud_mayor_con_texto_relacionado() -> None:
    e = HashEmbedder()
    source = "machine learning improves screening recall in systematic reviews"
    related = "machine learning improves screening recall"
    unrelated = "italian cooking pasta tomato recipe"
    assert semantic_similarity(e, related, source) > semantic_similarity(e, unrelated, source)


def test_verify_narrative_grounding_semantico() -> None:
    e = HashEmbedder()
    sources = {
        "rec-1": "machine learning improves screening recall in systematic reviews of evidence"
    }

    grounded = "Según [rec-1]: machine learning improves screening recall in systematic reviews."
    report = verify_narrative("reporte", grounded, ["rec-1"], sources=sources, embedder=e)
    assert report.hallucination_flagged is False

    # Cita a un id real pero con contenido no relacionado → baja similitud → se marca.
    ungrounded = "El estudio [rec-1] trata sobre cocina italiana, pasta y tomate; nada relacionado."
    report2 = verify_narrative("reporte", ungrounded, ["rec-1"], sources=sources, embedder=e)
    assert report2.hallucination_flagged is True
