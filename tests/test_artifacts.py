"""Contratos de artefactos de la Ola 1 (spec 2026-10-04 §4; PR-0)."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from revisia.config import STAGES
from revisia.provenance.runmeta import RUNMETA_SCHEMA_VERSION, RunMeta, sha256_text
from revisia.schemas.artifacts import (
    ARTIFACT_SCHEMA_VERSION,
    DEPOSIT_FILE,
    ENVIRONMENT_PACKAGES,
    GATED_STAGES,
    JOURNAL_PATHS,
    TRANSIENT_FULLTEXT_REASONS,
    WITHHELD_DIRS,
    DedupReport,
    DepositInfo,
    DepositSource,
    Environment,
    ExcludedReport,
    FulltextReason,
    FulltextSource,
    GateAction,
    GateSummary,
    GroundingMode,
    JournalEntry,
    JournalStage,
    LLMCall,
    LLMStage,
    QueryOrigin,
    QuoteStatus,
    ReasonSource,
    RetrievalOutcome,
    RunInfo,
    RunKind,
    RunStatus,
    SearchEntryKind,
    SearchEntryStatus,
    SearchLog,
    SearchLogEntry,
    WithheldDir,
    WithheldFile,
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
    assert entry.schema_version == ARTIFACT_SCHEMA_VERSION == 2
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


# ── Ola 2 · contratos v2 (spec 2026-10-18 §4.1, §4.2; D12, D17, D20, D21, D23) ──


def test_schema_version_sube_a_2_y_coincide_con_runmeta() -> None:
    assert ARTIFACT_SCHEMA_VERSION == RUNMETA_SCHEMA_VERSION == 2
    assert set(get_args(RunKind)) == {"review", "benchmark"}
    assert set(get_args(QuoteStatus)) == {"exact", "normalized", "not_found", "none"}
    assert set(get_args(GroundingMode)) == {"existence", "judge", "embedder"}
    assert set(get_args(FulltextSource)) == {"oa", "human_rescue"}
    assert len(ENVIRONMENT_PACKAGES) == 13 and len(set(ENVIRONMENT_PACKAGES)) == 13


def test_run_info_v1_valida_y_es_review_sin_entorno() -> None:
    v1 = {
        "schema_version": 1,
        "slug": "s",
        "timestamp": "T",
        "started_utc": "2026-10-01T00:00:00+00:00",
        "engine_version": "0.8.0",
        "python_version": "3.13.0",
        "max_results": 5,
        "mailto_set": False,
    }
    info = RunInfo.model_validate(v1)
    assert (info.kind, info.environment) == ("review", None)
    assert RunInfo.model_validate({**v1, "kind": "benchmark"}).kind == "benchmark"
    with pytest.raises(ValidationError):
        RunInfo.model_validate({**v1, "kind": "piloto"})


def test_environment_minimo_y_con_plantillas() -> None:
    env = Environment(
        engine_version="0.9.0",
        python_version="3.13.0",
        python_implementation="CPython",
        platform="Windows-11",
        created_utc="2026-10-18T00:00:00+00:00",
        prompt_templates={"extraccion/v2.md": "a" * 64, "rob/RoB2.yml": "b" * 64},
    )
    assert (env.git_commit, env.git_dirty, env.packages) == (None, None, {})
    assert Environment.model_validate(env.model_dump()) == env


def _entrada_v1() -> dict:
    return {
        "schema_version": 1,
        "stage": "screening_ta",
        "record_id": "r",
        "input_sha256": "i" * 64,
        "output": {"record_id": "r"},
    }


def test_journal_entry_v1_es_ok_y_la_failed_exige_output_nulo_y_error() -> None:
    assert JournalEntry.model_validate(_entrada_v1()).status == "ok"
    fallo = {"type": "DeterministicCallError", "message": "400", "attempts": 3}
    failed = JournalEntry.model_validate(
        {**_entrada_v1(), "output": None, "error": fallo, "status": "failed"}
    )
    assert failed.error is not None and failed.error.attempts == 3
    for incoherente in (
        {**_entrada_v1(), "status": "failed"},  # failed con output
        {**_entrada_v1(), "output": None},  # ok sin output
        {**_entrada_v1(), "error": fallo},  # ok con error
        {**_entrada_v1(), "output": None, "status": "failed"},  # failed sin error
    ):
        with pytest.raises(ValidationError):
            JournalEntry.model_validate(incoherente)
    with pytest.raises(ValidationError):
        JournalEntry.model_validate({k: v for k, v in _entrada_v1().items() if k != "output"})


def test_retrieval_outcome_v2_rescate_humano_y_recorte() -> None:
    oa = RetrievalOutcome(available=True, n_chars=10, text_sha256="t")
    assert (oa.source, oa.truncated, oa.n_chars_total, oa.rescue_file) == ("oa", False, None, None)
    rescate = RetrievalOutcome(
        available=True,
        n_chars=10,
        source="human_rescue",
        rescue_file="screening_ft/rescues/a.pdf",
        rescue_file_sha256="f" * 64,
    )
    assert rescate.source == "human_rescue"
    with pytest.raises(ValidationError):  # rescate sin fichero
        RetrievalOutcome(available=True, source="human_rescue")
    with pytest.raises(ValidationError):  # fichero sin ser rescate
        RetrievalOutcome(available=True, rescue_file="screening_ft/rescues/a.pdf")
    with pytest.raises(ValidationError):  # hash suelto en un texto de acceso abierto
        RetrievalOutcome(available=True, source="oa", rescue_file_sha256="f" * 64)
    with pytest.raises(ValidationError):  # rescate con fichero y sin hash
        RetrievalOutcome(
            available=True, source="human_rescue", rescue_file="screening_ft/rescues/a.pdf"
        )
    with pytest.raises(ValidationError):  # rescate con hash y sin fichero
        RetrievalOutcome(available=True, source="human_rescue", rescue_file_sha256="f" * 64)

    recortado = RetrievalOutcome(
        available=True, n_chars=120_000, n_chars_total=150_000, truncated=True
    )
    assert recortado.truncated
    with pytest.raises(ValidationError):  # truncated sin total
        RetrievalOutcome(available=True, n_chars=10, truncated=True)
    with pytest.raises(ValidationError):  # total no mayor que lo guardado
        RetrievalOutcome(available=True, n_chars=10, n_chars_total=10, truncated=True)


def test_gate_summary_n_edits_vale_cero_por_defecto() -> None:
    resumen = GateSummary(
        stage="extraccion", action="approve", actor="human:ana", autonomy="A0", timestamp_utc="t"
    )
    assert resumen.n_edits == 0


def test_deposit_info_lista_lo_retenido_con_sus_hashes() -> None:
    info = DepositInfo(
        source_run=DepositSource(slug="s", timestamp="T", manifest_sha256="m" * 64),
        withheld=[
            WithheldDir(
                path="04_fulltext/texts/",
                reason="copyright",
                files=[
                    WithheldFile(relpath="04_fulltext/texts/0001.txt", sha256="a" * 64, n_bytes=12)
                ],
            )
        ],
        engine_version="0.9.0",
    )
    assert info.schema_version == 2 and info.created_utc
    assert WITHHELD_DIRS == ("04_fulltext/texts/", "screening_ft/rescues/")
    assert DEPOSIT_FILE == "deposit.json"
    with pytest.raises(ValidationError):
        WithheldDir(path="x/", reason="porque sí")
