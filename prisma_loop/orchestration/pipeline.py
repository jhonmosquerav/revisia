"""Pipeline del tracer bullet (recorrido por etapas, Python puro y testeable).

Encadena los agentes con un checkpoint humano tras el screening y otro antes de
finalizar el reporte, corriendo el verificador anti-alucinación sobre la
síntesis. Es ``orchestration/flow.py`` (Prefect) quien lo envuelve para una
corrida "de producción"; aquí vive la lógica, sin dependencias pesadas, para
poder testearla offline con el proveedor ``fake``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from prisma_loop.agents import dedup as dedup_agent
from prisma_loop.agents import extraccion as extraccion_agent
from prisma_loop.agents import fulltext as fulltext_agent
from prisma_loop.agents import reporte as reporte_agent
from prisma_loop.agents import rob as rob_agent
from prisma_loop.agents import screening as screening_agent
from prisma_loop.agents import screening_ft as screening_ft_agent
from prisma_loop.agents import search_backends
from prisma_loop.agents import verificador as verificador_agent
from prisma_loop.config import ReviewProtocol
from prisma_loop.exclusions import compute_exclusion_breakdown
from prisma_loop.exports import (
    PrismaCounts,
    render_bibtex,
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
from prisma_loop.extraction_agreement import (
    compute_extraction_agreement,
    select_double_extraction_subset,
)
from prisma_loop.ingest import import_directory
from prisma_loop.llm.registry import build_provider
from prisma_loop.meta_analysis import meta_analyze
from prisma_loop.metrics import ScreeningMetrics, compute_screening_metrics
from prisma_loop.orchestration.hitl import review_gate
from prisma_loop.orchestration.run_context import RunContext
from prisma_loop.rag.embed import Embedder, HashEmbedder
from prisma_loop.schemas.effects import EffectInput
from prisma_loop.schemas.extraction import ExtractionRecord
from prisma_loop.schemas.records import SearchRecord
from prisma_loop.schemas.rob import RoBAssessment

SearchFn = Callable[[str, int], list[SearchRecord]]
FetchFn = Callable[[SearchRecord], fulltext_agent.FullText]


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
) -> list[SearchRecord]:
    """Busca en cada base declarada (con su cadena) + importación manual.

    Por cada base de ``protocol.databases`` lee su cadena en
    ``search_strings/<base>.txt`` (cae a la pregunta) y despacha al backend; las
    bases sin backend programático (Scopus/WoS) se cubren con los archivos
    RIS/BibTeX de ``imported/``. La deduplicación posterior une los solapes.
    """
    databases = protocol.databases or ["openalex"]
    records: list[SearchRecord] = []
    for db in databases:
        string_file = protocol_dir / "search_strings" / f"{db.lower()}.txt"
        query = question_text
        if string_file.exists():
            query = string_file.read_text(encoding="utf-8").strip() or question_text
        try:
            records += search_backends.search_database(db, query, max_results, mailto=mailto)
        except ValueError:
            # Base sin backend (p. ej. Scopus): se incorpora vía imported/.
            continue
    records += import_directory(protocol_dir / "imported")
    return records


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


def run_pipeline(
    protocol: ReviewProtocol,
    protocol_dir: str | Path,
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
    """Ejecuta el tracer bullet end-to-end y devuelve su resultado."""
    protocol_dir = Path(protocol_dir)
    ie = _load_yaml(protocol_dir / "inclusion_exclusion.yml")
    form = _load_yaml(protocol_dir / "extraction_form.yml")
    form_fields = form.get("fields", [])
    criteria_text = _criteria_to_text(ie)
    question_text = protocol.question.text

    # Gold standard humano para métricas (opcional): gold.yml del protocolo +
    # cualquier etiqueta pasada por código (estas últimas tienen prioridad).
    gold: dict[str, bool] = {}
    gold_file = _load_yaml(protocol_dir / "gold.yml")
    for rid, val in (gold_file.get("gold", gold_file) or {}).items():
        gold[rid] = bool(val)
    if gold_labels:
        gold.update(gold_labels)

    # ── 1. Búsqueda multi-base (A2) ─────────────────────────────────────
    # ``search_fn`` inyectado (tests) tiene prioridad y conserva el contrato
    # de una sola llamada; en producción se busca en todas las bases declaradas.
    if search_fn is not None:
        raw_records = search_fn(question_text, max_results)
    else:
        raw_records = _multi_database_search(
            protocol, protocol_dir, question_text, max_results, mailto
        )

    # ── 2. Deduplicación (A2) ───────────────────────────────────────────
    deduped, discarded = dedup_agent.deduplicate(raw_records)

    # ── 3. Screening T/A (A1) · ensemble multi-modelo + voto a recall ───
    members = [
        screening_agent.ScreenerMember(
            provider=build_provider(cfg),
            model_name=f"{cfg.provider}:{cfg.model}",
            temperature=cfg.temperature,
            seed=cfg.seed,
        )
        for cfg in protocol.screeners_for("screening_ta")
    ]
    decisions = []
    for record in deduped:
        decision, metas = screening_agent.screen_record(
            members,
            question=question_text,
            criteria=criteria_text,
            record=record,
        )
        decision.final_label = decision.human_label or decision.ensemble_label
        decisions.append(decision)
        for meta in metas:
            run_ctx.record_meta(meta)
    run_ctx.write_json("03_screening/decisions.json", [d.model_dump() for d in decisions])

    # Métricas frente al gold standard humano (Recall/Lost-Evidence, MCC, WMCC, kappa).
    screening_metrics: ScreeningMetrics | None = None
    if gold:
        screening_metrics = compute_screening_metrics(
            decisions, gold, fn_weight=protocol.thresholds.get("wmcc_fn_weight", 10.0)
        )
        run_ctx.write_json("03_screening/metrics.json", screening_metrics.model_dump())

    passed = {d.record_id for d in decisions if d.final_label in {"include", "unclear"}}
    excluded_ta = sum(1 for d in decisions if d.final_label == "exclude")

    # ── 4. Checkpoint humano tras screening ─────────────────────────────
    gate = review_gate(
        stage="screening_ta",
        autonomy=protocol.autonomy_for("screening_ta"),
        run_ctx=run_ctx,
        review_payload={
            "n_screened": len(deduped),
            "n_pass": len(passed),
            "n_excluded": excluded_ta,
            "pass_ids": sorted(passed),
        },
        auto_approve=auto_approve,
    )
    if gate.status == "paused":
        return PipelineResult(
            "paused", gate.message, metrics=screening_metrics, run_dir=run_ctx.run_dir
        )
    if gate.status == "rejected":
        return PipelineResult(
            "rejected", gate.message, metrics=screening_metrics, run_dir=run_ctx.run_dir
        )

    passed_ta = [r for r in deduped if r.record_id in passed]

    # ── 5. Texto completo + cribado a full-text (A0) ────────────────────
    fetch = fetch_fn or (lambda rec: fulltext_agent.fetch_fulltext(rec, mailto=mailto))
    ft_cfg = protocol.provider_for("screening_ft")
    ft_provider = build_provider(ft_cfg)
    ft_model = f"{ft_cfg.provider}:{ft_cfg.model}"
    fulltexts: dict[str, str] = {}
    ft_decisions = []
    ft_abstract_only = 0
    for record in passed_ta:
        ft = fetch(record)
        if not ft.available:
            ft_abstract_only += 1
        fulltexts[record.record_id] = ft.text or (record.abstract or "")
        decision, meta = screening_ft_agent.screen_fulltext(
            ft_provider,
            ft_model,
            question=question_text,
            criteria=criteria_text,
            record=record,
            text=ft.text,
            temperature=ft_cfg.temperature,
            seed=ft_cfg.seed,
        )
        decision.final_label = decision.human_label or decision.ensemble_label
        ft_decisions.append(decision)
        run_ctx.record_meta(meta)
    run_ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])

    included_ids = {d.record_id for d in ft_decisions if d.final_label in {"include", "unclear"}}
    excluded_ft = sum(1 for d in ft_decisions if d.final_label == "exclude")

    ft_gate = review_gate(
        stage="screening_ft",
        autonomy=protocol.autonomy_for("screening_ft"),
        run_ctx=run_ctx,
        review_payload={
            "n_evaluados": len(passed_ta),
            "n_incluidos": len(included_ids),
            "n_excluidos": excluded_ft,
        },
        auto_approve=auto_approve,
    )
    if ft_gate.status != "approved":
        return PipelineResult(
            ft_gate.status, ft_gate.message, metrics=screening_metrics, run_dir=run_ctx.run_dir
        )

    included = [r for r in passed_ta if r.record_id in included_ids]

    # Desglose de exclusiones humano vs IA (PRISMA-trAIce) sobre ambas fases.
    exclusion_breakdown = compute_exclusion_breakdown(decisions + ft_decisions)
    run_ctx.write_json("03_screening/exclusions.json", exclusion_breakdown.model_dump())
    # Solo fase T/A: alimenta la nota ** del flow diagram oficial (trAIce R1).
    ta_breakdown = compute_exclusion_breakdown(decisions)

    # Razones de exclusión en elegibilidad (cajas "Reason 1..n" del flow oficial).
    ft_exclusion_reasons: dict[str, int] = {}
    for d in ft_decisions:
        if d.final_label == "exclude":
            violated = [c for v in d.votes for c in v.criteria_violated]
            reason = violated[0] if violated else "criterio no especificado"
            ft_exclusion_reasons[reason] = ft_exclusion_reasons.get(reason, 0) + 1

    # ── 6. Extracción de datos (A0) ─────────────────────────────────────
    extract_cfg = protocol.provider_for("extraccion")
    extract_provider = build_provider(extract_cfg)
    extractions: dict[str, ExtractionRecord] = {}
    for record in included:
        extraction, meta = extraccion_agent.extract_record(
            extract_provider,
            record=record,
            form_fields=form_fields,
            temperature=extract_cfg.temperature,
            seed=extract_cfg.seed,
        )
        extractions[record.record_id] = extraction
        run_ctx.record_meta(meta)
    run_ctx.write_json(
        "05_extraction/extractions.json",
        {k: v.model_dump() for k, v in extractions.items()},
    )

    # Doble extracción independiente (≥20%) si hay un 2.º extractor configurado
    # en ensemble_llm['extraccion'] · reporta acuerdo entre extractores (§6).
    extraction_agreement = None
    second_extractors = protocol.ensemble_llm.get("extraccion", [])
    if second_extractors and included:
        subset = select_double_extraction_subset(included)
        second_cfg = second_extractors[0]
        second_provider = build_provider(second_cfg)
        secondary: dict[str, ExtractionRecord] = {}
        for record in subset:
            extraction2, meta2 = extraccion_agent.extract_record(
                second_provider,
                record=record,
                form_fields=form_fields,
                temperature=second_cfg.temperature,
                seed=second_cfg.seed,
            )
            secondary[record.record_id] = extraction2
            run_ctx.record_meta(meta2)
        primary_subset = {r.record_id: extractions[r.record_id] for r in subset}
        extraction_agreement = compute_extraction_agreement(primary_subset, secondary)
        run_ctx.write_json("05_extraction/agreement.json", extraction_agreement.model_dump())

    extract_gate = review_gate(
        stage="extraccion",
        autonomy=protocol.autonomy_for("extraccion"),
        run_ctx=run_ctx,
        review_payload={"n_extraidos": len(extractions)},
        auto_approve=auto_approve,
    )
    if extract_gate.status != "approved":
        return PipelineResult(
            extract_gate.status,
            extract_gate.message,
            metrics=screening_metrics,
            run_dir=run_ctx.run_dir,
        )

    # ── 7. Riesgo de sesgo (A0) ─────────────────────────────────────────
    rob_cfg = protocol.provider_for("rob")
    rob_provider = build_provider(rob_cfg)
    assessments: dict[str, RoBAssessment] = {}
    for record in included:
        assessment, meta = rob_agent.assess_rob(
            rob_provider,
            tool=protocol.rob_tool,
            record=record,
            extraction=extractions.get(record.record_id),
            text=fulltexts.get(record.record_id),
            temperature=rob_cfg.temperature,
            seed=rob_cfg.seed,
        )
        assessments[record.record_id] = assessment
        run_ctx.record_meta(meta)
    run_ctx.write_json(
        "07_rob/assessments.json",
        {k: v.model_dump() for k, v in assessments.items()},
    )
    rob_gate = review_gate(
        stage="rob",
        autonomy=protocol.autonomy_for("rob"),
        run_ctx=run_ctx,
        review_payload={"n_evaluados": len(assessments), "tool": protocol.rob_tool},
        auto_approve=auto_approve,
    )
    if rob_gate.status != "approved":
        return PipelineResult(
            rob_gate.status, rob_gate.message, metrics=screening_metrics, run_dir=run_ctx.run_dir
        )

    # ── 7b. Meta-análisis cuantitativo (§8.1) · opcional, desde effects.yml ──
    # Si el protocolo aporta tamaños de efecto, se sintetiza cuantitativamente
    # (efectos fijos + aleatorios, I²/τ², Egger); si no, solo síntesis narrativa.
    meta_result = None
    effects_cfg = _load_yaml(protocol_dir / "effects.yml")
    raw_effects = effects_cfg.get("effects", [])
    if raw_effects:
        measure = effects_cfg.get("measure", "precomputed")
        effects = [EffectInput.model_validate(e) for e in raw_effects]
        meta_result = meta_analyze(effects, measure)
        run_ctx.write_json("08_meta/meta_analysis.json", meta_result.model_dump())

    # ── 8. Síntesis narrativa (A1) ──────────────────────────────────────
    synth_cfg = protocol.provider_for("sintesis")
    synth_provider = build_provider(synth_cfg)
    narrative, meta = reporte_agent.synthesize_narrative(
        synth_provider,
        question=question_text,
        included=included,
        extractions=extractions,
        temperature=synth_cfg.temperature,
        seed=synth_cfg.seed,
    )
    run_ctx.record_meta(meta)

    # ── 9. Verificador anti-alucinación (grounding) ─────────────────────
    # Modo según protocol.grounding: "agent" (un modelo juzga; cruza idiomas,
    # sin vectores), "existence" (solo id en corpus) o "embedder" (coseno léxico).
    sources = {r.record_id: (fulltexts.get(r.record_id) or r.abstract or "") for r in included}
    verify_kwargs: dict = {"sources": sources}
    grounding_mode = getattr(protocol, "grounding", "embedder")
    if grounding_mode == "agent":
        from prisma_loop.rag.grounding import make_provider_judge

        verify_kwargs["judge"] = make_provider_judge(
            synth_provider, f"{synth_cfg.provider}:{synth_cfg.model}", temperature=0.0
        )
    elif grounding_mode != "existence":  # "embedder" (default)
        verify_kwargs["embedder"] = embedder or HashEmbedder()
    verification = verificador_agent.verify_narrative(
        "reporte",
        narrative,
        [r.record_id for r in included],
        **verify_kwargs,
    )
    run_ctx.write_json("06_synthesis/verification.json", verification.model_dump())

    # ── 10. Conteos PRISMA + entregables ────────────────────────────────
    identified_by_source: dict[str, int] = {}
    for r in raw_records:
        identified_by_source[r.source_db] = identified_by_source.get(r.source_db, 0) + 1
    counts = PrismaCounts(
        identified=len(raw_records),
        identified_by_source=identified_by_source,
        duplicates_removed=discarded,
        screened=len(deduped),
        excluded_ta=excluded_ta,
        excluded_ta_human=ta_breakdown.excluded_human,
        excluded_ta_ai=ta_breakdown.excluded_ai,
        fulltext_assessed=len(passed_ta),
        fulltext_abstract_only=ft_abstract_only,
        excluded_ft=excluded_ft,
        ft_exclusion_reasons=ft_exclusion_reasons,
        included=len(included),
    )
    deliverable = run_ctx.deliverable_dir()
    (deliverable / "documento.md").write_text(
        f"# {protocol.title}\n\n## Síntesis narrativa (borrador)\n\n{narrative}\n",
        encoding="utf-8",
    )
    (deliverable / "prisma_flow.md").write_text(
        render_flow_diagram(counts) + "\n\n" + render_flow_markdown(counts) + "\n",
        encoding="utf-8",
    )
    (deliverable / "risk_of_bias.md").write_text(
        _rob_table_md(protocol.rob_tool, assessments), encoding="utf-8"
    )
    (deliverable / "tabla_extraccion.md").write_text(
        render_extraction_table(included, extractions), encoding="utf-8"
    )
    (deliverable / "referencias.bib").write_text(render_bibtex(included), encoding="utf-8")
    models_used = sorted({f"{m.provider}:{m.model}" for m in run_ctx.metas})
    (deliverable / "metodologia.md").write_text(
        render_methods(
            protocol=protocol,
            counts=counts,
            metrics=screening_metrics,
            models=models_used,
            quantitative=meta_result is not None,
            exclusions=exclusion_breakdown,
            extraction_agreement=extraction_agreement,
        ),
        encoding="utf-8",
    )
    if meta_result is not None:
        (deliverable / "meta_analisis.md").write_text(
            render_forest_markdown(meta_result), encoding="utf-8"
        )
        assets = deliverable / "assets"
        render_forest_png(meta_result, assets / "forest.png")
        render_funnel_png(meta_result, assets / "funnel.png")
    (deliverable / "checklist_2020.md").write_text(render_prisma_2020_checklist(), encoding="utf-8")
    (deliverable / "checklist_s.md").write_text(
        render_prisma_s_checklist(
            databases=list(protocol.databases),
            search_window=protocol.search_window,
            counts=counts,
        ),
        encoding="utf-8",
    )
    (deliverable / "checklist_abstracts.md").write_text(
        render_prisma_abstracts_checklist(
            counts=counts,
            databases=list(protocol.databases),
            search_window=protocol.search_window,
            registration=protocol.registration,
        ),
        encoding="utf-8",
    )
    (deliverable / "checklist_traice.md").write_text(
        render_traice_checklist(
            run_ctx.metas,
            dict(protocol.autonomy),
            metrics=screening_metrics,
            exclusions=exclusion_breakdown,
            search_window=protocol.search_window,
        ),
        encoding="utf-8",
    )

    # ── Interop con herramientas OSS del ecosistema (docs/integraciones.md) ─
    interop_dir = deliverable / "interop"
    interop_dir.mkdir(parents=True, exist_ok=True)
    if assessments:
        (interop_dir / "robvis.csv").write_text(render_robvis_csv(assessments), encoding="utf-8")
    (interop_dir / "prisma2020_flow.csv").write_text(
        render_prisma2020_flow_csv(counts), encoding="utf-8"
    )
    if meta_result is not None:
        (interop_dir / "effects_metafor.csv").write_text(
            render_metafor_csv(meta_result), encoding="utf-8"
        )

    # ── 11. Checkpoint final del reporte (A1) ───────────────────────────
    final_gate = review_gate(
        stage="reporte",
        autonomy=protocol.autonomy_for("reporte"),
        run_ctx=run_ctx,
        review_payload={
            "included": len(included),
            "hallucination_flagged": verification.hallucination_flagged,
            "deliverable": str(deliverable),
        },
        auto_approve=auto_approve,
    )
    manifest_extra: dict = {
        "verification": verification.model_dump(),
        "risk_of_bias": {k: v.model_dump() for k, v in assessments.items()},
        "exclusions": exclusion_breakdown.model_dump(),
    }
    if screening_metrics is not None:
        manifest_extra["screening_metrics"] = screening_metrics.model_dump()
    if extraction_agreement is not None:
        manifest_extra["extraction_agreement"] = extraction_agreement.model_dump()
    if meta_result is not None:
        manifest_extra["meta_analysis"] = meta_result.model_dump()
    run_ctx.write_manifest(
        protocol_snapshot=protocol.model_dump(mode="json"),
        counts=counts.model_dump(),
        extra=manifest_extra,
    )
    if final_gate.status == "paused":
        return PipelineResult(
            "paused",
            final_gate.message,
            counts=counts,
            included=included,
            narrative=narrative,
            hallucination_flagged=verification.hallucination_flagged,
            metrics=screening_metrics,
            run_dir=run_ctx.run_dir,
        )

    return PipelineResult(
        status="completed",
        message=f"Revisión completada · {counts.included} estudios incluidos.",
        counts=counts,
        included=included,
        narrative=narrative,
        hallucination_flagged=verification.hallucination_flagged,
        metrics=screening_metrics,
        run_dir=run_ctx.run_dir,
    )
