"""Diario por etapa (Ola 1, D3; auditoría 2026-09-03, A9; spec 2026-10-04 §7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from revisia.orchestration.journal import JournalError, StageJournal
from revisia.orchestration.run_context import RunContext
from revisia.schemas.artifacts import JournalEntry


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
