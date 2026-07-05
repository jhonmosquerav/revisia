"""Test end-to-end del pipeline (offline · proveedor fake + búsqueda simulada).

Demuestra el tracer bullet completo sin red ni API key: búsqueda inyectada,
dedup, screening, extracción, síntesis, verificador, gates HITL (auto-approve),
entregables y manifiesto reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

from revisia.config import load_protocol
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _fake_search(query: str, n: int) -> list[SearchRecord]:
    records = [
        SearchRecord(
            record_id="rec-1",
            title="LLM screening for systematic reviews",
            abstract="We evaluate LLM screening with recall 0.98 and 60% workload reduction.",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-1-dup",
            title="LLM screening for systematic reviews",  # mismo título → duplicado
            abstract="duplicado",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-2",
            title="Active learning with ASReview",
            abstract="Active learning reduces screening workload by 70%.",
            source_db="OpenAlex",
        ),
    ]
    return records[:n]


def test_pipeline_end_to_end_offline(tmp_path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST")
    result = run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        max_results=10,
        auto_approve=True,
        search_fn=_fake_search,
    )

    assert result.status == "completed"
    assert result.counts.identified == 3
    assert result.counts.duplicates_removed == 1
    assert result.counts.screened == 2
    assert result.counts.included == 2  # el proveedor fake incluye todo
    assert result.hallucination_flagged is False

    # Entregables generados.
    deliverable = ctx.run_dir / "deliverable"
    assert (deliverable / "documento.md").exists()
    assert (deliverable / "prisma_flow.md").exists()
    assert (deliverable / "checklist_2020.md").exists()
    assert (deliverable / "checklist_traice.md").exists()

    # Manifiesto reproducible + ledger: 5 gates (screening_ta, screening_ft,
    # extraccion, rob, reporte).
    assert (ctx.run_dir / "manifest.yml").exists()
    assert len(ctx.ledger.read_all()) == 5
    # Etapas H3 presentes: full-text + riesgo de sesgo.
    assert (ctx.run_dir / "04_fulltext" / "decisions.json").exists()
    assert (ctx.run_dir / "07_rob" / "assessments.json").exists()
    assert (ctx.run_dir / "deliverable" / "risk_of_bias.md").exists()


def test_pipeline_pausa_sin_auto_approve(tmp_path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST2")
    result = run_pipeline(protocol, EXAMPLE, ctx, auto_approve=False, search_fn=_fake_search)
    # Sin auto-approve y sin decision.yml, el primer gate A1 pausa.
    assert result.status == "paused"
    assert (ctx.run_dir / "screening_ta" / "review_request.yml").exists()


def test_pipeline_ensemble_y_metricas(tmp_path) -> None:
    # El demo usa un ensemble de 2 miembros fake → 2 votos por registro.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST3")
    result = run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        auto_approve=True,
        search_fn=_fake_search,
        gold_labels={"rec-1": True, "rec-2": True},
    )
    assert result.status == "completed"

    # Métricas calculadas contra el gold standard (fake incluye todo → recall 1.0).
    assert result.metrics is not None
    assert result.metrics.n == 2
    assert result.metrics.recall == 1.0
    assert result.metrics.lost_evidence == 0.0
    assert (ctx.run_dir / "03_screening" / "metrics.json").exists()

    # Cada decisión lleva los 2 votos del ensemble.
    decisions = json.loads(
        (ctx.run_dir / "03_screening" / "decisions.json").read_text(encoding="utf-8")
    )
    assert len(decisions[0]["votes"]) == 2
