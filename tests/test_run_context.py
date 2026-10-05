"""RunContext de la Ola 1: llamadas a disco al registrarlas, JSON atómico y carpeta
nueva de verdad (auditoría 2026-09-03, A9; spec 2026-10-04 §7)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from revisia.orchestration.run_context import (
    RunContext,
    RunDirExistsError,
    RunInterrupted,
    resume_command,
)
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.artifacts import LLMCall


def _meta(model: str = "fake-1") -> RunMeta:
    return RunMeta(
        provider="fake",
        model=model,
        temperature=0.0,
        prompt_sha256=sha256_text("p"),
        response_sha256=sha256_text("r"),
        deterministic=True,
    )


def test_run_context_vuelca_llm_calls_al_registrar(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    call = ctx.record_meta(_meta(), stage="screening_ta", record_id="10.1/x", role="member:0")

    # En disco al volver, sin esperar al manifiesto (antes se perdían con un 429).
    lineas = ctx.llm_calls_path.read_text(encoding="utf-8").splitlines()
    assert [LLMCall.model_validate_json(x) for x in lineas] == [call]
    assert (call.stage, call.record_id, call.role) == ("screening_ta", "10.1/x", "member:0")
    assert ctx.metas == [call]

    # El manifiesto toma las llamadas del fichero: también las de otra invocación.
    otra = LLMCall.from_meta(_meta("fake-2"), stage="sintesis", record_id="sintesis")
    with ctx.llm_calls_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(otra.model_dump_json() + "\n")
    manifest = yaml.safe_load(
        ctx.write_manifest(protocol_snapshot={}, counts={}).read_text(encoding="utf-8")
    )
    assert [c["model"] for c in manifest["llm_calls"]] == ["fake-1", "fake-2"]
    assert manifest["models_used"] == ["fake:fake-1", "fake:fake-2"]
    assert manifest["final_gate"] == {"forced_human": False, "reason": None}
    assert not list(tmp_path.rglob("*.tmp"))  # escritura atómica, sin restos


def test_run_context_nuevo_no_reutiliza_carpeta_existente(tmp_path: Path) -> None:
    RunContext("demo", tmp_path, "T").write_json("03_screening/decisions.json", [])
    with pytest.raises(RunDirExistsError, match="--resume"):
        RunContext("demo", tmp_path, "T")
    # Una carpeta vacía (creada a mano antes de correr) sí se puede usar.
    (tmp_path / "demo-VACIA").mkdir()
    assert RunContext("demo", tmp_path, "VACIA").run_dir == tmp_path / "demo-VACIA"


def test_run_interrupted_dice_como_reanudar(tmp_path: Path) -> None:
    exc = RunInterrupted(tmp_path / "demo-T", "screening_ta", "RuntimeError: 429")
    assert (exc.stage, exc.error) == ("screening_ta", "RuntimeError: 429")
    assert f"revisia run --resume {tmp_path / 'demo-T'}" in str(exc)


def test_resume_command_entrecomilla_la_ruta_solo_si_tiene_espacios(tmp_path: Path) -> None:
    # Sin comillas, el shell parte `runs/mi revisión-T` en dos argumentos y el comando falla.
    sin_espacios = tmp_path / "demo-T"
    con_espacios = tmp_path / "mis corridas" / "demo-T"

    assert resume_command(sin_espacios) == f"revisia run --resume {sin_espacios}"
    assert resume_command(con_espacios) == f'revisia run --resume "{con_espacios}"'
    assert resume_command(str(con_espacios)) == resume_command(con_espacios)
    # Lo usan también los mensajes de una interrupción.
    exc = RunInterrupted(con_espacios, "rob", "RuntimeError: 429")
    assert f'Reanuda con: revisia run --resume "{con_espacios}"' in str(exc)
