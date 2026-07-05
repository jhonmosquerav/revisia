"""Tests del cerebro de investigador (memoria persistente en markdown + JSONL)."""

from __future__ import annotations

import json

from revisia.memory import ResearchBrain


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


def test_recall_devuelve_none_sin_memoria(tmp_path) -> None:
    assert ResearchBrain(tmp_path / "cerebro").recall("inexistente") is None


def test_recall_y_delta_living_review(tmp_path) -> None:
    brain = ResearchBrain(tmp_path / "cerebro")
    brain.record_review(
        slug="rev",
        timestamp="t1",
        question="¿P?",
        counts={"included": 2},
        included_ids=["a", "b"],
        narrative="síntesis uno",
        models=[],
    )
    recall = brain.recall("rev")
    assert recall is not None
    assert recall.n_runs == 1
    assert recall.last_included_ids == ["a", "b"]
    assert "síntesis uno" in recall.semantic_summary

    brain.record_review(
        slug="rev",
        timestamp="t2",
        question="¿P?",
        counts={"included": 2},
        included_ids=["b", "c"],
        narrative="síntesis dos",
        models=[],
    )
    recall2 = brain.recall("rev")
    assert recall2 is not None
    assert recall2.n_runs == 2
    assert recall2.last_timestamp == "t2"

    # El evento nuevo lleva el delta de la actualización (living review).
    lines = (
        (tmp_path / "cerebro" / "genome" / "events.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    event = json.loads(lines[-1])
    assert event["update_of"] == "t1"
    assert event["included_new"] == ["c"]
    assert event["included_dropped"] == ["a"]

    # El episodio narra el delta.
    episode = (tmp_path / "cerebro" / "wiki" / "episodic" / "rev-t2.md").read_text(encoding="utf-8")
    assert "living review" in episode
    assert "[c]" in episode


def test_paginas_wiki_llevan_frontmatter(tmp_path) -> None:
    brain = ResearchBrain(tmp_path / "cerebro")
    brain.record_review(
        slug="rev",
        timestamp="t1",
        question="¿P?",
        counts={},
        included_ids=["a"],
        narrative="n",
        models=[],
    )
    semantic = (tmp_path / "cerebro" / "wiki" / "semantic" / "rev.md").read_text(encoding="utf-8")
    episodic = (tmp_path / "cerebro" / "wiki" / "episodic" / "rev-t1.md").read_text(
        encoding="utf-8"
    )
    assert semantic.startswith("---")
    assert "tipo: semantic" in semantic
    assert episodic.startswith("---")
    assert "tipo: episodic" in episodic
    assert "corrida: t1" in episodic


def test_summary_agrupa_por_slug(tmp_path) -> None:
    brain = ResearchBrain(tmp_path / "cerebro")
    for ts in ("t1", "t2"):
        brain.record_review(
            slug="rev-a",
            timestamp=ts,
            question="A",
            counts={},
            included_ids=["x"],
            narrative="n",
            models=[],
        )
    brain.record_review(
        slug="rev-b",
        timestamp="t9",
        question="B",
        counts={},
        included_ids=[],
        narrative="n",
        models=[],
    )
    recalls = brain.summary()
    assert [r.slug for r in recalls] == ["rev-a", "rev-b"]
    assert recalls[0].n_runs == 2
    assert recalls[1].n_runs == 1


def test_cli_brain_list_y_show(tmp_path, capsys) -> None:
    from revisia.cli import main

    brain_dir = tmp_path / "cerebro"
    ResearchBrain(brain_dir).record_review(
        slug="rev",
        timestamp="t1",
        question="¿P?",
        counts={"included": 1},
        included_ids=["a"],
        narrative="n",
        models=[],
    )
    assert main(["brain", str(brain_dir)]) == 0
    out = capsys.readouterr().out
    assert "rev" in out and "1 corrida" in out

    assert main(["brain", str(brain_dir), "rev"]) == 0
    out = capsys.readouterr().out
    assert "síntesis vigente" in out

    assert main(["brain", str(brain_dir), "no-existe"]) == 1


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
