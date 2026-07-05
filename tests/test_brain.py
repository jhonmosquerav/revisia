"""Tests del cerebro de investigador (memoria persistente en markdown + JSONL)."""

from __future__ import annotations

import json

from prisma_loop.memory import ResearchBrain


def test_record_review_escribe_las_capas(tmp_path) -> None:
    brain = ResearchBrain(tmp_path / "cerebro")
    episode = brain.record_review(
        slug="ia-prisma",
        timestamp="20260628",
        question="¿Cómo se aplica la IA al proceso PRISMA?",
        counts={"identified": 24, "included": 2},
        included_ids=["10.1/x", "10.2/y"],
        narrative="La IA acelera el cribado [10.1/x].",
        models=["agent:opus"],
        extractions={"10.1/x": {"tecnica_ia": {"value": "LLM"}}},
        titles={"10.1/x": "Un estudio", "10.2/y": "Otro estudio"},
    )
    root = tmp_path / "cerebro"
    assert (root / "genome" / "events.jsonl").exists()
    assert (root / "wiki" / "semantic" / "ia-prisma.md").exists()
    assert episode.exists() and episode.name == "ia-prisma-20260628.md"
    assert (root / "raw" / "ia-prisma-20260628" / "incluidos.md").exists()
    assert (root / "index.md").exists()

    # El evento JSONL es válido y registra los incluidos.
    line = (root / "genome" / "events.jsonl").read_text(encoding="utf-8").strip()
    event = json.loads(line)
    assert event["slug"] == "ia-prisma"
    assert event["n_included"] == 2
    # El raw incluye el valor extraído.
    raw = (root / "raw" / "ia-prisma-20260628" / "incluidos.md").read_text(encoding="utf-8")
    assert "LLM" in raw


def test_record_review_acumula_y_reconstruye_indice(tmp_path) -> None:
    brain = ResearchBrain(tmp_path / "cerebro")
    brain.record_review(
        slug="rev-a",
        timestamp="t1",
        question="P A",
        counts={},
        included_ids=["a"],
        narrative="n",
        models=[],
    )
    brain.record_review(
        slug="rev-b",
        timestamp="t2",
        question="P B",
        counts={},
        included_ids=["b", "c"],
        narrative="n",
        models=[],
    )
    events = (tmp_path / "cerebro" / "genome" / "events.jsonl").read_text(encoding="utf-8")
    assert events.count("\n") == 2  # dos eventos acumulados
    index = (tmp_path / "cerebro" / "index.md").read_text(encoding="utf-8")
    assert "rev-a" in index and "rev-b" in index


def test_record_from_run_lee_artefactos(tmp_path) -> None:
    run = tmp_path / "runs" / "demo-20260628"
    (run / "05_extraction").mkdir(parents=True)
    (run / "deliverable").mkdir(parents=True)
    (run / "manifest.yml").write_text(
        "slug: demo\ntimestamp: '20260628'\n"
        "protocol:\n  question:\n    text: '¿Pregunta?'\n"
        "counts:\n  included: 1\n"
        "models_used:\n  - agent:opus\n",
        encoding="utf-8",
    )
    (run / "05_extraction" / "extractions.json").write_text(
        json.dumps({"10.1/x": {"study_id": "10.1/x", "fields": {"tecnica_ia": {"value": "LLM"}}}}),
        encoding="utf-8",
    )
    (run / "deliverable" / "documento.md").write_text(
        "# Demo\n\nSíntesis [10.1/x].\n", encoding="utf-8"
    )
    (run / "deliverable" / "referencias.bib").write_text(
        "@article{x,\n  title = {Un estudio real},\n  doi = {10.1/x},\n}\n", encoding="utf-8"
    )

    brain = ResearchBrain(tmp_path / "cerebro")
    episode = brain.record_from_run(run)
    assert episode.exists()
    semantic = (tmp_path / "cerebro" / "wiki" / "semantic" / "demo.md").read_text(encoding="utf-8")
    assert "Un estudio real" in semantic  # título resuelto desde el .bib
    assert "10.1/x" in semantic
