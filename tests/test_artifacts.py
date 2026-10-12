"""Contratos de artefactos de la Ola 1 (spec 2026-10-04 §4; PR-0)."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from revisia.config import STAGES
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.artifacts import (
    ARTIFACT_SCHEMA_VERSION,
    GATED_STAGES,
    JOURNAL_PATHS,
    TRANSIENT_FULLTEXT_REASONS,
    DedupReport,
    ExcludedReport,
    FulltextReason,
    GateAction,
    GateSummary,
    JournalEntry,
    JournalStage,
    LLMCall,
    LLMStage,
    QueryOrigin,
    ReasonSource,
    RetrievalOutcome,
    RunInfo,
    RunStatus,
    SearchEntryKind,
    SearchEntryStatus,
    SearchLog,
    SearchLogEntry,
)


def _meta() -> RunMeta:
    return RunMeta(
        provider="fake",
        model="fake-1",
        temperature=0.0,
        prompt_sha256=sha256_text("p"),
        response_sha256=sha256_text("r"),
        deterministic=True,
    )


def test_journal_paths_cubren_cada_etapa_con_diario() -> None:
    assert set(JOURNAL_PATHS) == set(get_args(JournalStage))
    rutas = list(JOURNAL_PATHS.values())
    assert len(set(rutas)) == len(rutas)
    assert all(r.endswith(".jsonl") and "\\" not in r for r in rutas)
    assert JOURNAL_PATHS["screening_ta"] == "03_screening/journal.jsonl"
    assert JOURNAL_PATHS["fulltext_retrieval"] == "04_fulltext/retrieval.jsonl"
    assert JOURNAL_PATHS["screening_ft"] == "04_fulltext/journal.jsonl"
    assert JOURNAL_PATHS["extraccion"] == "05_extraction/journal.jsonl"
    assert JOURNAL_PATHS["extraccion_2"] == "05_extraction/journal_2.jsonl"
    assert JOURNAL_PATHS["rob"] == "07_rob/journal.jsonl"
    assert JOURNAL_PATHS["sintesis"] == "06_synthesis/journal.jsonl"
    assert JOURNAL_PATHS["verificacion"] == "06_synthesis/verification.jsonl"


def test_etapas_llm_son_las_de_diario_menos_la_recuperacion() -> None:
    assert set(get_args(JournalStage)) - set(get_args(LLMStage)) == {"fulltext_retrieval"}


def test_gated_stages_en_orden_canonico() -> None:
    assert GATED_STAGES == ("screening_ta", "screening_ft", "extraccion", "rob", "reporte")
    posiciones = [STAGES.index(s) for s in GATED_STAGES]
    assert posiciones == sorted(posiciones)


# Miembros exactos de cada alias del contrato, escritos a mano desde la spec §4.3
# (no derivados del módulo): ampliar o quitar un miembro es un cambio de contrato
# y tiene que romper aquí, no en silencio aguas abajo (hallazgos Minor de A1-A3).
@pytest.mark.parametrize(
    ("alias", "esperado"),
    [
        pytest.param(
            RunStatus,
            ["running", "paused", "rejected", "completed", "interrupted"],
            id="RunStatus",
        ),
        pytest.param(
            LLMStage,
            [
                "screening_ta",
                "screening_ft",
                "extraccion",
                "extraccion_2",
                "rob",
                "sintesis",
                "verificacion",
            ],
            id="LLMStage",
        ),
        pytest.param(
            JournalStage,
            [
                "screening_ta",
                "fulltext_retrieval",
                "screening_ft",
                "extraccion",
                "extraccion_2",
                "rob",
                "sintesis",
                "verificacion",
            ],
            id="JournalStage",
        ),
        pytest.param(
            FulltextReason,
            ["sin_url_oa", "sin_httpx", "error_http", "texto_vacio", "no_disponible"],
            id="FulltextReason",
        ),
        pytest.param(
            SearchEntryKind, ["database", "manual_import", "injected"], id="SearchEntryKind"
        ),
        pytest.param(
            SearchEntryStatus, ["ok", "failed", "manual_only", "unknown"], id="SearchEntryStatus"
        ),
        pytest.param(QueryOrigin, ["file", "question_fallback"], id="QueryOrigin"),
        pytest.param(ReasonSource, ["human", "ai"], id="ReasonSource"),
        pytest.param(GateAction, ["approve", "reject", "auto-proceed"], id="GateAction"),
    ],
)
def test_literales_del_contrato(alias: object, esperado: list[str]) -> None:
    # `sorted` y no `set`: además de los miembros, descarta un miembro repetido.
    assert sorted(get_args(alias)) == sorted(esperado)


def test_motivos_transitorios_de_recuperacion_del_contrato() -> None:
    # Escrito a mano, como los literales: ampliarlo cambia qué informes se reintentan al
    # reanudar (A9) y qué avisa el gate de FT, y tiene que romper aquí. Y no puede nombrar
    # un motivo que `FulltextReason` no tenga (un typo lo dejaría sin efecto en silencio).
    assert isinstance(TRANSIENT_FULLTEXT_REASONS, frozenset)
    assert sorted(TRANSIENT_FULLTEXT_REASONS) == ["error_http", "sin_httpx"]
    assert set(TRANSIENT_FULLTEXT_REASONS) <= set(get_args(FulltextReason))


def test_llm_call_hereda_runmeta_y_etiqueta() -> None:
    call = LLMCall.from_meta(_meta(), stage="screening_ta", record_id="10.1/x", role="member:0")
    assert isinstance(call, RunMeta)
    assert (call.stage, call.record_id, call.role) == ("screening_ta", "10.1/x", "member:0")
    assert call.prompt_sha256 == _meta().prompt_sha256
    assert LLMCall.model_validate_json(call.model_dump_json()) == call
    with pytest.raises(ValidationError):
        LLMCall.from_meta(_meta(), stage="busqueda")


def test_journal_entry_ida_y_vuelta() -> None:
    entry = JournalEntry(
        stage="screening_ft",
        record_id="10.1/x",
        input_sha256=sha256_text("in"),
        output={"record_id": "10.1/x", "ensemble_label": "include"},
        metas=[LLMCall.from_meta(_meta(), stage="screening_ft", record_id="10.1/x")],
    )
    assert entry.schema_version == ARTIFACT_SCHEMA_VERSION == 1
    assert entry.timestamp_utc.endswith("+00:00")
    assert JournalEntry.model_validate_json(entry.model_dump_json()) == entry
    with pytest.raises(ValidationError):
        JournalEntry(stage="dedup", record_id="x", input_sha256="h", output={})


def test_run_info_por_defecto_corriendo_y_sin_correo() -> None:
    info = RunInfo(
        slug="demo",
        timestamp="20261004-120000",
        started_utc="2026-10-04T12:00:00+00:00",
        engine_version="0.7.0",
        python_version="3.13.0",
        max_results=50,
        mailto_set=False,
    )
    assert info.status == "running"
    assert info.resumes == [] and info.interruptions == []
    assert "mailto" not in info.model_dump()
    with pytest.raises(ValidationError):
        RunInfo.model_validate({**info.model_dump(), "status": "pausada"})


def test_search_log_entrada_minima_y_tipos() -> None:
    entry = SearchLogEntry(
        database="Europe PMC",
        db_key="europepmc",
        kind="database",
        declared=True,
        backend="europepmc_search",
        status="ok",
        query="llm screening",
        query_origin="file",
        query_file="00_protocol/search_strings/europepmc.txt",
        query_sha256=sha256_text("llm screening"),
        max_results=50,
        n_returned=3,
        source_db=["EuropePMC"],
    )
    log = SearchLog(
        started_utc="2026-10-04T12:00:00+00:00",
        finished_utc="2026-10-04T12:00:05+00:00",
        max_results=50,
        mailto_set=True,
        entries=[entry],
    )
    assert SearchLog.model_validate_json(log.model_dump_json()) == log
    with pytest.raises(ValidationError):
        SearchLogEntry(database="x", db_key="x", kind="database", declared=True, status="caida")


def test_dedup_report_con_duplicados_y_renombrados() -> None:
    report = DedupReport.model_validate(
        {
            "n_in": 3,
            "n_out": 2,
            "duplicates": [
                {"record_id": "b", "source_db": "Crossref", "kept_record_id": "a", "key": "doi:1"}
            ],
            "renamed": [{"from_id": "c", "to_id": "c#2"}],
        }
    )
    assert report.duplicates[0].kept_record_id == "a"
    assert report.renamed[0].to_id == "c#2"


def test_retrieval_outcome_motivo_solo_si_no_se_recupera() -> None:
    ok = RetrievalOutcome(available=True, source_url="https://x", n_chars=10)
    assert ok.reason is None
    fallo = RetrievalOutcome(available=False, reason="sin_url_oa")
    assert fallo.n_chars == 0
    with pytest.raises(ValidationError, match="necesita un motivo"):
        RetrievalOutcome(available=False)
    with pytest.raises(ValidationError, match="no lleva motivo"):
        RetrievalOutcome(available=True, reason="error_http")


def test_excluded_report_exige_origen_de_la_razon() -> None:
    rep = ExcludedReport(record_id="a", title="T", reason="población", reason_source="ai")
    assert rep.year is None and rep.doi is None
    with pytest.raises(ValidationError):
        ExcludedReport(record_id="a", title="T", reason="x", reason_source="agente")


def test_gate_summary_acciones_validas() -> None:
    summary = GateSummary(
        stage="reporte",
        action="approve",
        actor="human:revisora",
        autonomy="A1",
        timestamp_utc="2026-10-04T12:00:00+00:00",
    )
    assert (summary.n_labels, summary.n_flag_reviews, summary.forced_human) == (0, 0, False)
    with pytest.raises(ValidationError):
        GateSummary(stage="reporte", action="label", actor="h", autonomy="A1", timestamp_utc="t")
