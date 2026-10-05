"""Pipeline del tracer bullet (recorrido por etapas, Python puro y testeable).

Encadena los agentes con un checkpoint humano tras el screening y otro antes de
finalizar el reporte, corriendo el verificador anti-alucinación sobre la
síntesis. Es ``orchestration/flow.py`` (Prefect) quien lo envuelve para una
corrida "de producción"; aquí vive la lógica, sin dependencias pesadas, para
poder testearla offline con el proveedor ``fake``.

Estructura (Ola 1, spec 2026-10-04 §7): ``run_pipeline`` solo encadena; cada
etapa vive en su función (``_search``, ``_dedup``, ``_screen_ta``,
``_fulltext``, ``_extract``, ``_assess_rob``, ``_synthesize_and_verify``,
``_build_counts``, ``_write_deliverables``) y comparte el estado de la
invocación en un ``_Run``, cuyos ``gate``/``stop`` sustituyen los cinco bloques
de checkpoint casi iguales de antes. Es la base de la reanudación por diario.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import yaml
from pydantic import BaseModel

from revisia.agents import _http
from revisia.agents import dedup as dedup_agent
from revisia.agents import extraccion as extraccion_agent
from revisia.agents import fulltext as fulltext_agent
from revisia.agents import reporte as reporte_agent
from revisia.agents import rob as rob_agent
from revisia.agents import screening as screening_agent
from revisia.agents import screening_ft as screening_ft_agent
from revisia.agents import verificador as verificador_agent
from revisia.config import ReviewProtocol
from revisia.exclusions import ExclusionBreakdown, compute_exclusion_breakdown, compute_ft_excluded
from revisia.exports import (
    PrismaCounts,
    render_bibtex,
    render_excluded_reports,
    render_extraction_table,
    render_flow_diagram,
    render_flow_markdown,
    render_forest_markdown,
    render_forest_png,
    render_funnel_png,
    render_metafor_csv,
    render_methods,
    render_prisma2020_flow_csv,
    render_prisma_2020_checklist,
    render_prisma_abstracts_checklist,
    render_prisma_s_checklist,
    render_robvis_csv,
    render_traice_checklist,
)
from revisia.extraction_agreement import (
    ExtractionAgreement,
    compute_extraction_agreement,
    select_double_extraction_subset,
)
from revisia.llm.base import LLMProvider
from revisia.llm.preflight import PreflightError, preflight
from revisia.llm.registry import ProviderConfig, build_provider
from revisia.meta_analysis import MetaAnalysisResult, meta_analyze
from revisia.metrics import ScreeningMetrics, compute_screening_metrics
from revisia.orchestration.gates import apply_labels, ta_payload, ta_policy
from revisia.orchestration.hitl import (
    DecisionFileError,
    FlagPolicy,
    GateResult,
    RecordPolicy,
    review_gate,
)
from revisia.orchestration.journal import JournalError, StageJournal, entry_output, journaled
from revisia.orchestration.run_context import (
    LegacyRunError,
    RunContext,
    RunDirExistsError,
    RunInterrupted,
)
from revisia.orchestration.search_stage import (
    SEARCH_DIR,
    multi_database_search,
    read_search_log,
    run_search,
)
from revisia.orchestration.snapshot import (
    SEARCH_STRINGS_DIR,
    SNAPSHOT_DIR,
    ProtocolMismatchError,
    ensure_snapshot,
    read_run_info,
    write_run_info,
)
from revisia.provenance.runmeta import RunMeta, canonical_sha256, sha256_text, utc_now_iso
from revisia.rag.embed import Embedder, HashEmbedder
from revisia.schemas.artifacts import (
    GATED_STAGES,
    DedupReport,
    ExcludedReport,
    JournalEntry,
    RetrievalOutcome,
    RunInterruption,
    RunStatus,
)
from revisia.schemas.effects import EffectInput
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.records import SearchRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision
from revisia.schemas.verification import VerificationReport

SearchFn = Callable[[str, int], list[SearchRecord]]
FetchFn = Callable[[SearchRecord], fulltext_agent.FullText]

# Errores de configuración o de entrada humana: se relanzan tal cual (rc 2 en el
# CLI) y no cuentan como interrupción. Cualquier otro error a mitad de corrida
# queda en run.json y se relanza como RunInterrupted (rc 3, D14).
_CONFIG_ERRORS: tuple[type[BaseException], ...] = (
    PreflightError,
    ProtocolMismatchError,
    JournalError,
    DecisionFileError,
    LegacyRunError,
    RunDirExistsError,
)

# Tope del error que se guarda en `run.json.interruptions` (y en RunInterrupted): un
# cuerpo HTTP entero no debe volver run.json ilegible.
_MAX_ERROR_CHARS = 1000


@dataclass(slots=True)
class PipelineResult:
    status: str  # "completed" | "paused" | "rejected"
    message: str
    counts: PrismaCounts = field(default_factory=PrismaCounts)
    included: list[SearchRecord] = field(default_factory=list)
    narrative: str | None = None
    hallucination_flagged: bool = False
    metrics: ScreeningMetrics | None = None
    run_dir: Path | None = None
    # Gate en el que se detuvo la corrida (pausa o rechazo); None si se completó.
    stage: str | None = None


def _criteria_to_text(ie: dict) -> str:
    criteria = ie.get("criteria", ie)
    lines: list[str] = []
    for dim, spec in criteria.items():
        if isinstance(spec, dict):
            inc = spec.get("inclusion", "")
            exc = spec.get("exclusion", "")
            lines.append(f"- {dim}: incluir={inc!r}; excluir={exc!r}")
        else:
            lines.append(f"- {dim}: {spec}")
    return "\n".join(lines)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _multi_database_search(
    protocol: ReviewProtocol,
    protocol_dir: Path,
    question_text: str,
    max_results: int,
    mailto: str | None,
) -> tuple[list[SearchRecord], list[dict[str, str]]]:
    """Envoltorio de compatibilidad sobre ``search_stage.multi_database_search``.

    Conserva la firma y la tupla ``(registros, fallos)`` de antes de la Ola 1
    (la usan los tests de búsqueda multi-base). Lee las cadenas de
    ``<protocol_dir>/search_strings/`` y los RIS/BibTeX de ``imported/``; los
    fallos van redactados y una base sin backend no es un fallo (va por
    ``imported/``).
    """
    records, entries = multi_database_search(
        protocol,
        strings_dir=protocol_dir / "search_strings",
        imported_dir=protocol_dir / "imported",
        question=question_text,
        max_results=max_results,
        mailto=mailto,
    )
    failures = [{"db": e.database, "error": e.error or ""} for e in entries if e.status == "failed"]
    return records, failures


def _rob_table_md(tool: str, assessments: dict[str, RoBAssessment]) -> str:
    """Tabla Markdown de riesgo de sesgo (un estudio por fila + juicio global)."""
    lines = [f"# Riesgo de sesgo · {tool}", ""]
    if not assessments:
        lines.append("_(sin estudios evaluados)_")
        return "\n".join(lines)
    lines += ["| Estudio | Juicio global | Dominios |", "|---|---|---|"]
    for study_id, a in assessments.items():
        domains = "; ".join(f"{d.domain}={d.judgment}" for d in a.domains)
        lines.append(f"| {study_id} | {a.overall} | {domains} |")
    return "\n".join(lines)


@dataclass(slots=True)
class _Run:
    """Estado compartido de una invocación de ``run_pipeline``.

    Las funciones por etapa lo reciben en vez de una docena de argumentos.
    ``gate`` aplica el checkpoint de una etapa con la autonomía del protocolo y
    ``stop`` traduce un gate no aprobado en el ``PipelineResult`` con el que la
    corrida se detiene (antes, cinco bloques casi iguales). ``snapshot_dir`` es
    ``00_protocol/``, la única fuente de criterios, formulario, efectos, gold y
    cadenas; ``source_dir`` es el protocolo original (``None`` al reanudar sin
    él).
    """

    protocol: ReviewProtocol
    snapshot_dir: Path
    source_dir: Path | None
    ctx: RunContext
    question: str
    criteria: str
    form_fields: list[dict]
    auto_approve: bool
    mailto: str | None
    metrics: ScreeningMetrics | None = None
    # Etapa en curso (la que queda en run.json si la corrida se interrumpe).
    stage: str | None = None
    # `status`/`stage` de run.json antes de esta invocación (`None`: corrida nueva).
    previous: tuple[RunStatus, str | None] | None = None

    def finish(self, status: RunStatus, stage: str | None) -> None:
        """Deja en ``run.json`` cómo termina esta invocación (spec §4.3)."""
        info = read_run_info(self.ctx.run_dir)
        if info is not None:
            write_run_info(
                self.ctx.run_dir, info.model_copy(update={"status": status, "stage": stage})
            )

    def interrupted(self, error: str) -> None:
        """Registra una interrupción en ``run.json`` (estado ``interrupted``, D14).

        Es contabilidad en el camino de error: si falla (``run.json`` bloqueado
        en Windows, disco lleno), se ignora para que la excepción original
        —un 429, un Ctrl+C— llegue intacta al CLI y no la tape un
        ``PermissionError`` (revisión de B8, I1).
        """
        with contextlib.suppress(Exception):
            info = read_run_info(self.ctx.run_dir)
            if info is None:
                return
            interruption = RunInterruption(utc=utc_now_iso(), stage=self.stage, error=error)
            write_run_info(
                self.ctx.run_dir,
                info.model_copy(
                    update={
                        "interruptions": [*info.interruptions, interruption],
                        "status": "interrupted",
                        "stage": self.stage,
                    }
                ),
            )

    def config_error(self) -> None:
        """Deshace el ``running`` de ``ensure_snapshot`` tras un error de configuración.

        Un ``decision.yml`` mal escrito o un diario corrupto no son una caída: el
        usuario lo corrige y reanuda. Si la corrida ya existía, ``run.json``
        recupera el ``status``/``stage`` con que llegó (p. ej. ``paused`` en
        ``screening_ta``) en vez de quedarse en ``running``; si era nueva, queda
        ``interrupted`` en la etapa en curso. En ambos casos sin entrada en
        ``interruptions``. La entrada de ``resumes`` que añadió ``ensure_snapshot`` se
        conserva: registra el intento de reanudar, aunque no llegara a ejecutar nada.
        Best-effort, como ``interrupted`` (revisión de B8, I2).
        """
        with contextlib.suppress(Exception):
            info = read_run_info(self.ctx.run_dir)
            if info is None:
                return
            status, stage = self.previous or ("interrupted", self.stage)
            write_run_info(
                self.ctx.run_dir, info.model_copy(update={"status": status, "stage": stage})
            )

    def gate(
        self,
        stage: str,
        payload: dict,
        *,
        records: RecordPolicy | None = None,
        flags: FlagPolicy | None = None,
        force_human: bool = False,
    ) -> GateResult:
        """Checkpoint humano de ``stage`` con la autonomía que fija el protocolo.

        ``records`` habilita la decisión por registro (cribado), ``flags`` la
        adjudicación de citas marcadas y ``force_human`` exige humano (M5).
        """
        self.stage = stage
        return review_gate(
            stage=stage,
            autonomy=self.protocol.autonomy_for(stage),
            run_ctx=self.ctx,
            review_payload=payload,
            auto_approve=self.auto_approve,
            records=records,
            flags=flags,
            force_human=force_human,
        )

    def stop(self, gate: GateResult, stage: str) -> PipelineResult | None:
        """``None`` si el gate aprobó; si no, el resultado con el que se detiene."""
        if gate.status == "approved":
            return None
        self.finish(gate.status, stage)
        return PipelineResult(
            gate.status, gate.message, metrics=self.metrics, run_dir=self.ctx.run_dir, stage=stage
        )


@dataclass(slots=True)
class _FullTextStage:
    """Resultado de la recuperación y el cribado a texto completo."""

    decisions: list[ScreeningDecision]
    texts: dict[str, str]
    not_retrieved: int


def _search(run: _Run, *, max_results: int, search_fn: SearchFn | None) -> list[SearchRecord]:
    """Búsqueda multi-base (A2), congelada en ``01_search/`` (M12).

    ``search_fn`` inyectado (tests) tiene prioridad y conserva el contrato de
    una sola llamada; en producción se busca en todas las bases declaradas con
    las cadenas de ``00_protocol/search_strings/``. Si la búsqueda ya terminó
    (existe ``01_search/log.json``), se carga sin repetirla.
    """
    return run_search(
        run.protocol,
        source_dir=run.source_dir,
        strings_dir=run.snapshot_dir / SEARCH_STRINGS_DIR,
        question=run.question,
        max_results=max_results,
        mailto=run.mailto,
        search_fn=search_fn,
        run_ctx=run.ctx,
    )


def _dedup(run: _Run, raw_records: list[SearchRecord]) -> tuple[list[SearchRecord], int]:
    """Deduplicación determinista (A2), congelada en ``02_dedup/``.

    ``records.json`` se escribe antes que ``dedup.json``, la marca de etapa
    completa: al reanudar se cargan ambos sin recalcular.
    """
    dedup_dir = run.ctx.run_dir / "02_dedup"
    if (dedup_dir / "dedup.json").exists():
        raw = json.loads((dedup_dir / "records.json").read_text(encoding="utf-8"))
        report = DedupReport.model_validate_json(
            (dedup_dir / "dedup.json").read_text(encoding="utf-8")
        )
        return [SearchRecord.model_validate(r) for r in raw], len(report.duplicates)
    deduped, report = dedup_agent.deduplicate_with_report(raw_records)
    run.ctx.write_json("02_dedup/records.json", [r.model_dump(mode="json") for r in deduped])
    run.ctx.write_json("02_dedup/dedup.json", report.model_dump(mode="json"))
    return deduped, len(report.duplicates)


def _load_gold(run: _Run, gold_labels: dict[str, bool] | None) -> dict[str, bool]:
    """Gold standard humano: ``00_protocol/gold.yml`` + etiquetas por código.

    Las pasadas por código tienen prioridad sobre las del fichero.
    """
    gold: dict[str, bool] = {}
    gold_file = _load_yaml(run.snapshot_dir / "gold.yml")
    for rid, val in (gold_file.get("gold", gold_file) or {}).items():
        gold[rid] = bool(val)
    if gold_labels:
        gold.update(gold_labels)
    return gold


def _member_role(i: int) -> str:
    """Rol de la llamada ``i`` del ensemble de T/A en ``llm_calls.jsonl``."""
    return f"member:{i}"


def _screen_ta(
    run: _Run, deduped: list[SearchRecord], gold: dict[str, bool]
) -> list[ScreeningDecision]:
    """Cribado T/A (A1): ensemble multi-modelo con voto sesgado a recall.

    Cada registro pasa por el diario de T/A (``03_screening/journal.jsonl``): al
    reanudar, un registro ya cribado no se vuelve a llamar (A9). Deja las
    métricas frente al gold (Recall/Lost-Evidence, MCC, WMCC, kappa) en
    ``run.metrics``.
    """
    members = [
        screening_agent.ScreenerMember(
            provider=build_provider(cfg),
            model_name=f"{cfg.provider}:{cfg.model}",
            temperature=cfg.temperature,
            seed=cfg.seed,
        )
        for cfg in run.protocol.screeners_for("screening_ta")
    ]
    miembros = [[m.model_name, m.temperature, m.seed] for m in members]
    journal = StageJournal(run.ctx, "screening_ta")
    decisions = []
    for record in deduped:
        decision = journaled(
            journal,
            record_id=record.record_id,
            inputs={
                "title": record.title,
                "abstract": record.abstract,
                "question": run.question,
                "criteria": run.criteria,
                "miembros": miembros,
            },
            model=ScreeningDecision,
            compute=partial(
                screening_agent.screen_record,
                members,
                question=run.question,
                criteria=run.criteria,
                record=record,
            ),
            run_ctx=run.ctx,
            role_of=_member_role,
        )
        decision.final_label = decision.human_label or decision.ensemble_label
        decisions.append(decision)
    run.ctx.write_json("03_screening/decisions.json", [d.model_dump() for d in decisions])

    if gold:
        # Gold efectivo (fichero + `gold_labels=`), para que el auditor recalcule
        # las métricas desde disco (D6).
        run.ctx.write_json("03_screening/gold.json", dict(sorted(gold.items())))
        run.metrics = compute_screening_metrics(
            decisions, gold, fn_weight=run.protocol.thresholds.get("wmcc_fn_weight", 10.0)
        )
        run.ctx.write_json("03_screening/metrics.json", run.metrics.model_dump())
    return decisions


# Claves de `SearchRecord.extra` que usa la recuperación de texto completo
# (`agents/fulltext.py`): entran en el `input_sha256` de su diario.
_RETRIEVAL_EXTRA: tuple[str, ...] = ("fulltext_url", "oa_url", "pmcid", "pmid")

# Motivos de fallo que NO se escriben en el diario de la recuperación: un error de red
# (`error_http`) o la falta de `httpx` (`sin_httpx`) no es una respuesta definitiva sobre
# el informe, así que congelarla haría que reanudar nunca lo reintentara y que "informes
# no recuperados" contara fallos que ya se habrían resuelto (auditoría 2026-09-03, A9:
# un fallo transitorio se resuelve reanudando). Se usan en esta invocación y en
# `retrieval.json` y se piden otra vez al reanudar. Los motivos permanentes
# (`sin_url_oa`, `texto_vacio`, `no_disponible`) y los éxitos sí se escriben.
_TRANSIENT_FULLTEXT_REASONS: frozenset[str] = frozenset({"error_http", "sin_httpx"})


def _write_bytes_durably(path: Path, data: bytes) -> None:
    """Escribe ``data`` en ``path`` de forma atómica y duradera.

    Temporal en el mismo directorio, ``flush`` + ``fsync`` y ``os.replace``: el
    diario ya hace ``fsync`` al escribir, y sin esto, tras un corte de luz, el
    diario puede sobrevivir sin el texto al que apunta y la reanudación declararía
    la corrida no fiable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _fetch_one(run: _Run, fetch: FetchFn, record: SearchRecord) -> RetrievalOutcome:
    """Recupera un texto completo y, si lo hay, lo guarda en la caché de la corrida.

    El fichero es ``04_fulltext/texts/<sha256(id)[:16]>.txt`` (ningún
    ``record_id`` como nombre de fichero, spec §4.1), en bytes UTF-8 para que su
    hash no dependa del fin de línea del sistema. Sin LLM: ninguna llamada.
    """
    ft = fetch(record)
    if not ft.available:
        # Un fetch_fn inyectado puede no dar motivo: el genérico es no_disponible.
        return RetrievalOutcome(
            available=False,
            source_url=ft.source_url,
            reason=ft.reason or "no_disponible",
            detail=ft.detail,
        )
    text_file = f"04_fulltext/texts/{sha256_text(record.record_id)[:16]}.txt"
    _write_bytes_durably(run.ctx.run_dir / text_file, ft.text.encode("utf-8"))
    return RetrievalOutcome(
        available=True,
        source_url=ft.source_url,
        n_chars=len(ft.text),
        text_sha256=sha256_text(ft.text),
        text_file=text_file,
    )


def _cached_text(run: _Run, record_id: str, outcome: RetrievalOutcome) -> str:
    """Texto completo de la caché, verificado contra el hash de su diario.

    Una entrada mal formada, un texto ausente o ilegible y un texto alterado son
    errores del diario (``JournalError``, rc 2): no son una caída que reintentar,
    porque cada reanudación fallaría igual (un bucle sin salida).
    """
    if outcome.text_file is None or outcome.text_sha256 is None:
        raise JournalError(
            f"{record_id}: entrada mal formada en 04_fulltext/retrieval.jsonl (texto "
            "disponible sin text_file o sin text_sha256); la corrida ya no es fiable: "
            "empieza una nueva."
        )
    try:
        text = (run.ctx.run_dir / outcome.text_file).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise JournalError(
            f"{outcome.text_file}: el texto en caché falta o es ilegible ({type(exc).__name__}); "
            "la corrida ya no es fiable: empieza una nueva."
        ) from exc
    if sha256_text(text) != outcome.text_sha256:
        raise JournalError(
            f"{outcome.text_file}: el texto en caché no coincide con el hash de su diario; "
            "la corrida ya no es fiable."
        )
    return text


def _retrieve(
    run: _Run, passed_ta: list[SearchRecord], fetch_fn: FetchFn | None
) -> tuple[dict[str, RetrievalOutcome], dict[str, str]]:
    """Recuperación de texto completo con diario (``04_fulltext/retrieval.jsonl``).

    Al reanudar no se vuelve a descargar nada de lo que ya tiene respuesta
    definitiva: el resultado sale del diario y el texto, de la caché. Los fallos
    transitorios (``_TRANSIENT_FULLTEXT_REASONS``) no se escriben en el diario y se
    reintentan al reanudar; el diario conserva así su invariante (misma clave,
    misma salida). Escribe ``04_fulltext/retrieval.json`` en el orden de
    ``passed_ta``.
    """
    fetch = fetch_fn or (lambda rec: fulltext_agent.fetch_fulltext(rec, mailto=run.mailto))
    journal = StageJournal(run.ctx, "fulltext_retrieval")
    outcomes: dict[str, RetrievalOutcome] = {}
    texts: dict[str, str] = {}
    for record in passed_ta:
        input_sha256 = canonical_sha256(
            {
                "record_id": record.record_id,
                "doi": record.doi,
                "extra": {k: record.extra[k] for k in _RETRIEVAL_EXTRA if k in record.extra},
                "mailto_set": bool(run.mailto),
            }
        )
        entry = journal.lookup(record.record_id, input_sha256)
        if entry is not None:
            outcome = entry_output(entry, RetrievalOutcome, source=journal.path)
        else:
            # No usa `journaled`, que escribe siempre la salida de `compute`: aquí los
            # motivos transitorios (`_TRANSIENT_FULLTEXT_REASONS`) no se escriben, para
            # reintentarlos al reanudar, y el texto se cachea antes del `append` (una
            # caída entre medias deja un texto huérfano, inocuo, nunca una entrada sin
            # texto).
            outcome = _fetch_one(run, fetch, record)
            if outcome.reason not in _TRANSIENT_FULLTEXT_REASONS:
                journal.append(
                    JournalEntry(
                        stage="fulltext_retrieval",
                        record_id=record.record_id,
                        input_sha256=input_sha256,
                        output=outcome.model_dump(mode="json"),
                        metas=[],
                    )
                )
        outcomes[record.record_id] = outcome
        if outcome.available:
            texts[record.record_id] = _cached_text(run, record.record_id, outcome)
    run.ctx.write_json(
        "04_fulltext/retrieval.json",
        [{"record_id": rid, **o.model_dump(mode="json")} for rid, o in outcomes.items()],
    )
    return outcomes, texts


def _screen_ft_one(
    run: _Run,
    provider: LLMProvider,
    model_name: str,
    cfg: ProviderConfig,
    record: SearchRecord,
    text: str,
) -> tuple[ScreeningDecision, list[RunMeta]]:
    """Cribado a texto completo de un registro recuperado (``compute`` de su diario)."""
    decision, meta = screening_ft_agent.screen_fulltext(
        provider,
        model_name,
        question=run.question,
        criteria=run.criteria,
        record=record,
        text=text,
        temperature=cfg.temperature,
        seed=cfg.seed,
    )
    decision.fulltext_status = "retrieved"
    return decision, [meta]


def _fulltext(run: _Run, passed_ta: list[SearchRecord], fetch_fn: FetchFn | None) -> _FullTextStage:
    """Texto completo + cribado a texto completo (A0).

    PRISMA estricto (D2; auditoría 2026-09-03, M11): un informe sin texto
    completo NO se criba con IA (antes se cribaba con el abstract y contaba
    como evaluado). Queda como "no recuperado", con su motivo en
    04_fulltext/retrieval.json, y no llega a extracción.
    """
    outcomes, fulltexts = _retrieve(run, passed_ta, fetch_fn)
    ft_cfg = run.protocol.provider_for("screening_ft")
    ft_provider = build_provider(ft_cfg)
    ft_model = f"{ft_cfg.provider}:{ft_cfg.model}"
    journal = StageJournal(run.ctx, "screening_ft")
    ft_decisions: list[ScreeningDecision] = []
    for record in passed_ta:
        if not outcomes[record.record_id].available:
            ft_decisions.append(
                ScreeningDecision(
                    record_id=record.record_id,
                    phase="fulltext",
                    fulltext_status="not_retrieved",
                    votes=[],
                    ensemble_label=None,
                )
            )
            continue
        decision = journaled(
            journal,
            record_id=record.record_id,
            inputs={
                "title": record.title,
                "abstract": record.abstract,
                "question": run.question,
                "criteria": run.criteria,
                "miembros": [[ft_model, ft_cfg.temperature, ft_cfg.seed]],
                "text_sha256": outcomes[record.record_id].text_sha256,
            },
            model=ScreeningDecision,
            compute=partial(
                _screen_ft_one,
                run,
                ft_provider,
                ft_model,
                ft_cfg,
                record,
                fulltexts[record.record_id],
            ),
            run_ctx=run.ctx,
        )
        decision.final_label = decision.human_label or decision.ensemble_label
        ft_decisions.append(decision)
    run.ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])
    not_retrieved = sum(1 for d in ft_decisions if d.fulltext_status == "not_retrieved")
    return _FullTextStage(ft_decisions, fulltexts, not_retrieved)


def _extraction_inputs(
    run: _Run, record: SearchRecord, fulltexts: dict[str, str], cfg: ProviderConfig
) -> dict:
    """``inputs`` del diario de extracción: registro, texto, formulario y proveedor.

    Incluye ``title`` y ``abstract`` porque ``extraccion.extract_record`` los manda a la
    IA junto con el texto: si el registro cambia, el diario no puede devolver la
    extracción vieja (revisión de la Tarea 13). Desvía la tabla del §7 del spec, que
    solo pedía el hash del texto; la de RoB la hereda (``_assess_rob``).
    """
    text = fulltexts.get(record.record_id)
    return {
        "record_id": record.record_id,
        "title": record.title,
        "abstract": record.abstract,
        "text_sha256": sha256_text(text) if text is not None else None,
        "form_fields": run.form_fields,
        "proveedor": [f"{cfg.provider}:{cfg.model}", cfg.temperature, cfg.seed],
    }


def _extract_one(
    run: _Run, provider: LLMProvider, cfg: ProviderConfig, record: SearchRecord
) -> tuple[ExtractionRecord, list[RunMeta]]:
    """Extracción de un estudio (``compute`` de su diario)."""
    extraction, meta = extraccion_agent.extract_record(
        provider,
        record=record,
        form_fields=run.form_fields,
        temperature=cfg.temperature,
        seed=cfg.seed,
    )
    return extraction, [meta]


def _extract(
    run: _Run, included: list[SearchRecord], fulltexts: dict[str, str]
) -> tuple[dict[str, ExtractionRecord], ExtractionAgreement | None]:
    """Extracción de datos (A0) y, si hay 2.º extractor, doble extracción (≥20 %).

    El 2.º extractor es el primero de ``ensemble_llm['extraccion']``; el acuerdo
    entre extractores va a ``05_extraction/agreement.json`` (§6). Cada extractor
    tiene su diario (``05_extraction/journal.jsonl`` y ``journal_2.jsonl``).
    """
    extract_cfg = run.protocol.provider_for("extraccion")
    extract_provider = build_provider(extract_cfg)
    journal = StageJournal(run.ctx, "extraccion")
    extractions: dict[str, ExtractionRecord] = {}
    for record in included:
        extractions[record.record_id] = journaled(
            journal,
            record_id=record.record_id,
            inputs=_extraction_inputs(run, record, fulltexts, extract_cfg),
            model=ExtractionRecord,
            compute=partial(_extract_one, run, extract_provider, extract_cfg, record),
            run_ctx=run.ctx,
        )
    run.ctx.write_json(
        "05_extraction/extractions.json",
        {k: v.model_dump() for k, v in extractions.items()},
    )

    extraction_agreement = None
    second_extractors = run.protocol.ensemble_llm.get("extraccion", [])
    if second_extractors and included:
        subset = select_double_extraction_subset(included)
        second_cfg = second_extractors[0]
        second_provider = build_provider(second_cfg)
        journal_2 = StageJournal(run.ctx, "extraccion_2")
        secondary: dict[str, ExtractionRecord] = {}
        for record in subset:
            secondary[record.record_id] = journaled(
                journal_2,
                record_id=record.record_id,
                inputs=_extraction_inputs(run, record, fulltexts, second_cfg),
                model=ExtractionRecord,
                compute=partial(_extract_one, run, second_provider, second_cfg, record),
                run_ctx=run.ctx,
            )
        primary_subset = {r.record_id: extractions[r.record_id] for r in subset}
        extraction_agreement = compute_extraction_agreement(primary_subset, secondary)
        run.ctx.write_json("05_extraction/agreement.json", extraction_agreement.model_dump())
    return extractions, extraction_agreement


def _rob_one(
    run: _Run,
    provider: LLMProvider,
    cfg: ProviderConfig,
    record: SearchRecord,
    extraction: ExtractionRecord | None,
    text: str | None,
) -> tuple[RoBAssessment, list[RunMeta]]:
    """Riesgo de sesgo de un estudio (``compute`` de su diario)."""
    assessment, meta = rob_agent.assess_rob(
        provider,
        tool=run.protocol.rob_tool,
        record=record,
        extraction=extraction,
        text=text,
        temperature=cfg.temperature,
        seed=cfg.seed,
    )
    return assessment, [meta]


def _assess_rob(
    run: _Run,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
    fulltexts: dict[str, str],
) -> dict[str, RoBAssessment]:
    """Riesgo de sesgo (A0) con la herramienta del protocolo, con diario (``07_rob/``).

    La entrada del diario cubre lo de la extracción más el hash de la extracción
    del estudio y la herramienta (spec §7).
    """
    rob_cfg = run.protocol.provider_for("rob")
    rob_provider = build_provider(rob_cfg)
    journal = StageJournal(run.ctx, "rob")
    assessments: dict[str, RoBAssessment] = {}
    for record in included:
        extraction = extractions.get(record.record_id)
        extraction_sha256 = (
            canonical_sha256(extraction.model_dump(mode="json")) if extraction is not None else None
        )
        assessments[record.record_id] = journaled(
            journal,
            record_id=record.record_id,
            inputs={
                **_extraction_inputs(run, record, fulltexts, rob_cfg),
                "extraction_sha256": extraction_sha256,
                "tool": run.protocol.rob_tool,
            },
            model=RoBAssessment,
            compute=partial(
                _rob_one,
                run,
                rob_provider,
                rob_cfg,
                record,
                extraction,
                fulltexts.get(record.record_id),
            ),
            run_ctx=run.ctx,
        )
    run.ctx.write_json(
        "07_rob/assessments.json",
        {k: v.model_dump() for k, v in assessments.items()},
    )
    return assessments


def _meta_analysis(run: _Run) -> tuple[MetaAnalysisResult | None, str]:
    """Meta-análisis cuantitativo (§8.1) · opcional, desde ``effects.yml``.

    Si el protocolo aporta tamaños de efecto, se sintetiza cuantitativamente
    (efectos fijos + aleatorios, I²/τ², Egger); si no, solo síntesis narrativa.
    Devuelve el resultado y el modo de presentación del forest.
    """
    effects_cfg = _load_yaml(run.snapshot_dir / "effects.yml")
    meta_display = effects_cfg.get("display", "raw")  # "proportion" → forest en 0–1
    raw_effects = effects_cfg.get("effects", [])
    if not raw_effects:
        return None, meta_display
    measure = effects_cfg.get("measure", "precomputed")
    effects = [EffectInput.model_validate(e) for e in raw_effects]
    meta_result = meta_analyze(effects, measure)
    run.ctx.write_json("08_meta/meta_analysis.json", meta_result.model_dump())
    return meta_result, meta_display


class _Narrative(BaseModel):
    """Salida del diario de síntesis: ``{narrative}`` (spec §4.3)."""

    narrative: str


def _synthesize_one(
    run: _Run,
    provider: LLMProvider,
    cfg: ProviderConfig,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
) -> tuple[_Narrative, list[RunMeta]]:
    """Síntesis narrativa (``compute`` del diario de síntesis)."""
    narrative, meta = reporte_agent.synthesize_narrative(
        provider,
        question=run.question,
        included=included,
        extractions=extractions,
        temperature=cfg.temperature,
        seed=cfg.seed,
    )
    return _Narrative(narrative=narrative), [meta]


def _verify_one(
    run: _Run,
    narrative: str,
    included: list[SearchRecord],
    sources: dict[str, str],
    *,
    provider: LLMProvider,
    cfg: ProviderConfig,
    embedder: Embedder | None,
) -> tuple[VerificationReport, list[RunMeta]]:
    """Verificación anti-alucinación (``compute`` de su diario).

    En modo ``agent`` cada juicio es una llamada al LLM: ``on_meta`` las recoge
    para que el diario y ``llm_calls.jsonl`` las registren.
    """
    metas: list[RunMeta] = []
    verify_kwargs: dict = {"sources": sources}
    grounding_mode = getattr(run.protocol, "grounding", "embedder")
    if grounding_mode == "agent":
        from revisia.rag.grounding import make_provider_judge

        verify_kwargs["judge"] = make_provider_judge(
            provider,
            f"{cfg.provider}:{cfg.model}",
            temperature=0.0,
            on_meta=metas.append,
        )
    elif grounding_mode != "existence":  # "embedder" (default)
        verify_kwargs["embedder"] = embedder or HashEmbedder()
    verification = verificador_agent.verify_narrative(
        "reporte",
        narrative,
        [r.record_id for r in included],
        **verify_kwargs,
    )
    return verification, metas


def _synthesize_and_verify(
    run: _Run,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
    fulltexts: dict[str, str],
    embedder: Embedder | None,
) -> tuple[str, VerificationReport]:
    """Síntesis narrativa (A1) y verificador anti-alucinación (grounding).

    Modo según ``protocol.grounding``: "agent" (un modelo juzga; cruza idiomas,
    sin vectores), "existence" (solo id en corpus) o "embedder" (coseno léxico).
    Las dos van al diario (``record_id`` ``"sintesis"`` y ``"verificacion"``):
    sin él, reanudar volvería a llamar al LLM, cambiaría la narrativa y con ella
    la solicitud del gate final, que no convergería nunca (spec §2, hallazgo 1).
    """
    synth_cfg = run.protocol.provider_for("sintesis")
    synth_provider = build_provider(synth_cfg)
    narrative = journaled(
        StageJournal(run.ctx, "sintesis"),
        record_id="sintesis",
        inputs={
            "incluidos": [[r.record_id, r.title] for r in included],
            "extracciones_sha256": canonical_sha256(
                {k: v.model_dump(mode="json") for k, v in extractions.items()}
            ),
            "proveedor": [
                f"{synth_cfg.provider}:{synth_cfg.model}",
                synth_cfg.temperature,
                synth_cfg.seed,
            ],
        },
        model=_Narrative,
        compute=partial(_synthesize_one, run, synth_provider, synth_cfg, included, extractions),
        run_ctx=run.ctx,
    ).narrative

    sources = {r.record_id: (fulltexts.get(r.record_id) or r.abstract or "") for r in included}
    verification = journaled(
        StageJournal(run.ctx, "verificacion"),
        record_id="verificacion",
        inputs={
            "narrativa_sha256": sha256_text(narrative),
            "fuentes_sha256": canonical_sha256(sources),
            "modo": getattr(run.protocol, "grounding", "embedder"),
        },
        model=VerificationReport,
        compute=partial(
            _verify_one,
            run,
            narrative,
            included,
            sources,
            provider=synth_provider,
            cfg=synth_cfg,
            embedder=embedder,
        ),
        run_ctx=run.ctx,
    )
    run.ctx.write_json("06_synthesis/verification.json", verification.model_dump())
    return narrative, verification


def _build_counts(
    *,
    raw_records: list[SearchRecord],
    deduped: list[SearchRecord],
    discarded: int,
    excluded_ta: int,
    ta_breakdown: ExclusionBreakdown,
    passed_ta: list[SearchRecord],
    ft: _FullTextStage,
    excluded_ft: int,
    excluded_reports: list[ExcludedReport],
    ft_exclusion_reasons: dict[str, int],
    included: list[SearchRecord],
) -> PrismaCounts:
    """Conteos PRISMA 2020 de la corrida (diagrama, tabla, CSV y manifiesto)."""
    identified_by_source: dict[str, int] = {}
    for r in raw_records:
        identified_by_source[r.source_db] = identified_by_source.get(r.source_db, 0) + 1
    return PrismaCounts(
        identified=len(raw_records),
        identified_by_source=identified_by_source,
        duplicates_removed=discarded,
        screened=len(deduped),
        excluded_ta=excluded_ta,
        excluded_ta_human=ta_breakdown.excluded_human,
        excluded_ta_ai=ta_breakdown.excluded_ai,
        fulltext_sought=len(passed_ta),
        fulltext_not_retrieved=ft.not_retrieved,
        fulltext_rescued=0,  # los rescates humanos llegan con el HITL por registro (PR-D)
        fulltext_assessed=len(passed_ta) - ft.not_retrieved,
        excluded_ft=excluded_ft,
        excluded_ft_human=sum(1 for r in excluded_reports if r.reason_source == "human"),
        excluded_ft_ai=sum(1 for r in excluded_reports if r.reason_source == "ai"),
        ft_exclusion_reasons=ft_exclusion_reasons,
        included=len(included),
    )


def _write_deliverables(
    run: _Run,
    *,
    counts: PrismaCounts,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
    assessments: dict[str, RoBAssessment],
    narrative: str,
    excluded_reports: list[ExcludedReport],
    exclusion_breakdown: ExclusionBreakdown,
    extraction_agreement: ExtractionAgreement | None,
    meta_result: MetaAnalysisResult | None,
    meta_display: str,
) -> Path:
    """Escribe el entregable completo (``deliverable/``) y devuelve su carpeta."""
    protocol = run.protocol
    search_log = read_search_log(run.ctx.run_dir)
    deliverable = run.ctx.deliverable_dir()
    (deliverable / "documento.md").write_text(
        f"# {protocol.title}\n\n## Síntesis narrativa (borrador)\n\n{narrative}\n",
        encoding="utf-8",
    )
    (deliverable / "prisma_flow.md").write_text(
        render_flow_diagram(counts) + "\n\n" + render_flow_markdown(counts) + "\n",
        encoding="utf-8",
    )
    (deliverable / "excluidos_texto_completo.md").write_text(
        render_excluded_reports(excluded_reports), encoding="utf-8"
    )
    (deliverable / "risk_of_bias.md").write_text(
        _rob_table_md(protocol.rob_tool, assessments), encoding="utf-8"
    )
    (deliverable / "tabla_extraccion.md").write_text(
        render_extraction_table(included, extractions), encoding="utf-8"
    )
    (deliverable / "referencias.bib").write_text(render_bibtex(included), encoding="utf-8")
    models_used = sorted({f"{m.provider}:{m.model}" for m in run.ctx.metas})
    (deliverable / "metodologia.md").write_text(
        render_methods(
            protocol=protocol,
            counts=counts,
            metrics=run.metrics,
            models=models_used,
            quantitative=meta_result is not None,
            exclusions=exclusion_breakdown,
            extraction_agreement=extraction_agreement,
            search_log=search_log,
        ),
        encoding="utf-8",
    )
    if meta_result is not None:
        (deliverable / "meta_analisis.md").write_text(
            render_forest_markdown(meta_result, display=meta_display), encoding="utf-8"
        )
        assets = deliverable / "assets"
        render_forest_png(meta_result, assets / "forest.png", display=meta_display)
        render_funnel_png(meta_result, assets / "funnel.png")
    (deliverable / "checklist_2020.md").write_text(render_prisma_2020_checklist(), encoding="utf-8")
    (deliverable / "checklist_s.md").write_text(
        render_prisma_s_checklist(
            databases=list(protocol.databases),
            search_window=protocol.search_window,
            counts=counts,
            search_log=search_log,
        ),
        encoding="utf-8",
    )
    (deliverable / "checklist_abstracts.md").write_text(
        render_prisma_abstracts_checklist(
            counts=counts,
            databases=list(protocol.databases),
            search_window=protocol.search_window,
            registration=protocol.registration,
            search_log=search_log,
        ),
        encoding="utf-8",
    )
    (deliverable / "checklist_traice.md").write_text(
        render_traice_checklist(
            run.ctx.metas,
            dict(protocol.autonomy),
            metrics=run.metrics,
            exclusions=exclusion_breakdown,
            search_window=protocol.search_window,
        ),
        encoding="utf-8",
    )

    # Interop con herramientas OSS del ecosistema (docs/integraciones.md).
    interop_dir = deliverable / "interop"
    interop_dir.mkdir(parents=True, exist_ok=True)
    if assessments:
        (interop_dir / "robvis.csv").write_text(render_robvis_csv(assessments), encoding="utf-8")
    (interop_dir / "prisma2020_flow.csv").write_text(
        render_prisma2020_flow_csv(
            counts, meta_k=meta_result.k if meta_result is not None else None
        ),
        encoding="utf-8",
    )
    if meta_result is not None:
        (interop_dir / "effects_metafor.csv").write_text(
            render_metafor_csv(meta_result), encoding="utf-8"
        )
    return deliverable


def run_pipeline(
    protocol: ReviewProtocol,
    protocol_dir: str | Path | None,
    run_ctx: RunContext,
    *,
    max_results: int = 25,
    auto_approve: bool = False,
    mailto: str | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    embedder: Embedder | None = None,
    gold_labels: dict[str, bool] | None = None,
) -> PipelineResult:
    """Ejecuta el tracer bullet end-to-end y devuelve su resultado.

    Una corrida nueva copia el protocolo a ``00_protocol/`` y escribe
    ``run.json``; una que se reanuda (``run.json`` ya existe) verifica su
    instantánea y toma ``max_results`` de ``run.json``. ``protocol_dir`` puede
    ser ``None`` al reanudar.

    Antes de nada corre el preflight sin red (M6): con ``context="resume"`` si la
    búsqueda ya está congelada (``01_search/log.json``) o la inyecta
    ``search_fn`` (no hay bases que comprobar), y ``"run"`` si no.

    Raises:
        PreflightError, ProtocolMismatchError, JournalError, DecisionFileError:
            errores de configuración o de entrada humana (rc 2 en el CLI).
        RunInterrupted: cualquier otro error a mitad de corrida; queda en
            ``run.json`` (``status: interrupted``) y se reanuda (D14).
    """
    frozen = (run_ctx.run_dir / SEARCH_DIR / "log.json").exists()
    report = preflight(
        protocol,
        protocol_dir if protocol_dir is not None else run_ctx.run_dir / SNAPSHOT_DIR,
        context="resume" if frozen or search_fn is not None else "run",
        mailto=mailto,
    )
    if report.errors:
        raise PreflightError(report)
    # Estado con que llega la corrida (si ya existía): `ensure_snapshot` lo pisa con
    # `running` y un error de configuración tiene que poder devolverlo (I2).
    before = read_run_info(run_ctx.run_dir)
    previous = (before.status, before.stage) if before is not None else None
    snapshot_dir, run_info = ensure_snapshot(
        protocol_dir, run_ctx, max_results=max_results, mailto=mailto
    )
    ie = _load_yaml(snapshot_dir / "inclusion_exclusion.yml")
    form = _load_yaml(snapshot_dir / "extraction_form.yml")
    run = _Run(
        protocol=protocol,
        snapshot_dir=snapshot_dir,
        source_dir=Path(protocol_dir) if protocol_dir is not None else None,
        ctx=run_ctx,
        question=protocol.question.text,
        criteria=_criteria_to_text(ie),
        form_fields=form.get("fields", []),
        auto_approve=auto_approve,
        mailto=mailto,
        previous=previous,
    )
    try:
        return _run_stages(
            run,
            max_results=run_info.max_results,
            search_fn=search_fn,
            fetch_fn=fetch_fn,
            embedder=embedder,
            gold_labels=gold_labels,
        )
    except _CONFIG_ERRORS:
        run.config_error()
        raise
    except KeyboardInterrupt:
        run.interrupted("KeyboardInterrupt")
        raise
    except Exception as exc:
        # Redactar antes de recortar: un secreto cortado a medias ya no casaría con
        # el patrón y se filtraría.
        error = _http.redact_secrets(f"{type(exc).__name__}: {exc}")[:_MAX_ERROR_CHARS]
        run.interrupted(error)
        raise RunInterrupted(run_ctx.run_dir, run.stage, error) from exc


def _run_stages(
    run: _Run,
    *,
    max_results: int,
    search_fn: SearchFn | None,
    fetch_fn: FetchFn | None,
    embedder: Embedder | None,
    gold_labels: dict[str, bool] | None,
) -> PipelineResult:
    """Encadena las etapas; ``run.stage`` dice cuál está en curso."""
    protocol = run.protocol
    run.stage = "busqueda"
    raw_records = _search(run, max_results=max_results, search_fn=search_fn)
    run.stage = "dedup"
    deduped, discarded = _dedup(run, raw_records)
    run.stage = "screening_ta"
    decisions = _screen_ta(run, deduped, _load_gold(run, gold_labels))
    ta_autonomy = protocol.autonomy_for("screening_ta")
    ta_gate = run.gate(
        "screening_ta",
        ta_payload(decisions=decisions, records=deduped, autonomy=ta_autonomy),
        records=ta_policy(decisions=decisions, records=deduped, autonomy=ta_autonomy),
    )
    if (stop := run.stop(ta_gate, "screening_ta")) is not None:
        return stop
    # D5: solo las etiquetas explícitas pasan a human_label; decisions.json se
    # reescribe con ellas (spec §4.2). Una aprobación en bloque o --auto-approve
    # no trae ninguna: la exclusión sigue siendo "IA avalada" (trAIce R1).
    decisions = apply_labels(decisions, ta_gate.labels, ta_gate.actor)
    run.ctx.write_json("03_screening/decisions.json", [d.model_dump() for d in decisions])
    passed = {d.record_id for d in decisions if d.final_label in {"include", "unclear"}}
    excluded_ta = sum(1 for d in decisions if d.final_label == "exclude")

    passed_ta = [r for r in deduped if r.record_id in passed]
    run.stage = "screening_ft"
    ft = _fulltext(run, passed_ta, fetch_fn)
    # Hasta PR-D un `unclear` de FT sigue pasando (lo resolverá un humano, D1).
    included_ids = {d.record_id for d in ft.decisions if d.final_label in {"include", "unclear"}}
    excluded_ft = sum(1 for d in ft.decisions if d.final_label == "exclude")
    ft_payload = {
        "n_buscados": len(passed_ta),
        "n_no_recuperados": ft.not_retrieved,
        "n_evaluados": len(passed_ta) - ft.not_retrieved,
        "n_incluidos": len(included_ids),
        "n_excluidos": excluded_ft,
    }
    if (stop := run.stop(run.gate("screening_ft", ft_payload), "screening_ft")) is not None:
        return stop
    included = [r for r in passed_ta if r.record_id in included_ids]

    # Desglose de exclusiones humano vs IA (PRISMA-trAIce) sobre ambas fases; el
    # de solo T/A alimenta la nota ** del flow diagram oficial (trAIce R1).
    exclusion_breakdown = compute_exclusion_breakdown(decisions + ft.decisions)
    run.ctx.write_json("03_screening/exclusions.json", exclusion_breakdown.model_dump())
    ta_breakdown = compute_exclusion_breakdown(decisions)
    # Informes excluidos en elegibilidad (16b) y sus razones (cajas "Reason 1..n"
    # del flow oficial): una sola lista para el diagrama, la tabla y el auditor.
    excluded_reports = compute_ft_excluded(ft.decisions, passed_ta)
    run.ctx.write_json("04_fulltext/excluded.json", [r.model_dump() for r in excluded_reports])
    ft_exclusion_reasons = dict(Counter(r.reason for r in excluded_reports))

    run.stage = "extraccion"
    extractions, extraction_agreement = _extract(run, included, ft.texts)
    extraction_gate = run.gate("extraccion", {"n_extraidos": len(extractions)})
    if (stop := run.stop(extraction_gate, "extraccion")) is not None:
        return stop
    run.stage = "rob"
    assessments = _assess_rob(run, included, extractions, ft.texts)
    rob_gate = run.gate("rob", {"n_evaluados": len(assessments), "tool": protocol.rob_tool})
    if (stop := run.stop(rob_gate, "rob")) is not None:
        return stop

    run.stage = "sintesis"
    meta_result, meta_display = _meta_analysis(run)
    narrative, verification = _synthesize_and_verify(run, included, extractions, ft.texts, embedder)
    run.stage = "reporte"
    counts = _build_counts(
        raw_records=raw_records,
        deduped=deduped,
        discarded=discarded,
        excluded_ta=excluded_ta,
        ta_breakdown=ta_breakdown,
        passed_ta=passed_ta,
        ft=ft,
        excluded_ft=excluded_ft,
        excluded_reports=excluded_reports,
        ft_exclusion_reasons=ft_exclusion_reasons,
        included=included,
    )
    deliverable = _write_deliverables(
        run,
        counts=counts,
        included=included,
        extractions=extractions,
        assessments=assessments,
        narrative=narrative,
        excluded_reports=excluded_reports,
        exclusion_breakdown=exclusion_breakdown,
        extraction_agreement=extraction_agreement,
        meta_result=meta_result,
        meta_display=meta_display,
    )

    # Checkpoint final del reporte (A1). La solicitud no lleva rutas absolutas (su
    # hash tiene que ser estable entre reanudaciones): el documento va por su hash.
    documento = (deliverable / "documento.md").read_text(encoding="utf-8")
    final_gate = run.gate(
        "reporte",
        {
            "included": len(included),
            "hallucination_flagged": verification.hallucination_flagged,
            "documento_sha256": sha256_text(documento),
        },
    )
    # Un reporte rechazado ya no se informa como "completed" (auditoría
    # 2026-09-03, C1). El estado va a run.json antes del manifiesto, que lo copia.
    status, message, stage = final_gate.status, final_gate.message, "reporte"
    if final_gate.status == "approved":
        status = "completed"
        message = f"Revisión completada · {counts.included} estudios incluidos."
        stage = None
    run.finish(status, stage)
    manifest_extra: dict = {
        "verification": verification.model_dump(),
        "risk_of_bias": {k: v.model_dump() for k, v in assessments.items()},
        "exclusions": exclusion_breakdown.model_dump(),
    }
    if run.metrics is not None:
        manifest_extra["screening_metrics"] = run.metrics.model_dump()
    if extraction_agreement is not None:
        manifest_extra["extraction_agreement"] = extraction_agreement.model_dump()
    if meta_result is not None:
        manifest_extra["meta_analysis"] = meta_result.model_dump()
    run.ctx.write_manifest(
        protocol_snapshot=protocol.model_dump(mode="json"),
        counts=counts.model_dump(),
        autonomy_effective={g: protocol.autonomy_for(g) for g in GATED_STAGES},
        final_gate={"forced_human": False, "reason": None},
        extra=manifest_extra,
    )
    return PipelineResult(
        status=status,
        message=message,
        counts=counts,
        included=included,
        narrative=narrative,
        hallucination_flagged=verification.hallucination_flagged,
        metrics=run.metrics,
        run_dir=run.ctx.run_dir,
        stage=stage,
    )
