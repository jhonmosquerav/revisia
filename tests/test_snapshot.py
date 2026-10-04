"""Instantánea del protocolo y run.json (Ola 1, D3 y D13; spec 2026-10-04 §7)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from fakes import fetch_disponible

from revisia import __version__
from revisia.config import load_protocol
from revisia.orchestration import snapshot as snapshot_mod
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import LegacyRunError, RunContext
from revisia.orchestration.snapshot import (
    ProtocolMismatchError,
    prompt_fingerprint,
    protocol_fingerprint,
)
from revisia.schemas.artifacts import RunInfo
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _busqueda(query: str, n: int) -> list[SearchRecord]:
    return [
        SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex"),
        SearchRecord(record_id="rec-2", title="Active learning", source_db="OpenAlex"),
    ][:n]


def _run_info(ctx: RunContext) -> RunInfo:
    return RunInfo.model_validate_json((ctx.run_dir / "run.json").read_text(encoding="utf-8"))


def test_snapshot_y_run_json(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        max_results=10,
        auto_approve=True,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
    )

    instantanea = ctx.run_dir / "00_protocol"
    copiados = sorted(p.relative_to(instantanea).as_posix() for p in instantanea.rglob("*.*"))
    assert copiados == [
        "effects.yml",
        "extraction_form.yml",
        "inclusion_exclusion.yml",
        "protocol.yml",
        "search_strings/openalex.txt",
    ]
    info = _run_info(ctx)
    assert (info.slug, info.timestamp, info.max_results, info.mailto_set) == (
        "demo-mini-review",
        "T",
        10,
        False,
    )
    assert info.engine_version == __version__
    assert info.protocol_sha256 == protocol_fingerprint(EXAMPLE)
    assert info.protocol_sha256 == protocol_fingerprint(instantanea)
    assert set(info.prompt_sha256) == {
        "extraccion/v1.md",
        "reporte/v1.md",
        "rob/v1.md",
        "screening/v1.md",
        "screening_ft/v1.md",
    }
    assert info.resumes == []
    assert "mailto" not in json.loads((ctx.run_dir / "run.json").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["run"]["started_utc"] == info.started_utc
    assert manifest["run"]["engine_version"] == __version__


def test_huella_del_protocolo_ignora_crlf(tmp_path: Path) -> None:
    copia = tmp_path / "proto"
    shutil.copytree(EXAMPLE, copia)
    for path in [copia / "protocol.yml", copia / "search_strings" / "openalex.txt"]:
        texto = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        path.write_bytes(texto.replace("\n", "\r\n").encode("utf-8"))
    assert protocol_fingerprint(copia) == protocol_fingerprint(EXAMPLE)


def test_resume_con_prompt_modificado_falla(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda).status == "paused"

    prompts = tmp_path / "prompts"
    shutil.copytree(snapshot_mod.PROMPTS_DIR, prompts, ignore=shutil.ignore_patterns("*.py*"))
    cribado = prompts / "screening" / "v1.md"
    cribado.write_text(cribado.read_text(encoding="utf-8") + "\nNueva regla.\n", encoding="utf-8")
    monkeypatch.setattr(snapshot_mod, "PROMPTS_DIR", prompts)
    assert prompt_fingerprint() != _run_info(ctx).prompt_sha256

    with pytest.raises(ProtocolMismatchError, match="revisia/prompts/screening/v1.md") as exc:
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    assert exc.value.files == ["revisia/prompts/screening/v1.md"]


def test_resume_con_instantanea_alterada_falla(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    criterios = ctx.run_dir / "00_protocol" / "inclusion_exclusion.yml"
    criterios.write_text(criterios.read_text(encoding="utf-8") + "\n# editado\n", "utf-8")
    with pytest.raises(ProtocolMismatchError, match="00_protocol/inclusion_exclusion.yml"):
        run_pipeline(protocol, None, ctx, search_fn=_busqueda)


def test_run_context_open_y_slug_por_defecto(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)  # el demo no declara slug: sale de la carpeta
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)

    reabierto = RunContext.open(ctx.run_dir)
    assert (reabierto.slug, reabierto.timestamp, reabierto.run_dir) == (
        "demo-mini-review",
        "T",
        ctx.run_dir,
    )
    instantanea = ctx.run_dir / "00_protocol"
    assert load_protocol(instantanea).slug == "00_protocol"  # hallazgo 4 del spec (§2)
    assert load_protocol(instantanea, default_slug=reabierto.slug).slug == "demo-mini-review"

    antigua = tmp_path / "demo-v07"
    (antigua / "03_screening").mkdir(parents=True)
    with pytest.raises(LegacyRunError, match="anterior a la Ola 1"):
        RunContext.open(antigua)
