"""Reanudación de corridas: estado en run.json, interrupciones y entrypoints (Ola 1,
D3 y D14; auditoría 2026-09-03, A9; spec 2026-10-04 §7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import ScriptedProvider, fetch_disponible

from revisia.agent_driver import run_review_with_agent
from revisia.config import load_protocol
from revisia.llm.preflight import PreflightError
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.flow import resume_review
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext, RunInterrupted
from revisia.orchestration.snapshot import read_run_info
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _busqueda(query: str, n: int) -> list[SearchRecord]:
    return [
        SearchRecord(
            record_id="rec-1",
            title="LLM screening for systematic reviews",
            abstract="We evaluate LLM screening.",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-2",
            title="Active learning with ASReview",
            abstract="Active learning reduces workload.",
            source_db="OpenAlex",
        ),
    ][:n]


def test_resume_toma_el_slug_de_run_json(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)  # el demo no declara `slug`
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda).status == "paused"

    result = resume_review(ctx.run_dir)

    assert (result.status, result.stage, result.run_dir) == ("paused", "screening_ta", ctx.run_dir)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo-mini-review-T"]
    info = read_run_info(ctx.run_dir)
    assert info.slug == "demo-mini-review"
    assert len(info.resumes) == 1


def test_estado_de_la_corrida_en_run_json(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("paused", "screening_ta")

    run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=_busqueda, fetch_fn=fetch_disponible
    )
    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("completed", None)


def test_interrupcion_queda_en_run_json_y_se_relanza(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proveedor = ScriptedProvider(fail_at=1)
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    with pytest.raises(RunInterrupted) as exc:
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)

    assert exc.value.stage == "screening_ta"
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert f"revisia run --resume {ctx.run_dir}" in str(exc.value)
    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("interrupted", "screening_ta")
    (interrupcion,) = info.interruptions
    assert interrupcion.stage == "screening_ta"
    assert interrupcion.error == "RuntimeError: 429 Too Many Requests"


def test_preflight_al_empezar_no_crea_nada(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    sin_proveedor = protocol.model_copy(update={"llm": {}, "ensemble_llm": {}})
    ctx = RunContext(protocol.slug, tmp_path, "T")
    with pytest.raises(PreflightError, match="screening_ft"):
        run_pipeline(sin_proveedor, EXAMPLE, ctx, search_fn=_busqueda)
    assert list(ctx.run_dir.iterdir()) == []  # ni run.json ni instantánea


def test_agent_driver_reanuda_con_run_dir(tmp_path: Path) -> None:
    def callback(req, schema):  # el demo usa `fake`: el callback no se llega a usar
        raise AssertionError("no debería llamarse")

    pausa = run_review_with_agent(
        EXAMPLE,
        callback,
        timestamp="T",
        runs_root=tmp_path,
        auto_approve=False,
        search_fn=_busqueda,
    )
    assert pausa.status == "paused"
    completa = run_review_with_agent(
        None, callback, run_dir=pausa.run_dir, auto_approve=True, fetch_fn=fetch_disponible
    )
    assert (completa.status, completa.run_dir) == ("completed", pausa.run_dir)
