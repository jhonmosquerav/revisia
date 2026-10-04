"""Test end-to-end del pipeline (offline · proveedor fake + búsqueda simulada).

Demuestra el tracer bullet completo sin red ni API key: búsqueda inyectada,
dedup, screening, extracción, síntesis, verificador, gates HITL (auto-approve),
entregables y manifiesto reproducible.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible
from hitl_helpers import correr_hasta

from revisia.audit import run_audit
from revisia.config import load_protocol
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration import search_stage as search_stage_mod
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _fake_search(query: str, n: int) -> list[SearchRecord]:
    records = [
        SearchRecord(
            record_id="rec-1",
            title="LLM screening for systematic reviews",
            abstract="We evaluate LLM screening with recall 0.98 and 60% workload reduction.",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-1-dup",
            title="LLM screening for systematic reviews",  # mismo título → duplicado
            abstract="duplicado",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-2",
            title="Active learning with ASReview",
            abstract="Active learning reduces screening workload by 70%.",
            source_db="OpenAlex",
        ),
    ]
    return records[:n]


def test_pipeline_end_to_end_offline(tmp_path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST")
    result = run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        max_results=10,
        auto_approve=True,
        search_fn=_fake_search,
        # PRISMA estricto (D2): sin texto completo nada llega a extracción, y los
        # registros simulados no tienen texto en abierto.
        fetch_fn=fetch_disponible,
    )

    assert result.status == "completed"
    assert result.counts.identified == 3
    assert result.counts.duplicates_removed == 1
    assert result.counts.screened == 2
    assert result.counts.fulltext_sought == 2
    assert result.counts.fulltext_not_retrieved == 0
    assert result.counts.fulltext_assessed == 2
    assert result.counts.included == 2  # el proveedor fake incluye todo
    assert result.hallucination_flagged is False

    # Entregables generados.
    deliverable = ctx.run_dir / "deliverable"
    assert (deliverable / "documento.md").exists()
    assert (deliverable / "prisma_flow.md").exists()
    assert (deliverable / "checklist_2020.md").exists()
    assert (deliverable / "checklist_traice.md").exists()
    assert (deliverable / "excluidos_texto_completo.md").exists()

    # Manifiesto reproducible + ledger: 5 gates (screening_ta, screening_ft,
    # extraccion, rob, reporte).
    assert (ctx.run_dir / "manifest.yml").exists()
    manifest = yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["provenance"] == "pipeline"
    assert len(ctx.ledger.read_all()) == 5
    # Etapas H3 presentes: full-text + riesgo de sesgo.
    assert (ctx.run_dir / "04_fulltext" / "decisions.json").exists()
    assert (ctx.run_dir / "07_rob" / "assessments.json").exists()
    assert (ctx.run_dir / "deliverable" / "risk_of_bias.md").exists()


def test_pipeline_pausa_sin_auto_approve(tmp_path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST2")
    result = run_pipeline(protocol, EXAMPLE, ctx, auto_approve=False, search_fn=_fake_search)
    # Sin auto-approve y sin decision.yml, el primer gate A1 pausa.
    assert result.status == "paused"
    assert (ctx.run_dir / "screening_ta" / "review_request.yml").exists()


def test_pipeline_ensemble_y_metricas(tmp_path) -> None:
    # El demo usa un ensemble de 2 miembros fake → 2 votos por registro.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST3")
    result = run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        auto_approve=True,
        search_fn=_fake_search,
        gold_labels={"rec-1": True, "rec-2": True},
    )
    assert result.status == "completed"

    # Métricas calculadas contra el gold standard (fake incluye todo → recall 1.0).
    assert result.metrics is not None
    assert result.metrics.n == 2
    assert result.metrics.recall == 1.0
    assert result.metrics.lost_evidence == 0.0
    assert (ctx.run_dir / "03_screening" / "metrics.json").exists()

    # Cada decisión lleva los 2 votos del ensemble.
    decisions = json.loads(
        (ctx.run_dir / "03_screening" / "decisions.json").read_text(encoding="utf-8")
    )
    assert len(decisions[0]["votes"]) == 2


def test_rejected_final_gate_is_not_completed(tmp_path) -> None:
    # Desde la Ola 1 una decisión.yml lleva el request_sha256 de su solicitud, así
    # que no se puede escribir antes de correr: el humano responde a cada pausa
    # (aprueba los gates de juicio) y rechaza el reporte final.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST")

    def rechazar_el_reporte(stage: str, _solicitud: dict) -> dict | None:
        if stage == "reporte":
            return {"approved": False, "reason": "síntesis sin respaldo"}
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
        etiquetar=rechazar_el_reporte,
    )
    assert result.status == "rejected"  # antes: "completed"
    assert "rechazado por human:revisora" in result.message
    assert (ctx.run_dir / "manifest.yml").exists()  # el rechazo deja rastro en disco
    last = ctx.ledger.read_all()[-1]
    assert (last.stage, last.action) == ("reporte", "reject")

    # El auditor no debe declarar publicable una corrida rechazada en el gate final.
    report = run_audit(ctx.run_dir)
    final_gate = next(c for c in report.checks if c.check_id == "final_gate")
    assert final_gate.status == "FAIL"
    assert report.publishable is False


def test_paused_run_final_gate_falla_en_auditoria(tmp_path) -> None:
    # Aprueba en humano las etapas de juicio previas al reporte (screening_ta,
    # screening_ft, extraccion, rob), respondiendo a cada pausa con el
    # request_sha256 de su solicitud, para que la corrida llegue viva hasta el
    # checkpoint final y pause justo ahí (A1): es ese gate el que queremos ver
    # fallar en la auditoría, no uno anterior.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST-PAUSED")

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
        parar_en="reporte",
    )
    assert result.status == "paused"
    assert "reporte" in result.message
    assert (ctx.run_dir / "reporte" / "review_request.yml").exists()

    report = run_audit(ctx.run_dir)
    final_gate = next(c for c in report.checks if c.check_id == "final_gate")
    assert final_gate.status == "FAIL"


def test_ft_no_recuperado_no_se_criba_con_ia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M11/D2: antes, un registro sin texto completo se cribaba con el abstract y
    # contaba como evaluado.
    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST-NR")
    result = run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        max_results=10,
        auto_approve=True,
        search_fn=_fake_search,
        fetch_fn=fetch_no_disponible(["rec-2"]),
    )

    assert result.status == "completed"
    c = result.counts
    assert (c.screened, c.fulltext_sought, c.fulltext_not_retrieved) == (2, 2, 1)
    assert (c.fulltext_assessed, c.included) == (1, 1)
    # El proveedor de FT solo vio el registro recuperado.
    prompts_ft = [p for p in proveedor.prompts if "TEXTO COMPLETO" in p]
    assert len(prompts_ft) == 1
    assert "Active learning with ASReview" not in prompts_ft[0]

    run = ctx.run_dir
    ft = json.loads((run / "04_fulltext" / "decisions.json").read_text(encoding="utf-8"))
    no_recuperado = next(d for d in ft if d["record_id"] == "rec-2")
    assert no_recuperado["fulltext_status"] == "not_retrieved"
    assert no_recuperado["votes"] == []
    assert no_recuperado["ensemble_label"] is None
    assert no_recuperado["final_label"] is None
    recuperacion = json.loads((run / "04_fulltext" / "retrieval.json").read_text(encoding="utf-8"))
    assert {r["record_id"]: r["reason"] for r in recuperacion} == {
        "rec-1": None,
        "rec-2": "no_disponible",
    }
    # No entra en extracción ni en RoB.
    extracciones = json.loads(
        (run / "05_extraction" / "extractions.json").read_text(encoding="utf-8")
    )
    assert set(extracciones) == {"rec-1"}
    flujo = (run / "deliverable" / "prisma_flow.md").read_text(encoding="utf-8")
    assert "Informes no recuperados (n = 1)" in flujo


def test_ft_exclusion_ia_llega_a_16b(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = ScriptedProvider(criterio_exclusion="población incorrecta")
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)

    def fetch(record: SearchRecord):
        ft = fetch_disponible(record)
        if record.record_id == "rec-2":
            ft.text += " Este estudio es irrelevante para la pregunta."
        return ft

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST-16B")
    result = run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=_fake_search, fetch_fn=fetch
    )
    c = result.counts
    assert (c.excluded_ft, c.excluded_ft_ai, c.excluded_ft_human) == (1, 1, 0)
    assert c.ft_exclusion_reasons == {"población incorrecta": 1}
    excluidos = json.loads(
        (ctx.run_dir / "04_fulltext" / "excluded.json").read_text(encoding="utf-8")
    )
    assert [(e["record_id"], e["reason_source"]) for e in excluidos] == [("rec-2", "ai")]
    md = (ctx.run_dir / "deliverable" / "excluidos_texto_completo.md").read_text(encoding="utf-8")
    assert "población incorrecta | IA |" in md


def test_pipeline_result_indica_la_etapa_de_la_pausa(tmp_path: Path) -> None:
    # Refactor de la Ola 1 (spec 2026-10-04 §7): el resultado dice en qué gate se
    # detuvo la corrida; la reanudación (PR-C) y los helpers de test lo usan.
    protocol = load_protocol(EXAMPLE)
    pausa = run_pipeline(
        protocol, EXAMPLE, RunContext(protocol.slug, tmp_path, "T-PAUSA"), search_fn=_fake_search
    )
    assert (pausa.status, pausa.stage) == ("paused", "screening_ta")

    completa = run_pipeline(
        protocol,
        EXAMPLE,
        RunContext(protocol.slug, tmp_path, "T-FIN"),
        auto_approve=True,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
    )
    assert (completa.status, completa.stage) == ("completed", None)


def test_llm_calls_etiquetadas_por_etapa_y_registro(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T-CALLS")
    run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        auto_approve=True,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
    )
    lineas = (ctx.run_dir / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
    calls = [json.loads(x) for x in lineas]
    assert Counter(c["stage"] for c in calls) == {
        "screening_ta": 4,  # 2 registros × 2 miembros del ensemble
        "screening_ft": 2,
        "extraccion": 2,
        "extraccion_2": 1,
        "rob": 2,
        "sintesis": 1,
    }
    ta = [(c["record_id"], c["role"]) for c in calls if c["stage"] == "screening_ta"]
    assert ta == [
        ("rec-1", "member:0"),
        ("rec-1", "member:1"),
        ("rec-2", "member:0"),
        ("rec-2", "member:1"),
    ]
    manifest = yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["llm_calls"] == calls
    assert manifest["autonomy_effective"] == {
        "screening_ta": "A1",
        "screening_ft": "A0",
        "extraccion": "A0",
        "rob": "A0",
        "reporte": "A1",
    }


@pytest.mark.parametrize(
    ("executed", "difiere"),
    [("2026-06-26", True), ("2026-03-01", False)],
    ids=["fecha_tecleada_distinta", "fechas_coincidentes"],
)
def test_entregables_de_busqueda_salen_del_log_del_motor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executed: str, difiere: bool
) -> None:
    # M12 · cableado: PRISMA-S, el checklist de resúmenes y metodologia.md reciben el
    # log de búsqueda. Quitar `search_log=` de cualquiera de las tres llamadas lo rompe.
    monkeypatch.setattr(search_stage_mod, "utc_now_iso", lambda: "2026-03-01T10:00:00+00:00")
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    ficha = proto / "protocol.yml"
    ficha.write_text(
        ficha.read_text(encoding="utf-8").replace(
            'executed: "2026-06-26"', f'executed: "{executed}"'
        ),
        encoding="utf-8",
    )
    protocol = load_protocol(proto)
    assert protocol.search_window["executed"] == executed
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T-LOG")
    result = run_pipeline(
        protocol,
        proto,
        ctx,
        auto_approve=True,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
    )
    assert result.status == "completed"
    entregable = ctx.run_dir / "deliverable"

    def item(fichero: str, prefijo: str) -> str:
        texto = (entregable / fichero).read_text(encoding="utf-8")
        return next(x for x in texto.splitlines() if x.startswith(prefijo))

    # PRISMA-S: la rama «injected» (sin cadena por base) y la fecha del motor.
    item_8 = item("checklist_s.md", "- [ ] 8.")
    assert "búsqueda inyectada (search_fn): sin cadena por base" in item_8
    item_13 = item("checklist_s.md", "- [ ] 13.")
    assert "(fecha del motor): 2026-03-01" in item_13
    assert ("Difiere de search_window.executed" in item_13) is difiere
    assert ("⚠" in item_13) is difiere
    # Resúmenes: ítem 4 con la fecha registrada por el motor.
    assert "2026-03-01 (registrada por el motor)" in item("checklist_abstracts.md", "- [ ] 4.")
    # Métodos: fecha del motor y sin cita de cadenas por base (la búsqueda fue inyectada).
    metodologia = (entregable / "metodologia.md").read_text(encoding="utf-8")
    assert "(fecha registrada por el motor): 2026-03-01" in metodologia
    assert "00_protocol/search_strings/" not in metodologia
