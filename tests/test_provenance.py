"""Tests de la capa de procedencia: RunMeta y ledger."""

from __future__ import annotations

from revisia.provenance import DecisionEntry, DecisionLedger, RunMeta, sha256_text


def test_sha256_text_es_determinista() -> None:
    assert sha256_text("hola") == sha256_text("hola")
    assert sha256_text("hola") != sha256_text("adiós")
    assert len(sha256_text("x")) == 64


def test_runmeta_serializa_redondo() -> None:
    meta = RunMeta(
        provider="gemini",
        model="gemini-2.0-flash",
        temperature=0.0,
        prompt_sha256=sha256_text("p"),
        response_sha256=sha256_text("r"),
    )
    dumped = meta.model_dump()
    assert dumped["provider"] == "gemini"
    assert dumped["deterministic"] is False
    assert RunMeta.model_validate(dumped) == meta


def test_ledger_append_y_lectura(tmp_path) -> None:
    ledger = DecisionLedger(tmp_path / "decisions.jsonl")
    ledger.append(
        DecisionEntry(
            stage="screening_ta",
            actor="agent:screener",
            autonomy="A1",
            action="include",
            target="rec-1",
        )
    )
    ledger.append(
        DecisionEntry(
            stage="screening_ta",
            actor="human:jhon",
            autonomy="A1",
            action="approve",
            target="rec-1",
        )
    )
    entries = ledger.read_all()
    assert len(entries) == 2
    assert entries[0].action == "include"
    assert entries[1].actor == "human:jhon"


def test_ledger_vacio_devuelve_lista_vacia(tmp_path) -> None:
    assert DecisionLedger(tmp_path / "noexiste.jsonl").read_all() == []
