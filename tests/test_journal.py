"""Diario por etapa (Ola 1, D3; auditoría 2026-09-03, A9; spec 2026-10-04 §7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import ScriptedProvider

from revisia.agents.screening import ScreenerMember, screen_record
from revisia.orchestration.journal import JournalError, StageJournal, journaled
from revisia.orchestration.run_context import RunContext
from revisia.schemas.artifacts import JournalEntry, LLMCall
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision


def _entrada(record_id: str, *, salida: str = "include") -> JournalEntry:
    return JournalEntry(
        stage="screening_ta",
        record_id=record_id,
        input_sha256="in-1",
        output={"record_id": record_id, "ensemble_label": salida},
    )


def test_journal_recupera_ultima_linea_truncada(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    diario = StageJournal(ctx, "screening_ta")
    diario.append(_entrada("a"))
    diario.append(_entrada("b"))
    with diario.path.open("ab") as fh:  # caída a mitad de escribir la tercera línea
        fh.write(b'{"schema_version": 1, "stage": "screening_ta", "rec')

    recargado = StageJournal(ctx, "screening_ta")
    assert recargado.lookup("a", "in-1") is not None
    assert recargado.lookup("b", "in-1") is not None
    recargado.append(_entrada("c"))

    lineas = diario.path.read_text(encoding="utf-8").splitlines()
    assert [JournalEntry.model_validate_json(x).record_id for x in lineas] == ["a", "b", "c"]


def test_journal_linea_corrupta_intermedia_es_error(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    diario = StageJournal(ctx, "screening_ta")
    diario.append(_entrada("a"))
    with diario.path.open("ab") as fh:
        fh.write(b"esto no es json\n")
    diario.append(_entrada("b"))
    with pytest.raises(JournalError, match="línea 2 corrupta"):
        StageJournal(ctx, "screening_ta")


def test_journal_misma_clave_y_distinta_salida_es_error(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    diario = StageJournal(ctx, "screening_ta")
    diario.append(_entrada("a"))
    diario.append(_entrada("a", salida="exclude"))  # editado a mano: dos verdades
    with pytest.raises(JournalError, match="distinta salida"):
        StageJournal(ctx, "screening_ta")


def _cribado(proveedor: ScriptedProvider, criterios: str):
    """``compute`` de un cribado T/A de un solo miembro sobre el registro "a"."""
    miembro = ScreenerMember(provider=proveedor, model_name="fake:guion")
    registro = SearchRecord(record_id="a", title="Estudio a")
    return lambda: screen_record([miembro], question="¿X?", criteria=criterios, record=registro)


def _cribar(ctx: RunContext, proveedor: ScriptedProvider, criterios: str) -> ScreeningDecision:
    return journaled(
        StageJournal(ctx, "screening_ta"),
        record_id="a",
        inputs={"criteria": criterios},
        model=ScreeningDecision,
        compute=_cribado(proveedor, criterios),
        run_ctx=ctx,
        role_of=lambda i: f"member:{i}",
    )


def test_journal_entrada_obsoleta_por_input_sha_se_recalcula(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    proveedor = ScriptedProvider()
    primera = _cribar(ctx, proveedor, "c1")
    assert _cribar(ctx, proveedor, "c1") == primera  # del diario, sin llamar
    assert proveedor.calls == 1

    # Cambian los criterios: la entrada vieja queda obsoleta y se recalcula.
    _cribar(ctx, proveedor, "c2")
    assert proveedor.calls == 2
    lineas = StageJournal(ctx, "screening_ta").path.read_text("utf-8").splitlines()
    entradas = [JournalEntry.model_validate_json(x) for x in lineas]
    assert len(entradas) == 2  # la obsoleta sigue en el fichero: es válida
    assert entradas[0].input_sha256 != entradas[1].input_sha256

    # Cada meta del diario está, idéntica, en llm_calls.jsonl (spec §4.4, relación 12).
    lineas = ctx.llm_calls_path.read_text("utf-8").splitlines()
    llamadas = [LLMCall.model_validate_json(x) for x in lineas]
    assert [m for e in entradas for m in e.metas] == llamadas
    assert {(c.stage, c.record_id, c.role) for c in llamadas} == {("screening_ta", "a", "member:0")}


def test_journaled_registra_las_llamadas_antes_que_el_diario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = RunContext("demo", tmp_path, "T")

    def _caida(self, entry) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(StageJournal, "append", _caida)
    with pytest.raises(OSError):
        _cribar(ctx, ScriptedProvider(), "c1")
    # La llamada ya está en llm_calls.jsonl (huérfana, válida); el diario, vacío.
    assert len(ctx.llm_calls_path.read_text("utf-8").splitlines()) == 1
    assert not StageJournal(ctx, "screening_ta").path.exists()
