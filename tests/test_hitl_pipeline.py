"""HITL por registro en el pipeline (Ola 1, PR-D; auditoría 2026-09-03, C1, M5 y M13;
spec 2026-10-04 §8)."""

from __future__ import annotations

import json
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible
from hitl_helpers import correr_hasta, leer_solicitud, responder_gate
from pydantic import BaseModel

from revisia import cli
from revisia.agents.fulltext import FullText
from revisia.config import load_protocol
from revisia.exports import PrismaCounts, render_methods, render_traice_checklist
from revisia.exports.checklist import describe_gate, human_validation_summary
from revisia.extraction_agreement import ExtractionAgreement
from revisia.metrics import ScreeningMetrics, compute_screening_metrics
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.gates import (
    apply_labels,
    dump_artifact,
    extraction_payload,
    ft_payload,
    ft_policy,
    report_payload,
    report_policy,
    rob_payload,
    ta_payload,
    ta_policy,
)
from revisia.orchestration.hitl import (
    _MAX_COMENTARIO,
    DecisionFileError,
    FlaggedClaim,
    FlagPolicy,
    RecordLabel,
    effective_autonomy,
    render_decision_template,
)
from revisia.orchestration.pipeline import PipelineResult, run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import read_run_info
from revisia.provenance.ledger import AUTO_APPROVE_ACTOR, summarize_gates
from revisia.provenance.runmeta import canonical_sha256, sha256_text
from revisia.schemas.artifacts import GateSummary, RetrievalOutcome
from revisia.schemas.extraction import ExtractionField, ExtractionRecord
from revisia.schemas.records import SearchRecord
from revisia.schemas.rob import RoBAssessment, RoBDomain
from revisia.schemas.screening import ScreeningDecision, ScreeningVote
from revisia.schemas.verification import CitationCheck, VerificationReport

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _busqueda(query: str, n: int) -> list[SearchRecord]:
    """rec-2 lleva "irrelevante" en el título: el guion lo excluye en T/A y en FT."""
    return [
        SearchRecord(
            record_id="rec-1",
            title="LLM screening for systematic reviews",
            abstract="We evaluate LLM screening.",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-2",
            title="Estudio irrelevante para la pregunta",
            abstract="Otra cosa.",
            source_db="OpenAlex",
        ),
    ][:n]


@pytest.fixture()
def proveedor(monkeypatch: pytest.MonkeyPatch) -> ScriptedProvider:
    guion = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: guion)
    return guion


def _json(ctx: RunContext, relpath: str):
    return json.loads((ctx.run_dir / relpath).read_text(encoding="utf-8"))


def _por_id(ctx: RunContext, relpath: str) -> dict[str, dict]:
    return {d["record_id"]: d for d in _json(ctx, relpath)}


def _sin_huella_humana(decisiones: dict[str, dict]) -> None:
    """D5: ninguna decisión lleva ``human_label``, ``human_reason`` ni ``human_actor``."""
    for rid, d in decisiones.items():
        huella = (d["human_label"], d["human_reason"], d["human_actor"])
        assert huella == (None, None, None), f"{rid}: {huella}"


def _proto_a0(tmp_path: Path, autonomia: str = "A0") -> Path:
    """Copia del demo con ``screening_ta`` en ``autonomia`` (por defecto A0: el humano
    etiqueta cada registro, D1)."""
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["autonomy"]["screening_ta"] = autonomia
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return proto


# ── Cribado T/A (D1, D5) ────────────────────────────────────────────────


def test_review_request_ta_lista_votos_por_miembro(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda).status == "paused"

    solicitud = leer_solicitud(ctx.run_dir, "screening_ta")
    assert (solicitud["mode"], solicitud["autonomy"], solicitud["must_label"]) == (
        "exceptions",
        "A1",
        [],
    )
    assert (solicitud["n_screened"], solicitud["n_proposed_pass"]) == (2, 1)
    assert solicitud["n_proposed_exclude"] == 1
    assert [r["record_id"] for r in solicitud["records"]] == ["rec-1", "rec-2"]
    rec2 = solicitud["records"][1]
    assert (rec2["proposal"], rec2["source_db"], rec2["title"]) == (
        "exclude",
        "OpenAlex",
        "Estudio irrelevante para la pregunta",
    )
    assert rec2["votes"] == [
        {
            "model": modelo,
            "label": "exclude",
            "confidence": 0.9,
            "rationale": "guion: exclude",
            "criteria_violated": ["fuera de alcance"],
        }
        for modelo in ("fake:fake-a", "fake:fake-b")
    ]
    plantilla = yaml.safe_load(
        (ctx.run_dir / "screening_ta" / "decision.template.yml").read_text(encoding="utf-8")
    )
    assert set(plantilla["records"]) == {"rec-1", "rec-2"}


def test_ta_a1_excepcion_humana_rescata_registro(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def rescatar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ta":
            return {"records": {"rec-2": {"label": "include", "reason": "sí trata de cribado"}}}
        return None

    pausa = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        etiquetar=rescatar,
        parar_en="screening_ft",
    )

    assert pausa.stage == "screening_ft"
    decisiones = _por_id(ctx, "03_screening/decisions.json")
    rec2 = decisiones["rec-2"]
    assert (rec2["ensemble_label"], rec2["human_label"], rec2["final_label"]) == (
        "exclude",
        "include",
        "include",
    )
    assert (rec2["human_reason"], rec2["human_actor"]) == ("sí trata de cribado", "human:revisora")
    # D5: la excepción es solo de rec-2; rec-1 sigue siendo "IA avalada".
    assert (decisiones["rec-1"]["human_label"], decisiones["rec-1"]["final_label"]) == (
        None,
        "include",
    )
    assert (decisiones["rec-1"]["human_reason"], decisiones["rec-1"]["human_actor"]) == (None, None)
    etiqueta = next(e for e in ctx.ledger.read_all() if e.action == "label")
    assert (etiqueta.target, etiqueta.detail["from"], etiqueta.detail["to"]) == (
        "rec-2",
        "exclude",
        "include",
    )
    assert len(_json(ctx, "04_fulltext/retrieval.json")) == 2  # rec-2 llega a texto completo


def test_ta_a1_sin_tocar_conserva_human_label_none(tmp_path: Path, proveedor) -> None:
    # D5: aprobar en bloque deja la exclusión como "IA avalada", no humana.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        parar_en="screening_ft",
    )

    decisiones = _por_id(ctx, "03_screening/decisions.json")
    assert [d["human_label"] for d in decisiones.values()] == [None, None]
    _sin_huella_humana(decisiones)
    assert decisiones["rec-2"]["final_label"] == "exclude"
    assert not [e for e in ctx.ledger.read_all() if e.action == "label"]
    aprobacion = next(e for e in ctx.ledger.read_all() if e.stage == "screening_ta")
    assert (aprobacion.action, aprobacion.detail["n_labels"]) == ("approve", 0)
    # Solo rec-1 (la propuesta de pasar) llega a texto completo.
    assert [r["record_id"] for r in _json(ctx, "04_fulltext/retrieval.json")] == ["rec-1"]


def test_ta_a1_aprobar_en_bloque_cuenta_la_exclusion_como_ia(tmp_path: Path, proveedor) -> None:
    # D5, hasta el desglose trAIce R1: la exclusión no etiquetada sigue siendo de la IA.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    resultado = correr_hasta(protocol, EXAMPLE, ctx, search_fn=_busqueda, fetch_fn=fetch_disponible)

    assert resultado.status == "completed"
    _sin_huella_humana(_por_id(ctx, "03_screening/decisions.json"))
    desglose = _json(ctx, "03_screening/exclusions.json")
    assert (desglose["excluded_ai"], desglose["excluded_human"]) == (1, 0)
    assert (resultado.counts.excluded_ta_ai, resultado.counts.excluded_ta_human) == (1, 0)


def test_ta_a0_etiquetar_todo_marca_a_cada_registro_como_humano(tmp_path: Path, proveedor) -> None:
    proto = _proto_a0(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    pausa = run_pipeline(protocol, proto, ctx, search_fn=_busqueda, fetch_fn=fetch_disponible)

    assert (pausa.status, pausa.stage) == ("paused", "screening_ta")
    solicitud = leer_solicitud(ctx.run_dir, "screening_ta")
    assert (solicitud["mode"], solicitud["autonomy"]) == ("label_all", "A0")
    assert solicitud["must_label"] == ["rec-1", "rec-2"]

    # Aprobar sin etiquetar nada no vale en A0: lista los pendientes.
    responder_gate(ctx.run_dir, "screening_ta")
    with pytest.raises(DecisionFileError, match=r"rec-1.*rec-2"):
        run_pipeline(
            protocol,
            proto,
            RunContext.open(ctx.run_dir),
            search_fn=_busqueda,
            fetch_fn=fetch_disponible,
        )

    # Etiquetar todo, también lo que coincide con la propuesta de la IA, es decisión humana.
    responder_gate(
        ctx.run_dir,
        "screening_ta",
        records={
            "rec-1": {"label": "include", "reason": "trata de cribado"},
            "rec-2": {"label": "exclude", "reason": "fuera de la pregunta"},
        },
    )
    pausa = run_pipeline(
        protocol,
        proto,
        RunContext.open(ctx.run_dir),
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
    )

    assert (pausa.status, pausa.stage) == ("paused", "screening_ft")
    decisiones = _por_id(ctx, "03_screening/decisions.json")
    assert [(d["human_label"], d["final_label"]) for d in decisiones.values()] == [
        ("include", "include"),
        ("exclude", "exclude"),
    ]
    assert [d["human_reason"] for d in decisiones.values()] == [
        "trata de cribado",
        "fuera de la pregunta",
    ]
    assert {d["human_actor"] for d in decisiones.values()} == {"human:revisora"}
    entradas = ctx.ledger.read_all()
    assert [e.target for e in entradas if e.action == "label"] == ["rec-1", "rec-2"]
    aprobacion = next(e for e in entradas if e.stage == "screening_ta" and e.action == "approve")
    assert aprobacion.detail["n_labels"] == 2
    assert [r["record_id"] for r in _json(ctx, "04_fulltext/retrieval.json")] == ["rec-1"]


def test_ta_a0_corte_humano_saca_un_registro_del_texto_completo(tmp_path: Path, proveedor) -> None:
    # La etiqueta humana manda sobre la propuesta: un corte (la IA incluía) no llega a FT
    # y un rescate (la IA excluía) sí.
    proto = _proto_a0(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    def invertir(stage: str, _solicitud: dict) -> dict | None:
        if stage != "screening_ta":
            return None
        return {
            "records": {
                "rec-1": {"label": "exclude", "reason": "es una nota editorial"},
                "rec-2": {"label": "include", "reason": "sí trata de cribado"},
            }
        }

    correr_hasta(
        protocol,
        proto,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        etiquetar=invertir,
        parar_en="screening_ft",
    )

    decisiones = _por_id(ctx, "03_screening/decisions.json")
    assert (decisiones["rec-1"]["ensemble_label"], decisiones["rec-1"]["final_label"]) == (
        "include",
        "exclude",
    )
    assert (decisiones["rec-2"]["ensemble_label"], decisiones["rec-2"]["final_label"]) == (
        "exclude",
        "include",
    )
    assert [r["record_id"] for r in _json(ctx, "04_fulltext/retrieval.json")] == ["rec-2"]


@pytest.mark.parametrize("autonomia", ["A1", "A0"])
def test_auto_approve_nunca_escribe_human_label(tmp_path: Path, proveedor, autonomia: str) -> None:
    # D5: --auto-approve es una aprobación de demostración: aprueba la propuesta de la IA
    # tal cual y no etiqueta nada (tampoco en A0, donde un humano tendría que etiquetar todo).
    proto = _proto_a0(tmp_path, autonomia)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    resultado = run_pipeline(
        protocol, proto, ctx, auto_approve=True, search_fn=_busqueda, fetch_fn=fetch_disponible
    )

    assert resultado.status == "completed"
    decisiones = _por_id(ctx, "03_screening/decisions.json")
    _sin_huella_humana(decisiones)
    assert [d["final_label"] for d in decisiones.values()] == ["include", "exclude"]
    entradas = ctx.ledger.read_all()
    assert not [e for e in entradas if e.action == "label"]
    aprobacion = next(e for e in entradas if e.stage == "screening_ta")
    assert (aprobacion.action, aprobacion.actor, aprobacion.detail["n_labels"]) == (
        "approve",
        AUTO_APPROVE_ACTOR,
        0,
    )


# ── Texto libre en la solicitud (D4; spec 2026-10-04, relación 15) ──────


class _ProveedorConSaltos(ScriptedProvider):
    """Su ``rationale`` y su criterio llevan separadores que YAML 1.1 trata como saltos."""

    def structured(self, req, schema):
        obj, meta = super().structured(req, schema)
        if "rationale" in schema.model_fields:
            obj = obj.model_copy(
                update={
                    "rationale": f"razón{chr(0x2028)}en dos líneas",
                    "criteria_violated": [f"criterio{chr(0x2029)}raro"],
                }
            )
        return obj, meta


def test_solicitud_ta_con_saltos_unicode_conserva_su_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Un título con U+0085 (mojibake de «…») y un rationale con U+2028 llegan al
    # review_request.yml por el mismo volcado de siempre (`dump_yaml`): leído de vuelta, el
    # fichero tiene que dar el mismo `request_sha256`, o el auditor no lo podría recalcular.
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: _ProveedorConSaltos())
    titulo = f"Estudio irrelevante{chr(0x85)} para la pregunta"

    def busqueda(_query: str, n: int) -> list[SearchRecord]:
        return [
            SearchRecord(
                record_id="rec-1",
                title=titulo,
                abstract="Otra cosa.",
                source_db="OpenAlex",
            )
        ][:n]

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=busqueda).status == "paused"

    solicitud = leer_solicitud(ctx.run_dir, "screening_ta")
    sin_hash = {k: v for k, v in solicitud.items() if k != "request_sha256"}
    assert canonical_sha256(sin_hash) == solicitud["request_sha256"]
    registro = solicitud["records"][0]
    assert registro["title"] == titulo
    assert registro["votes"][0]["rationale"] == f"razón{chr(0x2028)}en dos líneas"
    assert registro["votes"][0]["criteria_violated"] == [f"criterio{chr(0x2029)}raro"]
    # La plantilla (comentarios saneados) sigue siendo YAML válido y lista el registro.
    plantilla = yaml.safe_load(
        (ctx.run_dir / "screening_ta" / "decision.template.yml").read_text(encoding="utf-8")
    )
    assert set(plantilla["records"]) == {"rec-1"}


# ── Reanudar: el ledger conserva las etiquetas explícitas, y solo ellas ──


def test_ta_etiquetas_explicitas_sobreviven_a_reanudar_sin_decision_yml(
    tmp_path: Path, proveedor
) -> None:
    # `decision.yml` es solo el canal de entrada (spec §4.3): sin él, la decisión de T/A sale
    # del ledger, con la etiqueta de rec-2 y sin inventar ninguna para rec-1 (D5).
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def rescatar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ta":
            return {"records": {"rec-2": {"label": "include", "reason": "sí trata de cribado"}}}
        return None

    pausa = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        etiquetar=rescatar,
        parar_en="screening_ft",
    )
    assert pausa.stage == "screening_ft"
    (ctx.run_dir / "screening_ta" / "decision.yml").unlink()

    resultado = correr_hasta(
        protocol,
        EXAMPLE,
        RunContext.open(ctx.run_dir),
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
    )

    assert resultado.status == "completed"
    decisiones = _por_id(ctx, "03_screening/decisions.json")
    assert (decisiones["rec-2"]["human_label"], decisiones["rec-2"]["final_label"]) == (
        "include",
        "include",
    )
    assert (decisiones["rec-2"]["human_reason"], decisiones["rec-2"]["human_actor"]) == (
        "sí trata de cribado",
        "human:revisora",
    )
    assert decisiones["rec-1"]["human_label"] is None
    # En T/A (A1), solo la etiqueta explícita de rec-2: la de FT (A0) la pone `correr_hasta`.
    etiquetas_ta = [
        e.target for e in ctx.ledger.read_all() if e.action == "label" and e.stage == "screening_ta"
    ]
    assert etiquetas_ta == ["rec-2"]
    # El rescate cuenta: nada se excluyó en T/A y rec-2 llegó a texto completo.
    desglose = _json(ctx, "03_screening/exclusions.json")
    assert desglose["overridden_to_include"] == 1
    assert (resultado.counts.excluded_ta, resultado.counts.fulltext_sought) == (0, 2)


# ── Funciones puras de gates.py ─────────────────────────────────────────


def _decision(
    record_id: str, etiqueta: str, *, votos: tuple[str, ...] | None = None
) -> ScreeningDecision:
    """Decisión de T/A como la deja ``_screen_ta``: ``final_label`` = propuesta del ensemble."""
    return ScreeningDecision(
        record_id=record_id,
        votes=[
            ScreeningVote(model=f"m{i}", label=voto, confidence=0.8, rationale=f"razón {i}")
            for i, voto in enumerate(votos or (etiqueta,))
        ],
        ensemble_label=etiqueta,
        final_label=etiqueta,
    )


def _registros(*ids: str) -> list[SearchRecord]:
    return [
        SearchRecord(
            record_id=i, title=f"Título {i}", year=2020, doi=f"10.1/{i}", source_db="Crossref"
        )
        for i in ids
    ]


def test_apply_labels_solo_escribe_human_ante_una_etiqueta_explicita() -> None:
    originales = [
        _decision("a", "include"),
        _decision("b", "exclude"),
        _decision("c", "unclear"),
        _decision("d", "exclude"),
    ]
    etiquetas = {
        "b": RecordLabel(label="include", reason="rescate"),
        "c": RecordLabel(label=None, reason="solo un comentario"),  # `label: null` no etiqueta
        "zzz": RecordLabel(label="exclude"),  # un id ajeno a las decisiones no hace nada
    }

    nuevas = {d.record_id: d for d in apply_labels(originales, etiquetas, "human:ana")}

    sin_huella = [
        (nuevas[i].human_label, nuevas[i].human_reason, nuevas[i].human_actor) for i in "acd"
    ]
    assert sin_huella == [(None, None, None)] * 3
    b = nuevas["b"]
    assert (b.human_label, b.human_reason, b.human_actor) == ("include", "rescate", "human:ana")
    assert {i: d.final_label for i, d in nuevas.items()} == {
        "a": "include",
        "b": "include",
        "c": "unclear",
        "d": "exclude",
    }
    # Devuelve copias: las decisiones de entrada no cambian.
    assert all(d.human_label is None for d in originales)
    assert originales[1].final_label == "exclude"


def test_apply_labels_sin_etiquetas_no_deja_huella_humana_ni_con_actor() -> None:
    # `--auto-approve` llega con el actor sintético y sin etiquetas: el actor solo se
    # registra junto a una etiqueta explícita (D5).
    (nueva,) = apply_labels([_decision("a", "exclude")], {}, AUTO_APPROVE_ACTOR)

    assert (nueva.human_label, nueva.human_reason, nueva.human_actor) == (None, None, None)
    assert nueva.final_label == "exclude"


def test_ta_payload_ordena_por_id_y_resume_la_propuesta() -> None:
    decisiones = [
        _decision("c", "exclude"),
        _decision("b", "unclear", votos=("exclude", "unclear")),
        _decision("a", "include"),
    ]

    a1 = ta_payload(decisions=decisiones, records=_registros("b", "a", "c"), autonomy="A1")
    a0 = ta_payload(decisions=decisiones, records=_registros("b", "a", "c"), autonomy="A0")

    assert [r["record_id"] for r in a1["records"]] == ["a", "b", "c"]
    assert (a1["n_screened"], a1["n_proposed_pass"], a1["n_proposed_exclude"]) == (3, 2, 1)
    assert (a1["mode"], a1["must_label"]) == ("exceptions", [])
    assert (a0["mode"], a0["must_label"]) == ("label_all", ["a", "b", "c"])
    b = a1["records"][1]
    assert (b["title"], b["year"], b["doi"], b["source_db"], b["proposal"]) == (
        "Título b",
        2020,
        "10.1/b",
        "Crossref",
        "unclear",
    )
    assert [(v["model"], v["label"]) for v in b["votes"]] == [("m0", "exclude"), ("m1", "unclear")]
    # Las claves comunes las pone review_gate (y rechaza un payload que las traiga).
    assert not {"schema_version", "stage", "autonomy", "request_sha256"} & set(a1)


def test_ta_policy_a1_no_obliga_y_a0_exige_etiquetar_todo() -> None:
    decisiones = [
        _decision("b", "unclear", votos=("exclude", "unclear")),
        _decision("a", "include"),
    ]

    a1 = ta_policy(decisions=decisiones, records=_registros("a", "b"), autonomy="A1")
    a0 = ta_policy(decisions=decisiones, records=_registros("a", "b"), autonomy="A0")

    assert [(h.record_id, h.title, h.proposal) for h in a1.hints] == [
        ("a", "Título a", "include"),
        ("b", "Título b", "unclear"),
    ]
    assert "m0: exclude" in a1.hints[1].note and "m1: unclear" in a1.hints[1].note
    assert (a1.must_label, a1.must_resolve, a1.rescue_ids) == (frozenset(),) * 3
    assert a0.must_label == frozenset({"a", "b"})
    assert not a0.reason_on_exclude  # en T/A excluir no exige razón (solo en FT, lista 16b)


def test_ta_policy_sin_el_registro_usa_el_id_como_titulo() -> None:
    politica = ta_policy(decisions=[_decision("x", "include")], records=[], autonomy="A1")

    assert [(h.record_id, h.title) for h in politica.hints] == [("x", "x")]


def test_ta_payload_sin_el_registro_usa_el_id_como_titulo_como_ta_policy() -> None:
    # Una decisión cuyo registro falta no tumba la solicitud con un KeyError: ta_policy ya lo
    # toleraba (título = id) y las dos tienen que ver el mismo corpus (revisión de la Tarea 22).
    payload = ta_payload(decisions=[_decision("x", "include")], records=[], autonomy="A1")

    (registro,) = payload["records"]
    assert registro["record_id"] == "x"
    assert (registro["title"], registro["year"], registro["doi"], registro["source_db"]) == (
        "x",
        None,
        None,
        None,
    )
    assert registro["proposal"] == "include"


def test_ta_nota_muestra_el_voto_de_cada_miembro_antes_de_las_razones() -> None:
    # Con el ensemble sesgado a recall, un solo `include` basta para pasar: ese voto
    # discrepante es lo que el revisor tiene que ver aunque las razones sean largas. La
    # plantilla acota la nota a 120 caracteres, así que las etiquetas van todas primero.
    largo = "x" * 200
    decision = ScreeningDecision(
        record_id="a",
        votes=[
            ScreeningVote(model=f"m{i}", label=voto, confidence=0.8, rationale=f"{largo} {i}")
            for i, voto in enumerate(("exclude", "include", "exclude"))
        ],
        ensemble_label="include",
        final_label="include",
    )

    politica = ta_policy(decisions=[decision], records=_registros("a"), autonomy="A1")
    plantilla = render_decision_template(
        stage="screening_ta",
        autonomy="A1",
        request_sha256="0" * 64,
        records=politica,
        flags=None,
    )

    comentario = next(
        linea for linea in plantilla.splitlines() if linea.startswith("  # propuesta IA")
    )
    for esperado in ("m0: exclude (0.80)", "m1: include (0.80)", "m2: exclude (0.80)"):
        assert esperado in comentario
    # Las razones siguen en la nota (acotadas), después de los votos.
    assert politica.hints[0].note.index("m2: exclude") < politica.hints[0].note.index(largo[:20])
    assert len(politica.hints[0].note) < 3 * len(largo)


def _decision_con_modelos(
    modelos: tuple[str, ...], etiquetas: tuple[str, ...], razon: str
) -> ScreeningDecision:
    """Un registro ``a`` votado por ``modelos`` (uno por etiqueta), todos con la misma razón."""
    return ScreeningDecision(
        record_id="a",
        votes=[
            ScreeningVote(model=modelo, label=etiqueta, confidence=0.8, rationale=razon)
            for modelo, etiqueta in zip(modelos, etiquetas, strict=True)
        ],
        ensemble_label="include",
        final_label="include",
    )


def _comentario_de_la_plantilla(decision: ScreeningDecision) -> str:
    """La línea de comentario del registro de ``decision`` en ``decision.template.yml``."""
    politica = ta_policy(decisions=[decision], records=_registros("a"), autonomy="A1")
    plantilla = render_decision_template(
        stage="screening_ta",
        autonomy="A1",
        request_sha256="0" * 64,
        records=politica,
        flags=None,
    )
    return next(linea for linea in plantilla.splitlines() if linea.startswith("  # propuesta IA"))


def test_ta_plantilla_muestra_los_tres_votos_con_ids_de_modelo_reales() -> None:
    # Cada voto cuesta ~50 caracteres con ids reales: con el tope antiguo de 120 la nota
    # moría en `… | openrouter:deepseek/de…` y el voto discrepante no se veía.
    modelos = (
        "claude_code:claude-sonnet-5-5",
        "openrouter:google/gemini-3-pro",
        "openrouter:deepseek/deepseek-v4",
    )
    etiquetas = ("exclude", "include", "exclude")

    comentario = _comentario_de_la_plantilla(_decision_con_modelos(modelos, etiquetas, "r" * 200))

    for modelo, etiqueta in zip(modelos, etiquetas, strict=True):
        assert f"{modelo}: {etiqueta} (0.80)" in comentario
    # Lo único que se corta son las razones, y la línea sigue acotada.
    assert comentario.endswith("…")
    assert len(comentario.strip()) <= _MAX_COMENTARIO + len("# ")


def test_ta_plantilla_muestra_los_cinco_votos_con_ids_de_40_caracteres() -> None:
    modelos = tuple(f"p{i}:" + "m" * 37 for i in range(5))
    assert {len(m) for m in modelos} == {40}
    etiquetas = ("exclude", "exclude", "include", "unclear", "exclude")

    comentario = _comentario_de_la_plantilla(_decision_con_modelos(modelos, etiquetas, "r" * 5000))

    for modelo, etiqueta in zip(modelos, etiquetas, strict=True):
        assert f"{modelo}: {etiqueta} (0.80)" in comentario
    assert comentario.endswith("…")
    assert len(comentario.strip()) <= _MAX_COMENTARIO + len("# ")


def test_ta_nota_acota_el_id_de_modelo_a_40_caracteres_sin_perder_el_voto() -> None:
    # Un id de más de 40 caracteres se abrevia con «…»; el voto (etiqueta y confianza) queda.
    modelos = tuple(f"p{i}:" + "z" * 100 for i in range(5))
    etiquetas = ("exclude", "include", "exclude", "exclude", "unclear")

    comentario = _comentario_de_la_plantilla(_decision_con_modelos(modelos, etiquetas, "razón"))

    for modelo, etiqueta in zip(modelos, etiquetas, strict=True):
        assert f"{modelo[:39]}…: {etiqueta} (0.80)" in comentario
        assert modelo not in comentario


def test_ta_nota_omite_las_razones_vacias() -> None:
    def voto(modelo: str, etiqueta: str, razon: str) -> ScreeningVote:
        return ScreeningVote(model=modelo, label=etiqueta, confidence=0.7, rationale=razon)

    def nota(*votos: ScreeningVote) -> str:
        decision = ScreeningDecision(
            record_id="a", votes=list(votos), ensemble_label="include", final_label="include"
        )
        politica = ta_policy(decisions=[decision], records=_registros("a"), autonomy="A1")
        return politica.hints[0].note

    # Sin razón (vacía o solo espacios) no hay entrada `modelo: «»` en las razones.
    assert nota(voto("m0", "include", ""), voto("m1", "exclude", "no es un ECA")) == (
        "m0: include (0.70) | m1: exclude (0.70) · m1: «no es un ECA»"
    )
    # Ningún miembro razona: solo los votos, sin ` · ` colgando.
    assert nota(voto("m0", "include", ""), voto("m1", "exclude", "   ")) == (
        "m0: include (0.70) | m1: exclude (0.70)"
    )


# ── `unclear` de T/A con etiqueta humana (D1, D5) ───────────────────────


def _busqueda_con_dudoso(_query: str, n: int) -> list[SearchRecord]:
    """rec-3 lleva "dudoso" en el título: el guion lo marca ``unclear`` en T/A."""
    return [
        SearchRecord(
            record_id="rec-1",
            title="LLM screening for systematic reviews",
            abstract="We evaluate LLM screening.",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-3",
            title="Estudio dudoso sobre cribado",
            abstract="No está claro si aplica.",
            source_db="OpenAlex",
        ),
    ][:n]


@pytest.mark.parametrize(
    ("etiqueta", "llega_a_ft", "humana"),
    [(None, True, None), ("exclude", False, "exclude"), ("include", True, "include")],
    ids=["aprobar_en_bloque", "excluir_explicito", "incluir_explicito"],
)
def test_ta_unclear_con_etiqueta_humana_decide_si_llega_a_texto_completo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    etiqueta: str | None,
    llega_a_ft: bool,
    humana: str | None,
) -> None:
    # `unclear` pasa a texto completo (sesgo a recall) salvo que un humano lo excluya; solo
    # una etiqueta explícita deja `human_label`: aprobar en bloque lo deja como "IA avalada".
    guion = ScriptedProvider(palabras={"dudoso": "unclear"})
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: guion)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def decidir(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ta" and etiqueta is not None:
            return {"records": {"rec-3": {"label": etiqueta, "reason": "tras leer el resumen"}}}
        return None

    pausa = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_con_dudoso,
        fetch_fn=fetch_disponible,
        etiquetar=decidir,
        parar_en="screening_ft",
    )

    assert pausa.stage == "screening_ft"
    rec3 = _por_id(ctx, "03_screening/decisions.json")["rec-3"]
    assert (rec3["ensemble_label"], rec3["human_label"]) == ("unclear", humana)
    assert rec3["final_label"] == (humana or "unclear")
    llegados = [r["record_id"] for r in _json(ctx, "04_fulltext/retrieval.json")]
    assert ("rec-3" in llegados) is llega_a_ft
    assert "rec-1" in llegados


# ── Calidad de la propuesta IA (D6, D7) ──────────────────────────────────


def _proto_con_gold(tmp_path: Path) -> Path:
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)  # el demo declara recall_target: 0.95
    (proto / "gold.yml").write_text('gold:\n  "rec-1": true\n  "rec-2": true\n', "utf-8")
    return proto


def test_metricas_miden_la_propuesta_ia(tmp_path: Path, proveedor) -> None:
    # D6: un rescate humano no mejora el recall de la IA.
    rescatada = ScreeningDecision(
        record_id="x", ensemble_label="exclude", human_label="include", final_label="include"
    )
    metricas = compute_screening_metrics([rescatada], {"x": True})
    assert (metricas.tp, metricas.fn, metricas.recall) == (0, 1, 0.0)

    proto = _proto_con_gold(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    def rescatar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ta":
            return {"records": {"rec-2": {"label": "include", "reason": "relevante"}}}
        return None

    correr_hasta(
        protocol,
        proto,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        etiquetar=rescatar,
        parar_en="screening_ft",
    )
    assert _json(ctx, "03_screening/metrics.json")["recall"] == 0.5


def test_review_request_ta_informa_recall_y_exclusiones_ia(tmp_path: Path, proveedor) -> None:
    proto = _proto_con_gold(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(protocol, proto, ctx, search_fn=_busqueda)

    solicitud = leer_solicitud(ctx.run_dir, "screening_ta")
    assert solicitud["quality"] == {
        "recall": 0.5,
        "recall_target": 0.95,
        "kappa": 0.0,
        "kappa_min": None,
        "gold_positives": 2,
        "recall_meets_target": False,
    }
    assert solicitud["ai_excluded"] == ["rec-2"]


def test_review_request_ta_sin_gold_no_informa_calidad(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    solicitud = leer_solicitud(ctx.run_dir, "screening_ta")
    assert (solicitud["quality"], solicitud["ai_excluded"]) == (None, ["rec-2"])


def _metricas(recall: float | None) -> ScreeningMetrics:
    return ScreeningMetrics(n=2, tp=1, fp=0, fn=1, tn=0, recall=recall, cohen_kappa=0.0)


@pytest.mark.parametrize(
    ("recall", "umbrales", "cumple"),
    [
        (0.96, {"recall_target": 0.95}, True),
        (0.95, {"recall_target": 0.95}, True),  # la comparación es `>=`
        (0.5, {"recall_target": 0.95}, False),
        (None, {"recall_target": 0.95}, None),  # recall indefinido: ni cumple ni incumple
        (0.5, {"kappa_min": 0.6}, None),  # sin `recall_target` no hay con qué comparar
        (0.5, {}, None),
        (0.5, None, None),  # `ta_payload` tolera `thresholds=None`
    ],
)
def test_ta_payload_recall_meets_target_segun_recall_y_umbral(recall, umbrales, cumple) -> None:
    payload = ta_payload(
        decisions=[_decision("a", "include")],
        records=_registros("a"),
        autonomy="A1",
        metrics=_metricas(recall),
        thresholds=umbrales,
    )

    assert payload["quality"]["recall_meets_target"] is cumple
    assert payload["quality"]["recall"] == recall


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("recall_target", float("nan")),
        ("recall_target", float("inf")),
        ("kappa_min", float("nan")),
        ("kappa_min", -float("inf")),
    ],
)
def test_review_request_ta_con_umbral_no_finito_pausa_y_lo_deja_en_none(
    tmp_path: Path, proveedor, clave: str, valor: float
) -> None:
    # `.nan` y `.inf` son YAML válido: copiados tal cual a la solicitud, `canonical_sha256`
    # (allow_nan=False) lanzaba `ValueError` y la corrida moría en `screening_ta` sin pausar.
    # `load_protocol` ya los rechaza (rc 2, `test_umbral_no_finito_rechazado`), pero esta es la
    # defensa de la solicitud: un protocolo armado en código (`model_copy` no valida) puede
    # traerlos, y la solicitud los deja en `None` en vez de reventar.
    proto = _proto_con_gold(tmp_path)
    protocol = load_protocol(proto).model_copy(
        update={"thresholds": {"recall_target": 0.95, clave: valor}}
    )
    assert not math.isfinite(protocol.thresholds[clave])
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    resultado = run_pipeline(protocol, proto, ctx, search_fn=_busqueda)

    assert (resultado.status, resultado.stage) == ("paused", "screening_ta")
    calidad = leer_solicitud(ctx.run_dir, "screening_ta")["quality"]
    assert calidad[clave] is None
    # Sin umbral finito no se compara; el otro umbral sigue valiendo.
    esperado = None if clave == "recall_target" else False
    assert calidad["recall_meets_target"] is esperado


# ── Cribado a texto completo (C1, D1, D2, D9) ────────────────────────────


def _busqueda_ft(query: str, n: int) -> list[SearchRecord]:
    """Dos registros que pasan T/A; lo que decide FT lo pone el texto completo."""
    return [
        SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex"),
        SearchRecord(record_id="rec-2", title="Active learning", source_db="OpenAlex"),
    ][:n]


def _texto(**extra: str):
    """``fetch_fn`` que añade texto al de ``fetch_disponible`` (p. ej. "dudoso")."""

    def fetch(record: SearchRecord):
        ft = fetch_disponible(record)
        ft.text += " " + extra.get(record.record_id.replace("-", "_"), "")
        return ft

    return fetch


def _proto(tmp_path: Path, **autonomy: str) -> Path:
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["autonomy"].update(autonomy)
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), "utf-8")
    return proto


def _ft(ctx: RunContext) -> dict[str, dict]:
    return _por_id(ctx, "04_fulltext/decisions.json")


def test_ft_unclear_sin_resolver_impide_aprobar(tmp_path: Path, proveedor) -> None:
    # C1: hasta la Ola 1 un `unclear` de FT entraba en extracción y en los incluidos.
    proto = _proto(tmp_path, screening_ft="A1")
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    fetch = _texto(rec_1="Resultado dudoso.")
    correr_hasta(
        protocol, proto, ctx, search_fn=_busqueda_ft, fetch_fn=fetch, parar_en="screening_ft"
    )
    solicitud = leer_solicitud(ctx.run_dir, "screening_ft")
    assert (solicitud["must_resolve"], solicitud["must_label"]) == (["rec-1"], ["rec-1"])

    # En A1 una aprobación en bloque basta para lo demás, pero no para un `unclear`: la
    # validación la rechaza y nada llega a extracción.
    responder_gate(ctx.run_dir, "screening_ft")  # aprueba sin resolver el unclear
    with pytest.raises(DecisionFileError, match=r"rec-1 \(1 en total\)"):
        run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), fetch_fn=fetch)
    assert not (ctx.run_dir / "05_extraction").exists()

    responder_gate(
        ctx.run_dir, "screening_ft", records={"rec-1": {"label": "include", "reason": "cumple"}}
    )
    result = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), fetch_fn=fetch)
    assert result.stage == "extraccion"
    assert _ft(ctx)["rec-1"]["final_label"] == "include"


def test_auto_approve_no_resuelve_unclear_ft(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    result = run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        auto_approve=True,
        search_fn=_busqueda_ft,
        fetch_fn=_texto(rec_2="Caso dudoso."),
    )
    assert (result.status, result.stage) == ("paused", "screening_ft")
    assert "`unclear` solo los resuelve un humano" in result.message
    assert not (ctx.run_dir / "05_extraction").exists()  # el unclear no pasa en silencio


def test_ft_a0_pipeline_exige_etiquetar_los_recuperados(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)  # FT en A0 por defecto
    ctx = RunContext(protocol.slug, tmp_path, "T")
    fetch = fetch_no_disponible(["rec-2"])
    correr_hasta(
        protocol, EXAMPLE, ctx, search_fn=_busqueda_ft, fetch_fn=fetch, parar_en="screening_ft"
    )
    solicitud = leer_solicitud(ctx.run_dir, "screening_ft")
    assert (solicitud["mode"], solicitud["must_label"], solicitud["rescuable"]) == (
        "label_all",
        ["rec-1"],
        ["rec-2"],
    )
    assert (solicitud["n_sought"], solicitud["n_retrieved"], solicitud["n_not_retrieved"]) == (
        2,
        1,
        1,
    )
    no_recuperado = solicitud["records"][1]
    assert (no_recuperado["fulltext"], no_recuperado["fulltext_reason"]) == (
        "not_retrieved",
        "no_disponible",
    )
    assert no_recuperado["proposal"] is None and no_recuperado["confidence"] is None

    responder_gate(ctx.run_dir, "screening_ft")
    with pytest.raises(DecisionFileError, match=r"rec-1 \(1 en total\)"):
        run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)


def test_ft_a0_exclusion_humana_en_todos(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def etiquetar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {
                "records": {
                    "rec-1": {"label": "include", "reason": "cumple"},
                    "rec-2": {"label": "exclude", "reason": "población no elegible"},
                }
            }
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
        etiquetar=etiquetar,
    )

    assert result.status == "completed"
    c = result.counts
    assert (c.excluded_ft, c.excluded_ft_human, c.excluded_ft_ai, c.included) == (1, 1, 0, 1)
    assert all(d["human_label"] for d in _ft(ctx).values())  # A0: todo recuperado etiquetado
    assert _ft(ctx)["rec-2"]["human_actor"] == "human:revisora"


def test_rescate_de_no_recuperado_cuenta_como_evaluado(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def rescatar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {
                "records": {
                    "rec-1": {"label": "include", "reason": "cumple"},
                    "rec-2": {"label": "include", "reason": "PDF por préstamo interbibliotecario"},
                }
            }
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_no_disponible(["rec-2"]),
        etiquetar=rescatar,
    )

    c = result.counts
    assert (c.fulltext_sought, c.fulltext_not_retrieved, c.fulltext_rescued) == (2, 0, 1)
    assert (c.fulltext_assessed, c.included) == (2, 2)
    rec2 = _ft(ctx)["rec-2"]
    assert (rec2["fulltext_status"], rec2["votes"], rec2["final_label"]) == (
        "not_retrieved",
        [],
        "include",
    )
    rescate = next(e for e in ctx.ledger.read_all() if e.target == "rec-2")
    assert (rescate.action, rescate.detail["rescue"], rescate.detail["from"]) == (
        "label",
        True,
        None,
    )


def test_no_recuperado_sin_rescate_permite_aprobar(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_no_disponible(["rec-2"]),
    )
    c = result.counts
    assert result.status == "completed"
    assert (c.fulltext_not_retrieved, c.fulltext_rescued, c.fulltext_assessed) == (1, 0, 1)
    assert c.included == 1
    assert _ft(ctx)["rec-2"]["final_label"] is None


def test_16b_razon_humana(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def excluir(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {
                "records": {
                    "rec-1": {"label": "include", "reason": "cumple"},
                    "rec-2": {"label": "exclude", "reason": "diseño no elegible"},
                }
            }
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
        etiquetar=excluir,
    )
    assert result.counts.ft_exclusion_reasons == {"diseño no elegible": 1}
    (excluido,) = _json(ctx, "04_fulltext/excluded.json")
    assert (excluido["record_id"], excluido["reason_source"]) == ("rec-2", "human")
    md = (ctx.run_dir / "deliverable" / "excluidos_texto_completo.md").read_text("utf-8")
    assert "diseño no elegible | humano |" in md


def test_ft_a1_aprobar_en_bloque_deja_la_exclusion_ia_como_ia(tmp_path: Path, proveedor) -> None:
    # D5 en texto completo (seguimiento de la Tarea 24): un humano aprueba en bloque el gate
    # A1 sin etiquetar nada. La exclusión de la IA sigue siendo suya: la cuenta `excluded_ft_ai`,
    # su fila de 16b lleva `reason_source == "ai"` y el ledger no tiene ninguna etiqueta.
    proto = _proto(tmp_path, screening_ft="A1")
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    resultado = correr_hasta(
        protocol,
        proto,
        ctx,
        search_fn=_busqueda_ft,
        # La palabra clave "irrelevante" solo está en el texto completo de rec-2: pasa T/A y la
        # IA lo excluye en FT.
        fetch_fn=_texto(rec_2="Estudio irrelevante."),
    )

    assert resultado.status == "completed"
    c = resultado.counts
    assert (c.excluded_ft, c.excluded_ft_ai, c.excluded_ft_human, c.included) == (1, 1, 0, 1)
    (excluido,) = _json(ctx, "04_fulltext/excluded.json")
    assert (excluido["record_id"], excluido["reason_source"]) == ("rec-2", "ai")
    assert c.ft_exclusion_reasons == {"fuera de alcance": 1}
    rec2 = _ft(ctx)["rec-2"]
    assert (rec2["ensemble_label"], rec2["final_label"]) == ("exclude", "exclude")
    assert (rec2["human_label"], rec2["human_reason"], rec2["human_actor"]) == (None, None, None)
    # Lo único del humano en FT es la aprobación del gate: ni una etiqueta.
    ft_ledger = [e for e in ctx.ledger.read_all() if e.stage == "screening_ft"]
    assert [e.action for e in ft_ledger] == ["approve"]
    assert not [e for e in ctx.ledger.read_all() if e.action == "label" and e.target == "rec-2"]


def test_ft_unclear_resuelto_como_exclude_va_a_16b_y_no_a_extraccion(
    tmp_path: Path, proveedor
) -> None:
    proto = _proto(tmp_path, screening_ft="A1")
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    def resolver(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {"records": {"rec-1": {"label": "exclude", "reason": "no es un estudio"}}}
        return None

    result = correr_hasta(
        protocol,
        proto,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=_texto(rec_1="Resultado dudoso."),
        etiquetar=resolver,
    )

    c = result.counts
    assert result.status == "completed"
    assert (c.excluded_ft, c.excluded_ft_human, c.excluded_ft_ai, c.included) == (1, 1, 0, 1)
    assert [r.record_id for r in result.included] == ["rec-2"]  # solo `include` llega a extracción
    assert set(_json(ctx, "05_extraction/extractions.json")) == {"rec-2"}
    # El `unclear` de la IA quedó como propuesta; la decisión final es la humana.
    rec1 = _ft(ctx)["rec-1"]
    assert (rec1["ensemble_label"], rec1["human_label"], rec1["final_label"]) == (
        "unclear",
        "exclude",
        "exclude",
    )
    assert c.ft_exclusion_reasons == {"no es un estudio": 1}


def test_rescate_etiquetado_exclude_va_a_16b_con_razon_humana(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def rescatar_y_excluir(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {
                "records": {
                    "rec-1": {"label": "include", "reason": "cumple"},
                    "rec-2": {"label": "exclude", "reason": "el PDF muestra otra población"},
                }
            }
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_no_disponible(["rec-2"]),
        etiquetar=rescatar_y_excluir,
    )

    c = result.counts
    # Rescatado = evaluado: ya no es "no recuperado" aunque la decisión sea excluirlo.
    assert (c.fulltext_sought, c.fulltext_not_retrieved, c.fulltext_rescued) == (2, 0, 1)
    assert (c.fulltext_assessed, c.excluded_ft, c.included) == (2, 1, 1)
    assert (c.excluded_ft_human, c.excluded_ft_ai) == (1, 0)
    (excluido,) = _json(ctx, "04_fulltext/excluded.json")
    assert (excluido["record_id"], excluido["reason_source"]) == ("rec-2", "human")
    assert excluido["reason"] == "el PDF muestra otra población"
    assert c.ft_exclusion_reasons == {"el PDF muestra otra población": 1}
    md = (ctx.run_dir / "deliverable" / "excluidos_texto_completo.md").read_text("utf-8")
    assert "el PDF muestra otra población | humano |" in md
    rec2 = _ft(ctx)["rec-2"]
    assert (rec2["fulltext_status"], rec2["human_label"], rec2["final_label"]) == (
        "not_retrieved",
        "exclude",
        "exclude",
    )


def _busqueda_ft3(query: str, n: int) -> list[SearchRecord]:
    return [
        *_busqueda_ft(query, n),
        SearchRecord(record_id="rec-3", title="Otro estudio", source_db="OpenAlex"),
    ][:n]


def test_conteos_ft_cumplen_la_relacion_8(tmp_path: Path, proveedor) -> None:
    # Spec §4.4, relación 8: `fulltext_assessed = fulltext_sought − fulltext_not_retrieved`,
    # y cada no recuperado está rescatado o sin rescatar, nunca en los dos.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def rescatar_uno(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {
                "records": {
                    "rec-1": {"label": "include", "reason": "cumple"},
                    "rec-2": {"label": "include", "reason": "PDF por préstamo"},
                }
            }
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft3,
        fetch_fn=fetch_no_disponible(["rec-2", "rec-3"]),
        etiquetar=rescatar_uno,
    )

    c = result.counts
    assert (c.fulltext_sought, c.fulltext_not_retrieved, c.fulltext_rescued) == (3, 1, 1)
    assert c.fulltext_assessed == c.fulltext_sought - c.fulltext_not_retrieved == 2
    n_no_recuperados = sum(1 for d in _ft(ctx).values() if d["fulltext_status"] == "not_retrieved")
    assert c.fulltext_rescued + c.fulltext_not_retrieved == n_no_recuperados == 2
    # Los evaluados son exactamente los que acabaron incluidos o excluidos.
    assert c.fulltext_assessed == c.included + c.excluded_ft
    assert _ft(ctx)["rec-3"]["final_label"] is None  # sin rescate: nunca llega a extracción
    assert set(_json(ctx, "05_extraction/extractions.json")) == {"rec-1", "rec-2"}


def test_rescate_sin_razon_se_rechaza(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    fetch = fetch_no_disponible(["rec-2"])
    correr_hasta(
        protocol, EXAMPLE, ctx, search_fn=_busqueda_ft, fetch_fn=fetch, parar_en="screening_ft"
    )
    responder_gate(
        ctx.run_dir,
        "screening_ft",
        records={"rec-1": {"label": "include", "reason": "cumple"}, "rec-2": {"label": "include"}},
    )
    with pytest.raises(DecisionFileError, match=r"'rec-2' no se recuperó.*rescate.*`reason`"):
        run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)


def _fetch_transitorio(record_id: str, *, fallos: int):
    """``fetch_fn`` que falla con ``error_http`` las primeras ``fallos`` veces de ``record_id``."""
    llamadas: dict[str, int] = {}

    def fetch(record: SearchRecord) -> FullText:
        llamadas[record.record_id] = llamadas.get(record.record_id, 0) + 1
        if record.record_id == record_id and llamadas[record_id] <= fallos:
            return FullText(text="", available=False, reason="error_http", detail="sin red")
        return fetch_disponible(record)

    return fetch


def test_rescate_de_un_no_recuperado_transitorio_cuenta_como_evaluado(
    tmp_path: Path, proveedor
) -> None:
    # Un `error_http` no se congela en el diario (se reintenta al reanudar), pero el humano
    # puede tener el PDF: se ofrece como rescatable, con un aviso de que es transitorio.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    vista: dict = {}

    def rescatar(stage: str, solicitud: dict) -> dict | None:
        if stage != "screening_ft":
            return None
        vista["solicitud"] = solicitud
        vista["plantilla"] = (ctx.run_dir / stage / "decision.template.yml").read_text("utf-8")
        return {
            "records": {
                "rec-1": {"label": "include", "reason": "cumple"},
                "rec-2": {"label": "include", "reason": "PDF por préstamo interbibliotecario"},
            }
        }

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=_fetch_transitorio("rec-2", fallos=99),
        etiquetar=rescatar,
    )

    assert vista["solicitud"]["rescuable"] == ["rec-2"]
    assert vista["solicitud"]["records"][1]["fulltext_reason"] == "error_http"
    (linea,) = [ln for ln in vista["plantilla"].splitlines() if "no recuperado: error_http" in ln]
    assert "transitorio" in linea and "se reintenta al reanudar" in linea
    assert "sin red" in linea  # y el detalle del fallo
    # El fallo transitorio no está en el diario de recuperación...
    diario = (ctx.run_dir / "04_fulltext" / "retrieval.jsonl").read_text("utf-8")
    assert [json.loads(ln)["record_id"] for ln in diario.splitlines() if ln.strip()] == ["rec-1"]
    # ...pero el rescate lo cuenta como evaluado y llega a la decisión humana de FT.
    c = result.counts
    assert (c.fulltext_sought, c.fulltext_not_retrieved, c.fulltext_rescued) == (2, 0, 1)
    assert (c.fulltext_assessed, c.included) == (2, 2)
    rec2 = _ft(ctx)["rec-2"]
    assert (rec2["fulltext_status"], rec2["human_label"], rec2["final_label"]) == (
        "not_retrieved",
        "include",
        "include",
    )


def test_el_rescate_de_un_transitorio_no_vale_si_al_reanudar_llega_el_texto(
    tmp_path: Path, proveedor
) -> None:
    # El rescate quedó atado al `request_sha256` de cuando rec-2 era «no recuperado». Si al
    # reanudar el texto llega, la solicitud cambia (rec-2 pasa a recuperado y tiene propuesta
    # IA): la decisión vieja no se aplica y el gate vuelve a pausar con la solicitud nueva.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    fetch = _fetch_transitorio("rec-2", fallos=1)  # falla la primera vez, luego responde
    correr_hasta(
        protocol, EXAMPLE, ctx, search_fn=_busqueda_ft, fetch_fn=fetch, parar_en="screening_ft"
    )
    antes = leer_solicitud(ctx.run_dir, "screening_ft")
    assert antes["rescuable"] == ["rec-2"]
    responder_gate(
        ctx.run_dir,
        "screening_ft",
        records={
            "rec-1": {"label": "include", "reason": "cumple"},
            "rec-2": {"label": "include", "reason": "PDF por préstamo interbibliotecario"},
        },
    )

    pausa = run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)

    assert (pausa.status, pausa.stage) == ("paused", "screening_ft")
    assert "otra solicitud" in pausa.message
    despues = leer_solicitud(ctx.run_dir, "screening_ft")
    assert despues["request_sha256"] != antes["request_sha256"]
    assert (despues["rescuable"], despues["must_label"]) == ([], ["rec-1", "rec-2"])
    assert despues["records"][1]["proposal"] == "include"  # ahora tiene voto de la IA
    # No se registró ni se aplicó nada del rescate viejo.
    assert [e for e in ctx.ledger.read_all() if e.stage == "screening_ft"] == []
    assert not (ctx.run_dir / "05_extraction").exists()

    # La revisora decide de nuevo, ya con el texto: rec-2 deja de ser un rescate.
    result = correr_hasta(
        protocol, EXAMPLE, RunContext.open(ctx.run_dir), search_fn=_busqueda_ft, fetch_fn=fetch
    )
    assert result.status == "completed"
    c = result.counts
    assert (c.fulltext_not_retrieved, c.fulltext_rescued, c.fulltext_assessed) == (0, 0, 2)
    rec2 = _ft(ctx)["rec-2"]
    assert (rec2["fulltext_status"], rec2["human_label"], len(rec2["votes"])) == (
        "retrieved",
        "include",
        1,
    )
    etiqueta = next(e for e in ctx.ledger.read_all() if e.target == "rec-2")
    assert etiqueta.detail["rescue"] is False


# ── Funciones puras de FT (gates.py) ────────────────────────────────────


def _decision_ft(
    record_id: str, etiqueta: str | None, *, recuperado: bool = True
) -> ScreeningDecision:
    """Decisión de FT como la deja ``_fulltext``: un voto, o ninguno si no se recuperó."""
    if not recuperado:
        return ScreeningDecision(
            record_id=record_id, phase="fulltext", fulltext_status="not_retrieved"
        )
    return ScreeningDecision(
        record_id=record_id,
        phase="fulltext",
        fulltext_status="retrieved",
        votes=[
            ScreeningVote(
                model="m0",
                label=etiqueta,
                confidence=0.8,
                rationale="razón",
                criteria_violated=["población"] if etiqueta == "exclude" else [],
            )
        ],
        ensemble_label=etiqueta,
        final_label=etiqueta,
    )


def _escenario_ft(motivo: str = "no_disponible", detalle: str | None = "sin PDF en abierto"):
    """``(decisiones, registros, recuperación)``: a propone incluir, b no se recuperó, c es
    ``unclear`` y d propone excluir."""
    decisiones = [
        _decision_ft("c", "unclear"),
        _decision_ft("a", "include"),
        _decision_ft("b", None, recuperado=False),
        _decision_ft("d", "exclude"),
    ]
    recuperacion = {
        "a": RetrievalOutcome(available=True, source_url="https://example.org/a"),
        "b": RetrievalOutcome(available=False, reason=motivo, detail=detalle),
        "c": RetrievalOutcome(available=True),
        "d": RetrievalOutcome(available=True),
    }
    return decisiones, _registros("a", "b", "c", "d"), recuperacion


def test_ft_payload_a0_pide_etiquetar_cada_recuperado_y_ofrece_los_no_recuperados() -> None:
    decisiones, registros, recuperacion = _escenario_ft()

    payload = ft_payload(
        decisions=decisiones, records=registros, retrieval=recuperacion, autonomy="A0"
    )

    assert payload["mode"] == "label_all"
    assert (payload["n_sought"], payload["n_retrieved"], payload["n_not_retrieved"]) == (4, 3, 1)
    assert payload["must_label"] == ["a", "c", "d"]  # todos los recuperados, no el no recuperado
    assert payload["must_resolve"] == ["c"]
    assert payload["rescuable"] == ["b"]
    assert [r["record_id"] for r in payload["records"]] == ["a", "b", "c", "d"]
    assert payload["records"][1] == {
        "record_id": "b",
        "title": "Título b",
        "year": 2020,
        "doi": "10.1/b",
        "fulltext": "not_retrieved",
        "fulltext_reason": "no_disponible",
        "fulltext_source_url": None,
        "proposal": None,
        "confidence": None,
        "rationale": None,
        "criteria_violated": [],
    }
    d = payload["records"][3]
    assert (d["proposal"], d["confidence"], d["rationale"], d["criteria_violated"]) == (
        "exclude",
        0.8,
        "razón",
        ["población"],
    )
    assert payload["records"][0]["fulltext_source_url"] == "https://example.org/a"


def test_ft_payload_a1_solo_obliga_a_resolver_los_unclear() -> None:
    decisiones, registros, recuperacion = _escenario_ft()

    payload = ft_payload(
        decisions=decisiones, records=registros, retrieval=recuperacion, autonomy="A1"
    )

    assert payload["mode"] == "exceptions"
    assert (payload["must_label"], payload["must_resolve"]) == (["c"], ["c"])
    assert payload["rescuable"] == ["b"]


def test_ft_payload_sin_el_registro_ni_la_recuperacion_no_rompe() -> None:
    fila = ft_payload(
        decisions=[_decision_ft("a", "include")], records=[], retrieval={}, autonomy="A0"
    )["records"][0]

    assert (fila["title"], fila["year"], fila["doi"]) == ("a", None, None)
    assert (fila["fulltext_reason"], fila["fulltext_source_url"]) == (None, None)


def test_ft_policy_a1_obliga_a_los_unclear_y_ofrece_rescatar_con_razon() -> None:
    decisiones, registros, recuperacion = _escenario_ft()

    politica = ft_policy(
        decisions=decisiones, records=registros, retrieval=recuperacion, autonomy="A1"
    )

    assert (politica.must_label, politica.must_resolve) == (frozenset("c"), frozenset("c"))
    assert politica.rescue_ids == frozenset("b")
    assert politica.reason_on_exclude is True
    assert [h.record_id for h in politica.hints] == ["a", "b", "c", "d"]
    hints = {h.record_id: h for h in politica.hints}
    assert (hints["b"].proposal, hints["b"].title) == (None, "Título b")
    # Un motivo permanente: el fallo se cuenta tal cual, sin prometer reintentos.
    assert hints["b"].note == "no recuperado: no_disponible (sin PDF en abierto)"
    assert hints["c"].proposal == "unclear"
    assert "m0: unclear (0.80)" in hints["c"].note


def test_ft_policy_a0_obliga_a_etiquetar_cada_recuperado() -> None:
    decisiones, registros, recuperacion = _escenario_ft()

    politica = ft_policy(
        decisions=decisiones, records=registros, retrieval=recuperacion, autonomy="A0"
    )

    assert politica.must_label == frozenset("acd")
    assert politica.must_resolve == frozenset("c")


@pytest.mark.parametrize("motivo", ["error_http", "sin_httpx"])
def test_ft_policy_avisa_de_que_un_no_recuperado_transitorio_se_reintenta(motivo: str) -> None:
    decisiones, registros, recuperacion = _escenario_ft(motivo, "sin red")

    politica = ft_policy(
        decisions=decisiones, records=registros, retrieval=recuperacion, autonomy="A0"
    )

    nota = next(h.note for h in politica.hints if h.record_id == "b")
    assert nota.startswith(f"no recuperado: {motivo}")
    assert "transitorio" in nota and "se reintenta al reanudar" in nota
    assert "habrá que decidir de nuevo" in nota
    assert "sin red" in nota
    assert politica.rescue_ids == frozenset("b")  # se ofrece rescatar igualmente


# ── Extracción y RoB: aprobación por etapa con la tabla completa (D1) ─────


def test_extraccion_y_rob_payload_con_tabla_y_hash_del_artefacto(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, EXAMPLE, ctx, parar_en="extraccion", **kwargs)

    solicitud = leer_solicitud(ctx.run_dir, "extraccion")
    extracciones = _json(ctx, "05_extraction/extractions.json")
    assert solicitud["n_studies"] == 2
    assert [s["record_id"] for s in solicitud["studies"]] == ["rec-1", "rec-2"]
    for estudio in solicitud["studies"]:
        campos = extracciones[estudio["record_id"]]["fields"]
        assert estudio["fields"] == {
            k: {x: v[x] for x in ("value", "source_quote", "status", "confidence")}
            for k, v in campos.items()
        }
    assert set(solicitud["second_extraction"]) == {
        "n_studies",
        "n_field_pairs",
        "value_agreement",
        "presence_kappa",
    }
    assert solicitud["artifact_sha256"] == canonical_sha256(extracciones)

    correr_hasta(protocol, EXAMPLE, RunContext.open(ctx.run_dir), parar_en="rob", **kwargs)
    solicitud = leer_solicitud(ctx.run_dir, "rob")
    evaluaciones = _json(ctx, "07_rob/assessments.json")
    assert (solicitud["tool"], solicitud["n_studies"]) == ("RoB2", 2)
    rec1 = solicitud["studies"][0]
    assert rec1["overall"] == evaluaciones["rec-1"]["overall"]
    assert len(rec1["domains"]) == len(evaluaciones["rec-1"]["domains"])
    assert solicitud["artifact_sha256"] == canonical_sha256(evaluaciones)


class _ProveedorConTablas(ScriptedProvider):
    """Rellena el formulario de extracción y los dominios de RoB (el guion base los deja vacíos).

    Con ``ScriptedProvider`` a secas las tablas salen sin campos ni dominios y comprobarlas
    sería vacuo. ``cita``, ``razon`` y ``apoyo`` son el texto libre que llega a la solicitud.
    """

    def __init__(self, *, cita: str = "cita", razon: str = "razón", apoyo: str = "apoyo") -> None:
        super().__init__()
        self.cita, self.razon, self.apoyo = cita, razon, apoyo

    def structured(self, req, schema):
        obj, meta = super().structured(req, schema)
        if "fields" in schema.model_fields:  # extracción
            obj = schema.model_validate(
                {
                    "fields": [
                        {
                            "key": "diseno",
                            "value": "ensayo aleatorizado",
                            "source_quote": self.cita,
                            "found": True,
                            "confidence": 0.9,
                        },
                        {"key": "metrica_recall", "value": None, "found": False},
                    ]
                }
            )
        elif "domains" in schema.model_fields:  # riesgo de sesgo
            obj = schema.model_validate(
                {
                    "domains": [
                        {
                            "domain": "Proceso de aleatorización",
                            "judgment": "low",
                            "rationale": self.razon,
                            "support_quote": self.apoyo,
                        },
                        {"domain": "Datos de resultado faltantes", "judgment": "some_concerns"},
                    ],
                    "overall": "some_concerns",
                }
            )
        else:
            return obj, meta
        return obj, self._meta(req, obj.model_dump_json())


def _correr_hasta_pausa(protocol, ctx: RunContext, parar_en: str) -> None:
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    resultado = correr_hasta(protocol, EXAMPLE, ctx, parar_en=parar_en, **kwargs)
    assert (resultado.status, resultado.stage) == ("paused", parar_en)


def test_extraccion_y_rob_payload_listan_campos_y_dominios_reales(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: _ProveedorConTablas())
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    _correr_hasta_pausa(protocol, ctx, "extraccion")

    solicitud = leer_solicitud(ctx.run_dir, "extraccion")
    assert solicitud["studies"][0] == {
        "record_id": "rec-1",
        "title": "LLM screening",
        "fields": {
            "diseno": {
                "value": "ensayo aleatorizado",
                "source_quote": "cita",
                "status": "needs_review",
                "confidence": 0.9,
            },
            "metrica_recall": {
                "value": None,
                "source_quote": None,
                "status": "not_found",
                "confidence": 0.0,
            },
        },
    }
    acuerdo = _json(ctx, "05_extraction/agreement.json")
    assert solicitud["second_extraction"] == {
        k: acuerdo[k] for k in ("n_studies", "n_field_pairs", "value_agreement", "presence_kappa")
    }

    _correr_hasta_pausa(protocol, RunContext.open(ctx.run_dir), "rob")
    solicitud = leer_solicitud(ctx.run_dir, "rob")
    assert solicitud["studies"][1] == {
        "record_id": "rec-2",
        "title": "Active learning",
        "overall": "some_concerns",
        "domains": [
            {
                "domain": "Proceso de aleatorización",
                "judgment": "low",
                "rationale": "razón",
                "support_quote": "apoyo",
            },
            {
                "domain": "Datos de resultado faltantes",
                "judgment": "some_concerns",
                "rationale": "",
                "support_quote": None,
            },
        ],
    }


def test_solicitudes_de_extraccion_y_rob_con_saltos_unicode_conservan_su_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Una cita con U+0085 (mojibake de «…») y U+2028 y una razón con U+2029 llegan al
    # review_request.yml por `dump_yaml`: leído de vuelta, el fichero tiene que dar el mismo
    # `request_sha256`, y `artifact_sha256` el hash del JSON que quedó en disco (no el de los
    # objetos en memoria), o el auditor no podría verificar lo que el humano aprobó.
    cita = f"se asignó{chr(0x85)} al azar{chr(0x2028)}por bloques"
    razon = f"razón{chr(0x2029)}larga"
    apoyo = f"apoyo{chr(0x85)}"
    monkeypatch.setattr(
        pipeline_mod,
        "build_provider",
        lambda _cfg: _ProveedorConTablas(cita=cita, razon=razon, apoyo=apoyo),
    )
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    for etapa, artefacto in (
        ("extraccion", "05_extraction/extractions.json"),
        ("rob", "07_rob/assessments.json"),
    ):
        _correr_hasta_pausa(
            protocol, RunContext.open(ctx.run_dir) if etapa == "rob" else ctx, etapa
        )
        solicitud = leer_solicitud(ctx.run_dir, etapa)
        sin_hash = {k: v for k, v in solicitud.items() if k != "request_sha256"}
        assert canonical_sha256(sin_hash) == solicitud["request_sha256"], etapa
        assert solicitud["artifact_sha256"] == canonical_sha256(_json(ctx, artefacto)), etapa
        if etapa == "extraccion":
            assert solicitud["studies"][0]["fields"]["diseno"]["source_quote"] == cita
        else:
            dominio = solicitud["studies"][0]["domains"][0]
            assert (dominio["rationale"], dominio["support_quote"]) == (razon, apoyo)


def test_records_en_extraccion_es_error(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
        parar_en="extraccion",
    )
    responder_gate(ctx.run_dir, "extraccion", records={"rec-1": {"label": "exclude"}})
    with pytest.raises(DecisionFileError, match="`records` solo vale"):
        run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)


# ── Extracción y RoB: un solo dict se escribe y se hashea ─────────────────


def _extraccion(study_id: str, valor: str | None = "ensayo") -> ExtractionRecord:
    return ExtractionRecord(
        study_id=study_id,
        fields={
            "diseno": ExtractionField(
                value=valor, source_quote="cita", confidence=0.9, status="verified"
            )
        },
    )


class _Registro(BaseModel):
    """Modelo cuyo volcado en modo Python y en modo JSON no coinciden (``datetime``)."""

    cuando: datetime


def test_dump_artifact_es_el_json_que_se_escribe_y_se_hashea() -> None:
    # El artefacto que se escribe en disco y el que se hashea en `artifact_sha256` salen del
    # mismo dict: en modo JSON, de modo que lo que hashea la solicitud es lo que el auditor
    # lee de vuelta del fichero (revisión de la Tarea 25).
    modelos = {"a": _Registro(cuando=datetime(2026, 10, 4, 12, 30, tzinfo=UTC))}

    volcado = dump_artifact(modelos)

    assert volcado == {"a": {"cuando": "2026-10-04T12:30:00Z"}}
    en_disco = json.loads(json.dumps(volcado, ensure_ascii=False, indent=2))
    assert canonical_sha256(volcado) == canonical_sha256(en_disco)


def test_artifact_sha256_de_extraccion_y_rob_es_el_hash_de_dump_artifact() -> None:
    extracciones = {"rec-1": _extraccion("rec-1")}
    evaluaciones = {
        "rec-1": RoBAssessment(
            study_id="rec-1",
            tool="RoB2",
            domains=[RoBDomain(domain="Aleatorización", judgment="low")],
            overall="low",
        )
    }

    solicitud = extraction_payload(
        included=_registros("rec-1"), extractions=extracciones, agreement=None
    )
    assert solicitud["artifact_sha256"] == canonical_sha256(dump_artifact(extracciones))
    solicitud = rob_payload(tool="RoB2", included=_registros("rec-1"), assessments=evaluaciones)
    assert solicitud["artifact_sha256"] == canonical_sha256(dump_artifact(evaluaciones))


def test_extraction_payload_sin_acuerdo_no_lleva_segunda_extraccion() -> None:
    solicitud = extraction_payload(
        included=_registros("rec-1"),
        extractions={"rec-1": _extraccion("rec-1")},
        agreement=None,
    )

    assert solicitud["second_extraction"] is None
    assert solicitud["n_studies"] == 1


def test_extraction_payload_con_acuerdo_lo_resume_sin_el_recuento_interno() -> None:
    acuerdo = ExtractionAgreement(
        n_studies=1, n_field_pairs=4, n_value_match=3, value_agreement=0.75, presence_kappa=0.5
    )

    solicitud = extraction_payload(
        included=_registros("rec-1"),
        extractions={"rec-1": _extraccion("rec-1")},
        agreement=acuerdo,
    )

    assert solicitud["second_extraction"] == {
        "n_studies": 1,
        "n_field_pairs": 4,
        "value_agreement": 0.75,
        "presence_kappa": 0.5,
    }


def test_extraction_y_rob_payload_sin_incluidos_no_rompen() -> None:
    solicitud = extraction_payload(included=[], extractions={}, agreement=None)
    assert (solicitud["n_studies"], solicitud["studies"]) == (0, [])
    assert solicitud["second_extraction"] is None
    assert solicitud["artifact_sha256"] == canonical_sha256({})

    solicitud = rob_payload(tool="RoB2", included=[], assessments={})
    assert (solicitud["tool"], solicitud["n_studies"], solicitud["studies"]) == ("RoB2", 0, [])
    assert solicitud["artifact_sha256"] == canonical_sha256({})


# ── Gate final con citas marcadas (M5, D8) ───────────────────────────────


@pytest.fixture()
def con_cita_inventada(monkeypatch: pytest.MonkeyPatch) -> ScriptedProvider:
    """Síntesis con una cita real y otra que no está en el corpus (``[2019]``)."""
    guion = ScriptedProvider(sintesis="La IA reduce el cribado [rec-1]. Lo confirma [2019].")
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: guion)
    return guion


def _proto_reporte(tmp_path: Path, reporte: str = "A2") -> Path:
    proto = _proto(tmp_path, reporte=reporte)  # con A2 el gate final ni siquiera pausaría
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["grounding"] = "existence"  # solo se comprueba que el id esté en el corpus
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), "utf-8")
    return proto


def _manifest(ctx: RunContext) -> dict:
    return yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))


def test_gate_final_forzado_a_humano_si_hallucination_flagged(
    tmp_path: Path, con_cita_inventada
) -> None:
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    result = run_pipeline(
        protocol,
        proto,
        ctx,
        auto_approve=True,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
    )

    assert (result.status, result.stage) == ("paused", "reporte")
    assert "exige una decisión humana" in result.message
    solicitud = leer_solicitud(ctx.run_dir, "reporte")
    assert solicitud["autonomy"] == "A1"  # A2 declarada, A1 efectiva
    assert (solicitud["forced_human"], solicitud["forced_reason"]) == (
        True,
        "hallucination_flagged",
    )
    (marca,) = solicitud["verification"]["flagged"]
    assert (marca["cited_id"], solicitud["must_adjudicate"]) == ("2019", [marca["index"]])
    assert solicitud["verification"]["mode"] == "existence"
    manifest = yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["final_gate"] == {"forced_human": True, "reason": "hallucination_flagged"}
    assert manifest["autonomy_effective"]["reporte"] == "A1"
    assert not [e for e in ctx.ledger.read_all() if e.stage == "reporte"]


def test_reporte_con_citas_adjudicadas_se_completa(tmp_path: Path, con_cita_inventada) -> None:
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, proto, ctx, parar_en="reporte", **kwargs)
    (indice,) = leer_solicitud(ctx.run_dir, "reporte")["must_adjudicate"]

    responder_gate(
        ctx.run_dir,
        "reporte",
        flags={str(indice): {"verdict": "false_positive", "reason": "[2019] es un año"}},
    )
    result = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)

    assert result.status == "completed"
    reporte = [e for e in ctx.ledger.read_all() if e.stage == "reporte"]
    assert [(e.action, e.target) for e in reporte] == [
        ("flag_review", f"flag:{indice}"),
        ("approve", None),
    ]
    resumen = summarize_gates(ctx.ledger.read_all())["reporte"]
    assert (resumen.forced_human, resumen.n_flag_reviews) == (True, 1)
    assert read_run_info(ctx.run_dir).status == "completed"


def test_el_indice_de_la_cita_es_su_posicion_en_checks_y_sobrevive_a_reanudar_sin_decision_yml(
    tmp_path: Path, con_cita_inventada
) -> None:
    # `index` es la posición en `verification.json.checks` (no entre las marcadas): aquí la
    # cita inventada es la 2.ª de dos, índice 1. Al reanudar sin ningún `decision.yml` (las
    # adjudicaciones salen del ledger) la solicitud sale idéntica, con los mismos índices y el
    # mismo `request_sha256`, y no se registra nada nuevo.
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, proto, ctx, parar_en="reporte", **kwargs)
    solicitud = leer_solicitud(ctx.run_dir, "reporte")
    (indice,) = solicitud["must_adjudicate"]
    cita = _json(ctx, "06_synthesis/verification.json")["checks"][indice]
    assert (indice, cita["cited_id"]) == (1, "2019")
    responder_gate(
        ctx.run_dir,
        "reporte",
        flags={str(indice): {"verdict": "false_positive", "reason": "[2019] es un año"}},
    )
    completa = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)
    assert completa.status == "completed"
    ledger = ctx.ledger.read_all()

    for decision in ctx.run_dir.glob("*/decision.yml"):
        decision.unlink()
    result = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)

    assert (result.status, result.stage) == ("completed", None)
    assert leer_solicitud(ctx.run_dir, "reporte") == solicitud
    assert ctx.ledger.read_all() == ledger
    assert read_run_info(ctx.run_dir).status == "completed"


def test_reporte_con_citas_marcadas_no_se_aprueba_sin_adjudicar_pero_se_puede_rechazar(
    tmp_path: Path, con_cita_inventada
) -> None:
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, proto, ctx, parar_en="reporte", **kwargs)

    responder_gate(ctx.run_dir, "reporte")  # aprueba sin adjudicar la cita marcada
    with pytest.raises(DecisionFileError, match="cita 1"):
        run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)
    assert not [e for e in ctx.ledger.read_all() if e.stage == "reporte"]

    responder_gate(ctx.run_dir, "reporte", approved=False, reason="[2019] es una cita inventada")
    result = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)

    assert (result.status, result.stage) == ("rejected", "reporte")
    assert [(e.action, e.target) for e in ctx.ledger.read_all() if e.stage == "reporte"] == [
        ("reject", None)
    ]
    assert read_run_info(ctx.run_dir).status == "rejected"
    manifest = _manifest(ctx)
    assert manifest["run"]["status"] == "rejected"
    assert manifest["final_gate"] == {"forced_human": True, "reason": "hallucination_flagged"}


def test_solicitud_del_reporte_con_saltos_unicode_en_la_cita_conserva_su_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # El fragmento marcado viene de la síntesis del LLM: con U+0085 (mojibake de «…»), U+2028 y
    # U+2029 llega a `review_request.yml` por `dump_yaml` y leído de vuelta tiene que dar el
    # mismo `request_sha256`; si no, el gate no convergería al reanudar.
    texto = (
        f"La IA reduce el cribado [rec-1]{chr(0x2028)} y se confirma{chr(0x85)} "
        f"[2019]{chr(0x2029)} fin."
    )
    monkeypatch.setattr(
        pipeline_mod, "build_provider", lambda _cfg: ScriptedProvider(sintesis=texto)
    )
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    pausa = correr_hasta(
        protocol,
        proto,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
        parar_en="reporte",
    )

    assert (pausa.status, pausa.stage) == ("paused", "reporte")
    solicitud = leer_solicitud(ctx.run_dir, "reporte")
    sin_hash = {k: v for k, v in solicitud.items() if k != "request_sha256"}
    assert canonical_sha256(sin_hash) == solicitud["request_sha256"]
    (marca,) = solicitud["verification"]["flagged"]
    assert (marca["cited_id"], chr(0x85) in marca["claim"], chr(0x2028) in marca["claim"]) == (
        "2019",
        True,
        True,
    )
    plantilla = yaml.safe_load(
        (ctx.run_dir / "reporte" / "decision.template.yml").read_text(encoding="utf-8")
    )
    assert plantilla["flags"] == {str(marca["index"]): {"verdict": None, "reason": None}}


@pytest.mark.parametrize("declarada", ["A1", "A2"])
def test_manifest_refleja_el_gate_final_forzado_y_se_reescribe_al_reanudar(
    tmp_path: Path, con_cita_inventada, declarada: str
) -> None:
    # Declarada A1 (ya pausaba) o A2 (no pausaría): con citas marcadas la autonomía efectiva
    # es A1 y `forced_human` es verdadero, en la pausa y también en el manifest que reescribe la
    # reanudación (``write_manifest`` va después del gate final).
    proto = _proto_reporte(tmp_path, declarada)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, proto, ctx, parar_en="reporte", **kwargs)

    pausa = _manifest(ctx)
    assert pausa["run"]["status"] == "paused"
    assert pausa["final_gate"] == {"forced_human": True, "reason": "hallucination_flagged"}
    assert pausa["autonomy_effective"]["reporte"] == "A1"
    assert pausa["verification"]["hallucination_flagged"] is True

    (indice,) = leer_solicitud(ctx.run_dir, "reporte")["must_adjudicate"]
    responder_gate(
        ctx.run_dir,
        "reporte",
        flags={str(indice): {"verdict": "false_positive", "reason": "[2019] es un año"}},
    )
    assert run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs).status == (
        "completed"
    )

    final = _manifest(ctx)
    assert final["run"]["status"] == "completed"
    assert final["final_gate"] == {"forced_human": True, "reason": "hallucination_flagged"}
    assert final["autonomy_effective"] == pausa["autonomy_effective"]
    assert final["autonomy_effective"]["reporte"] == "A1"
    assert final["autonomy_effective"]["screening_ta"] == protocol.autonomy_for("screening_ta")


@pytest.mark.parametrize("declarada", ["A1", "A2"])
def test_manifest_sin_citas_marcadas_conserva_la_autonomia_declarada(
    tmp_path: Path, proveedor, declarada: str
) -> None:
    proto = _proto_reporte(tmp_path, declarada)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    result = correr_hasta(protocol, proto, ctx, search_fn=_busqueda_ft, fetch_fn=fetch_disponible)

    assert result.status == "completed"
    assert result.hallucination_flagged is False
    manifest = _manifest(ctx)
    assert manifest["final_gate"] == {"forced_human": False, "reason": None}
    assert manifest["autonomy_effective"]["reporte"] == declarada
    if declarada == "A1":  # con A2 el gate no pide nada, así que no hay solicitud que leer
        solicitud = leer_solicitud(ctx.run_dir, "reporte")
        assert (solicitud["forced_human"], solicitud["forced_reason"]) == (False, None)
        assert (solicitud["must_adjudicate"], solicitud["verification"]["flagged"]) == ([], [])
        assert solicitud["verification"]["hallucination_flagged"] is False


@pytest.mark.parametrize(
    ("declarada", "forzado", "efectiva"),
    [
        ("A0", True, "A0"),  # A0 y A1 ya piden humano: no se tocan
        ("A1", True, "A1"),
        ("A2", True, "A1"),
        ("A3", True, "A1"),
        ("A2", False, "A2"),
        ("A3", False, "A3"),
    ],
)
def test_autonomy_effective_solo_baja_a_a1_un_reporte_a2_o_a3_forzado(
    declarada: str, forzado: bool, efectiva: str
) -> None:
    protocol = load_protocol(EXAMPLE)
    protocol = protocol.model_copy(update={"autonomy": {**protocol.autonomy, "reporte": declarada}})

    resultado = pipeline_mod._autonomy_effective(protocol, forced_human=forzado)

    assert resultado["reporte"] == efectiva
    assert set(resultado) == {"screening_ta", "screening_ft", "extraccion", "rob", "reporte"}
    otros = {g: a for g, a in resultado.items() if g != "reporte"}
    assert otros == {g: protocol.autonomy_for(g) for g in otros}


@pytest.mark.parametrize(
    ("declarada", "forzado", "efectiva"),
    [
        ("A0", True, "A0"),
        ("A1", True, "A1"),
        ("A2", True, "A1"),
        ("A3", True, "A1"),
        ("A2", False, "A2"),
        ("A3", False, "A3"),
    ],
)
def test_effective_autonomy_es_la_unica_regla_del_a2_a3_forzado_a_a1(
    declarada: str, forzado: bool, efectiva: str
) -> None:
    # La usan `review_gate` (lo que se pide y se registra) y `_autonomy_effective` (lo que
    # dice el manifiesto): una sola regla, para que no puedan separarse.
    assert effective_autonomy(declarada, forced_human=forzado) == efectiva


def test_reporte_a3_declarado_se_fuerza_a_a1_y_solo_se_completa_con_adjudicacion_humana(
    tmp_path: Path, con_cita_inventada
) -> None:
    proto = _proto_reporte(tmp_path, "A3")  # A3 no pausaría, no pediría humano: M5 lo exige
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}

    pausa = run_pipeline(protocol, proto, ctx, auto_approve=True, **kwargs)  # ni --auto-approve

    assert (pausa.status, pausa.stage) == ("paused", "reporte")
    solicitud = leer_solicitud(ctx.run_dir, "reporte")
    assert (solicitud["autonomy"], solicitud["forced_human"]) == ("A1", True)
    assert not [e for e in ctx.ledger.read_all() if e.stage == "reporte"]  # ni auto-proceed
    assert _manifest(ctx)["autonomy_effective"]["reporte"] == "A1"

    (indice,) = solicitud["must_adjudicate"]
    responder_gate(
        ctx.run_dir,
        "reporte",
        flags={str(indice): {"verdict": "false_positive", "reason": "[2019] es un año"}},
    )
    result = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)

    assert (result.status, result.stage) == ("completed", None)
    reporte = [e for e in ctx.ledger.read_all() if e.stage == "reporte"]
    assert [(e.action, e.autonomy) for e in reporte] == [("flag_review", "A1"), ("approve", "A1")]
    resumen = summarize_gates(ctx.ledger.read_all())["reporte"]
    assert (resumen.actor, resumen.forced_human, resumen.n_flag_reviews) == (
        "human:revisora",
        True,
        1,
    )


def test_reporte_forzado_rechazado_y_despues_aprobado_adjudicando_queda_en_el_ledger_d14(
    tmp_path: Path, con_cita_inventada
) -> None:
    # D14: rechazar el reporte no cierra la corrida para siempre; se puede reanudar y aprobar
    # adjudicando la cita. Las tres decisiones quedan en el ledger, en orden, y la efectiva es
    # la última (un reductor, el mismo del auditor).
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, proto, ctx, parar_en="reporte", **kwargs)
    (indice,) = leer_solicitud(ctx.run_dir, "reporte")["must_adjudicate"]

    responder_gate(ctx.run_dir, "reporte", approved=False, reason="[2019] parece inventada")
    rechazado = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)
    assert (rechazado.status, rechazado.stage) == ("rejected", "reporte")
    assert read_run_info(ctx.run_dir).status == "rejected"

    responder_gate(
        ctx.run_dir,
        "reporte",
        flags={str(indice): {"verdict": "false_positive", "reason": "[2019] es un año"}},
    )
    result = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)

    assert (result.status, result.stage) == ("completed", None)
    assert read_run_info(ctx.run_dir).status == "completed"
    reporte = [e for e in ctx.ledger.read_all() if e.stage == "reporte"]
    assert [(e.action, e.target) for e in reporte] == [
        ("reject", None),
        ("flag_review", f"flag:{indice}"),
        ("approve", None),
    ]
    resumen = summarize_gates(ctx.ledger.read_all())["reporte"]
    assert (resumen.action, resumen.forced_human, resumen.n_flag_reviews) == ("approve", True, 1)
    manifest = _manifest(ctx)
    assert manifest["run"]["status"] == "completed"
    assert manifest["final_gate"] == {"forced_human": True, "reason": "hallucination_flagged"}
    # El entregable se escribe antes del gate final: no arrastra como decisión el rechazo
    # anterior (que ya no es la efectiva), el reporte figura pendiente (M13).
    traice = _entregable(ctx, "checklist_traice.md")
    assert "- reporte (A1): pendiente de la decisión final · exige decisión humana" in traice
    assert "rechazado" not in traice
    assert "Reporte final: pendiente de la decisión final (autonomía A1) — exige" in _entregable(
        ctx, "metodologia.md"
    )


def _editar_diario_de_verificacion(ctx: RunContext, *, marcada: bool) -> None:
    """Fuerza ``hallucination_flagged`` en el diario de la verificación (edición a mano)."""
    ruta = ctx.run_dir / "06_synthesis" / "verification.jsonl"
    (linea,) = [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]
    linea["output"]["hallucination_flagged"] = marcada
    ruta.write_text(json.dumps(linea, ensure_ascii=False) + "\n", encoding="utf-8")


def test_diario_editado_a_no_marcado_con_citas_marcadas_sigue_forzando_humano(
    tmp_path: Path, con_cita_inventada
) -> None:
    # El gate se fuerza por las citas marcadas (las que hay que adjudicar), no por la bandera
    # del diario: editada a `false` con una cita marcada daba `forced_human: false` y un
    # `must_adjudicate` no vacío, y con `reporte` en A2 el gate no pausaba.
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, proto, ctx, parar_en="reporte", **kwargs)
    antes = leer_solicitud(ctx.run_dir, "reporte")
    _editar_diario_de_verificacion(ctx, marcada=False)

    pausa = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)

    assert (pausa.status, pausa.stage) == ("paused", "reporte")
    assert pausa.hallucination_flagged is True
    # verification.json (que lee el auditor) no contradice al gate: se reescribe recalculada.
    assert _json(ctx, "06_synthesis/verification.json")["hallucination_flagged"] is True
    solicitud = leer_solicitud(ctx.run_dir, "reporte")
    assert (solicitud["autonomy"], solicitud["forced_human"]) == ("A1", True)
    assert solicitud["must_adjudicate"] == antes["must_adjudicate"] != []
    assert solicitud["request_sha256"] == antes["request_sha256"]
    manifest = _manifest(ctx)
    assert manifest["final_gate"] == {"forced_human": True, "reason": "hallucination_flagged"}
    assert manifest["autonomy_effective"]["reporte"] == "A1"
    assert not [e for e in ctx.ledger.read_all() if e.stage == "reporte"]


def test_diario_editado_a_marcado_sin_citas_marcadas_no_fuerza_humano(
    tmp_path: Path, proveedor
) -> None:
    # Al revés: una bandera `true` sin ninguna cita marcada no deja un gate forzado con nada
    # que adjudicar. Reporte en A1 (pausa igualmente): la solicitud no pide adjudicar nada.
    proto = _proto_reporte(tmp_path, "A1")
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, proto, ctx, parar_en="reporte", **kwargs)
    antes = leer_solicitud(ctx.run_dir, "reporte")
    assert antes["forced_human"] is False
    _editar_diario_de_verificacion(ctx, marcada=True)

    pausa = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)

    assert (pausa.status, pausa.stage, pausa.hallucination_flagged) == ("paused", "reporte", False)
    solicitud = leer_solicitud(ctx.run_dir, "reporte")
    assert (solicitud["forced_human"], solicitud["must_adjudicate"]) == (False, [])
    assert solicitud["request_sha256"] == antes["request_sha256"]
    assert _json(ctx, "06_synthesis/verification.json")["hallucination_flagged"] is False
    assert _manifest(ctx)["final_gate"] == {"forced_human": False, "reason": None}


def _verificacion(*checks: CitationCheck) -> VerificationReport:
    informe = VerificationReport(stage="reporte", checks=list(checks))
    informe.recompute_flag()
    return informe


def _cita(
    id_: str, *, existe: bool = True, respaldada: bool = True, claim: str = "afirmación"
) -> CitationCheck:
    return CitationCheck(
        claim=claim,
        cited_id=id_,
        exists_in_corpus=existe,
        grounded=respaldada,
        note=None if existe and respaldada else f"nota {id_}",
    )


def test_report_payload_indexa_por_posicion_en_checks_y_acota_la_afirmacion() -> None:
    larga = "x" * 500
    verificacion = _verificacion(
        _cita("a"),
        _cita("b", existe=False, respaldada=False, claim=larga),
        _cita("c"),
        _cita("d", respaldada=False),
    )

    solicitud = report_payload(
        included=_registros("a", "c"),
        verification=verificacion,
        documento="# Documento\n",
        grounding_mode="embedder",
        forced_human=True,
    )

    assert solicitud["forced_human"] is True
    assert solicitud["forced_reason"] == "hallucination_flagged"
    assert (solicitud["n_included"], solicitud["included"]) == (2, ["a", "c"])
    assert solicitud["must_adjudicate"] == [1, 3]
    assert solicitud["documento_sha256"] == sha256_text("# Documento\n")
    resumen = solicitud["verification"]
    assert (resumen["mode"], resumen["n_checks"], resumen["n_flagged"]) == ("embedder", 4, 2)
    assert resumen["hallucination_flagged"] is True
    assert [(m["index"], m["cited_id"], m["note"]) for m in resumen["flagged"]] == [
        (1, "b", "nota b"),
        (3, "d", "nota d"),
    ]
    assert resumen["flagged"][0]["claim"] == "x" * 300


def test_report_payload_sin_marcas_ni_fuerza_no_pide_adjudicar_nada() -> None:
    solicitud = report_payload(
        included=_registros("a"),
        verification=_verificacion(_cita("a")),
        documento="doc",
        grounding_mode="existence",
        forced_human=False,
    )

    assert (solicitud["forced_human"], solicitud["forced_reason"]) == (False, None)
    assert solicitud["must_adjudicate"] == []
    assert solicitud["verification"]["flagged"] == []
    assert solicitud["verification"]["n_flagged"] == 0
    assert solicitud["verification"]["hallucination_flagged"] is False


def test_report_policy_es_none_sin_marcas_y_lleva_los_indices_de_checks_si_las_hay() -> None:
    assert report_policy(_verificacion(_cita("a"), _cita("b"))) is None
    assert report_policy(_verificacion()) is None

    politica = report_policy(
        _verificacion(_cita("a"), _cita("b", existe=False, respaldada=False, claim="y" * 400))
    )

    assert politica == FlagPolicy(
        flagged=(FlaggedClaim(1, "b", "y" * 300, "nota b"),),
    )


# ── trAIce y métodos con lo que pasó de verdad (M13) ──────────────────────


def _entregable(ctx: RunContext, nombre: str) -> str:
    return (ctx.run_dir / "deliverable" / nombre).read_text(encoding="utf-8")


def test_traice_autonomia_efectiva_y_actores_reales(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    humano = RunContext(protocol.slug, tmp_path, "HUMANO")
    correr_hasta(protocol, EXAMPLE, humano, search_fn=_busqueda_ft, fetch_fn=fetch_disponible)
    traice = _entregable(humano, "checklist_traice.md")
    assert "checkpoints HITL registrados" not in traice  # el texto fijo de antes
    assert "- screening_ta (A1): aprobado por humano (human:revisora)" in traice
    assert (
        "- screening_ft (A0): aprobado por humano (human:revisora) · 2 etiqueta(s) por registro"
        in traice
    )
    # Se escribe antes del gate final: ese gate figura pendiente.
    assert "- reporte (A1): pendiente de la decisión final" in traice
    assert "un humano resolvió todos los gates de juicio" in traice

    demo = RunContext(protocol.slug, tmp_path, "DEMO")
    run_pipeline(
        protocol,
        EXAMPLE,
        demo,
        auto_approve=True,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
    )
    traice = _entregable(demo, "checklist_traice.md")
    assert "- rob (A0): aprobado por auto-approve (demo): NO es una validación humana" in traice
    assert "⚠ gates de juicio sin decisión humana" in traice


def test_traice_reporte_forzado_figura_en_a1(tmp_path: Path, con_cita_inventada) -> None:
    proto = _proto_reporte(tmp_path)  # reporte declarado en A2
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(
        protocol, proto, ctx, auto_approve=True, search_fn=_busqueda_ft, fetch_fn=fetch_disponible
    )
    traice = _entregable(ctx, "checklist_traice.md")
    assert "- reporte (A1): pendiente de la decisión final · exige decisión humana" in traice


def test_methods_sin_texto_fijo_de_validacion_humana(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        auto_approve=True,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
    )
    metodos = _entregable(ctx, "metodologia.md")
    for fijo in (
        "checkpoint humano (HITL)",
        "revisión humana campo a campo",
        "Juicio final humano (A0)",
        "la decisión final es siempre humana",
    ):
        assert fijo not in metodos
    assert (
        "Título/abstract: aprobado por auto-approve (demo): NO es una validación humana "
        "(autonomía A1)" in metodos
    )
    assert "⚠ gates de juicio sin decisión humana" in metodos
    assert "Reporte final: pendiente de la decisión final (autonomía A1)." in metodos


def _gate(
    stage: str = "screening_ta",
    action: str = "approve",
    actor: str = "human:ana",
    autonomy: str = "A1",
    **extra,
) -> GateSummary:
    return GateSummary(
        stage=stage,
        action=action,
        actor=actor,
        autonomy=autonomy,
        timestamp_utc="2026-10-04T10:00:00Z",
        **extra,
    )


@pytest.mark.parametrize(
    ("stage", "resumen", "esperado"),
    [
        ("reporte", None, "pendiente de la decisión final"),
        ("rob", None, "pendiente (sin decisión registrada)"),
        (
            "reporte",
            _gate("reporte", "auto-proceed", "agent:reporte", "A2"),
            "auto-proceed (agent:reporte, autonomía A2): sin revisión humana",
        ),
        (
            "rob",
            _gate("rob", actor=AUTO_APPROVE_ACTOR, autonomy="A0"),
            "aprobado por auto-approve (demo): NO es una validación humana",
        ),
        ("screening_ta", _gate(), "aprobado por humano (human:ana)"),
        ("screening_ta", _gate(action="reject"), "rechazado por humano (human:ana)"),
        (
            "screening_ft",
            _gate("screening_ft", autonomy="A0", n_labels=3),
            "aprobado por humano (human:ana) · 3 etiqueta(s) por registro",
        ),
        (
            "reporte",
            _gate("reporte", n_flag_reviews=2, forced_human=True),
            "aprobado por humano (human:ana) · 2 cita(s) marcada(s) adjudicada(s) · "
            "forzado a humano por citas marcadas",
        ),
        (
            "screening_ft",
            _gate("screening_ft", autonomy="A0", n_labels=1, n_flag_reviews=1, forced_human=True),
            "aprobado por humano (human:ana) · 1 etiqueta(s) por registro · "
            "1 cita(s) marcada(s) adjudicada(s) · forzado a humano por citas marcadas",
        ),
        # Un actor sin el prefijo `human:` no es una validación humana, aunque apruebe.
        ("extraccion", _gate("extraccion", actor="ana"), "aprobado por ana (no humano)"),
        (
            "extraccion",
            _gate("extraccion", action="reject", actor="agent:extraccion"),
            "rechazado por agent:extraccion (no humano)",
        ),
    ],
)
def test_describe_gate_dice_quien_decidio_de_verdad(
    stage: str, resumen: GateSummary | None, esperado: str
) -> None:
    assert describe_gate(stage, resumen) == esperado


def test_human_validation_summary_distingue_humano_demo_y_sin_decisiones() -> None:
    ninguno = "ningún gate de juicio tiene todavía una decisión registrada."
    assert human_validation_summary({}) == ninguno
    # `reporte` no es un gate de juicio: ni una aprobación de demostración suya cuenta.
    assert human_validation_summary({"reporte": _gate("reporte", actor=AUTO_APPROVE_ACTOR)}) == (
        ninguno
    )

    humanos = {"rob": _gate("rob", autonomy="A0"), "screening_ta": _gate()}
    assert human_validation_summary(humanos) == (
        "un humano resolvió todos los gates de juicio con decisión (screening_ta, rob)."
    )

    demo = {**humanos, "extraccion": _gate("extraccion", actor=AUTO_APPROVE_ACTOR, autonomy="A0")}
    resumen = human_validation_summary(demo)
    assert resumen.startswith("⚠ gates de juicio sin decisión humana: extraccion (")
    assert "extraccion (auto-approve (demo))." in resumen
    # Va al entregable (se pega en un manuscrito): forma impersonal, no un imperativo.
    assert resumen.endswith("debe declararse.")
    assert "decláralo" not in resumen
    assert "screening_ta" not in resumen  # solo nombra los que no resolvió un humano


def _efectiva(**cambios: str) -> dict[str, str]:
    base = {"screening_ta": "A1", "screening_ft": "A0", "extraccion": "A0", "rob": "A0"}
    return {**base, "reporte": "A1", **cambios}


def test_render_traice_checklist_lista_cada_gate_con_su_autonomia_efectiva() -> None:
    gates = {
        "screening_ta": _gate(),
        "screening_ft": _gate("screening_ft", autonomy="A0", n_labels=2),
        "extraccion": _gate("extraccion", actor=AUTO_APPROVE_ACTOR, autonomy="A0"),
    }

    md = render_traice_checklist([], _efectiva(), gates=gates, forced_human=True)

    assert "## Autonomía por etapa" not in md  # lo declarado ya no se presenta como lo aplicado
    bloque = md.split("## Autonomía efectiva y decisión por gate\n", 1)[1].split("\n\n", 1)[0]
    assert bloque.splitlines() == [
        "- screening_ta (A1): aprobado por humano (human:ana)",
        "- screening_ft (A0): aprobado por humano (human:ana) · 2 etiqueta(s) por registro",
        "- extraccion (A0): aprobado por auto-approve (demo): NO es una validación humana",
        "- rob (A0): pendiente (sin decisión registrada)",
        "- reporte (A1): pendiente de la decisión final · exige decisión humana: "
        "el verificador marcó citas",
    ]
    assert "- Validación humana: ⚠ gates de juicio sin decisión humana: extraccion" in md


def test_render_traice_checklist_sin_gates_no_afirma_ninguna_validacion_humana() -> None:
    md = render_traice_checklist([], _efectiva(reporte="A2", rob="A0"))

    assert "checkpoints HITL registrados" not in md
    assert "- Validación humana: ningún gate de juicio tiene todavía una decisión" in md
    assert "- rob (A0): pendiente (sin decisión registrada)" in md
    # Una A2 sin citas marcadas no espera ninguna decisión humana: seguirá sola.
    assert "- reporte (A2): auto-proceed previsto (A2): sin revisión humana" in md
    assert "pendiente de la decisión final" not in md
    assert "exige decisión humana" not in md
    # Solo lista los gates de los que se informa la autonomía.
    solo_rob = render_traice_checklist([], {"rob": "A0"})
    assert "- rob (A0)" in solo_rob
    assert "screening_ta" not in solo_rob


def test_render_methods_dice_quien_decidio_cada_fase() -> None:
    protocol = load_protocol(EXAMPLE)
    gates = {
        "screening_ta": _gate(),
        "screening_ft": _gate("screening_ft", autonomy="A0", n_labels=2),
        "extraccion": _gate("extraccion", actor=AUTO_APPROVE_ACTOR, autonomy="A0"),
    }

    md = render_methods(
        protocol=protocol,
        counts=PrismaCounts(),
        gates=gates,
        autonomy_effective=_efectiva(),
        forced_human=True,
    )

    # La autonomía va en el mismo paréntesis que el actor, no en un segundo (se pega en un
    # manuscrito): «(human:ana; autonomía A1)», no «(human:ana) (autonomía A1)».
    assert "Título/abstract: aprobado por humano (human:ana; autonomía A1)." in md
    assert (
        "Texto completo: aprobado por humano (human:ana; autonomía A0) · 2 etiqueta(s) por "
        "registro." in md
    )
    assert (
        "La tabla de extracción se aprueba por etapa: aprobado por auto-approve (demo): NO es "
        "una validación humana (autonomía A0)." in md
    )
    assert "Decisión: pendiente (sin decisión registrada; autonomía A0)." in md
    assert "(human:ana) (autonomía" not in md
    assert "(sin decisión registrada) (autonomía" not in md
    assert "Validación humana: ⚠ gates de juicio sin decisión humana: extraccion" in md
    assert (
        "Reporte final: pendiente de la decisión final (autonomía A1) — exige decisión humana: "
        "el verificador marcó citas." in md
    )


def test_render_methods_sin_gates_usa_la_autonomia_declarada_y_no_afirma_validacion() -> None:
    protocol = load_protocol(EXAMPLE)

    md = render_methods(protocol=protocol, counts=PrismaCounts())

    assert "Título/abstract: pendiente (sin decisión registrada; autonomía A1)." in md
    assert "Texto completo: pendiente (sin decisión registrada; autonomía A0)." in md
    assert "ningún gate de juicio tiene todavía una decisión registrada." in md
    assert "Reporte final: pendiente de la decisión final (autonomía A1)." in md
    assert "exige decisión humana" not in md


def test_metricas_de_cribado_dicen_que_miden_la_propuesta_de_la_ia_d6() -> None:
    # Revisión de la Tarea 23: κ y recall evalúan la propuesta del ensemble frente al gold humano,
    # no la decisión final con las correcciones del revisor; "humano-IA" lo daba a entender.
    metricas = _metricas(0.5)
    protocol = load_protocol(EXAMPLE)

    traice = render_traice_checklist([], _efectiva(), metrics=metricas)
    metodos = render_methods(protocol=protocol, counts=PrismaCounts(), metrics=metricas)

    assert "## Métricas de cribado (propuesta de la IA vs gold standard humano)" in traice
    assert "propuesta de la IA (`ensemble_label`)" in traice
    assert "no la decisión final con las correcciones humanas" in traice
    assert "Cohen's kappa (propuesta de la IA vs gold humano): 0.000" in traice
    assert "Cohen's kappa de la propuesta de la IA frente al gold humano = 0.000" in metodos
    assert "no la decisión final con las correcciones humanas" in metodos
    assert "humano-IA" not in traice + metodos


def test_methods_declara_los_informes_rescatados_y_su_limite_de_texto() -> None:
    # Revisión de la Tarea 24: un no recuperado que el revisor evaluó con un PDF de fuera cuenta
    # como evaluado, y la IA no vio ese texto: RoB y verificación (que sí usan el texto completo
    # cuando existe), solo con título/abstract. La extracción no se nombra aquí: usa título y
    # abstract para todos, rescatados o no (revisión de la Tarea 27). Sin rescates no se dice
    # nada de esto.
    protocol = load_protocol(EXAMPLE)
    con = PrismaCounts(
        fulltext_sought=3,
        fulltext_not_retrieved=1,
        fulltext_rescued=2,
        fulltext_assessed=4,
        included=3,
    )

    md = render_methods(protocol=protocol, counts=con)

    assert (
        "Informes rescatados por el revisor: 2 que el motor no recuperó y un humano evaluó con "
        "el texto completo obtenido fuera de él (cuentan como evaluados, no como no "
        "recuperados)." in md
    )
    assert (
        "Limitación: la IA no tuvo ese texto, así que el riesgo de sesgo y la verificación de "
        "las citas de los que se incluyeron se hicieron solo con título/abstract." in md
    )
    assert "la extracción, el riesgo de sesgo" not in md
    sin = render_methods(protocol=protocol, counts=PrismaCounts(fulltext_sought=3, included=3))
    assert "rescatados por el revisor" not in sin
    assert "solo con título/abstract" not in sin


def test_metodologia_de_una_corrida_con_rescate_lo_declara(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def rescatar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {
                "records": {
                    "rec-1": {"label": "include", "reason": "cumple"},
                    "rec-2": {"label": "include", "reason": "PDF por préstamo interbibliotecario"},
                }
            }
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_no_disponible(["rec-2"]),
        etiquetar=rescatar,
    )

    assert (result.status, result.counts.fulltext_rescued) == ("completed", 1)
    metodos = _entregable(ctx, "metodologia.md")
    assert "Informes rescatados por el revisor: 1 que el motor no recuperó" in metodos
    assert "solo con título/abstract" in metodos
    assert "evaluados para elegibilidad=2" in metodos  # el rescate cuenta como evaluado


# ── metodologia.md no atribuye a la IA lo que no hizo (revisión de la Tarea 27) ──


def test_methods_dice_que_la_extraccion_usa_titulo_y_abstract_para_todos() -> None:
    # `extract_record` manda solo título y abstract, hubiera o no texto completo (M14 es de la
    # Ola 2): la frase va siempre, no solo cuando hay rescates, que sugerían lo contrario.
    protocol = load_protocol(EXAMPLE)
    sin_rescates = PrismaCounts(fulltext_sought=3, included=3)
    con_rescates = PrismaCounts(fulltext_sought=3, fulltext_rescued=1, fulltext_assessed=3)
    frase = (
        "La IA extrae a partir del título y el abstract; el texto completo no entra en la "
        "extracción (limitación conocida)."
    )

    for counts in (sin_rescates, con_rescates, PrismaCounts()):
        md = render_methods(protocol=protocol, counts=counts)
        assert frase in md
        assert md.index("### Extracción") < md.index(frase) < md.index("### Evaluación de calidad")


def test_methods_distingue_el_ensemble_de_ta_del_modelo_unico_de_ft() -> None:
    # `_fulltext` pasa un único miembro a `screen_fulltext`: el ensemble es solo de T/A, y solo
    # si el protocolo lo declara (el demo trae 2 miembros).
    protocol = load_protocol(EXAMPLE)
    assert len(protocol.screeners_for("screening_ta")) == 2

    md = render_methods(protocol=protocol, counts=PrismaCounts())

    assert (
        "ensemble multi-modelo sesgado a recall (2 modelos) en título/abstract y un solo modelo "
        "en texto completo" in md
    )
    assert "con ensemble multi-modelo sesgado a recall." not in md  # el texto de antes

    sin_ensemble = protocol.model_copy(update={"ensemble": [], "ensemble_llm": {}})
    md = render_methods(protocol=sin_ensemble, counts=PrismaCounts())
    assert (
        "un solo modelo (sin ensemble) en título/abstract y un solo modelo en texto completo" in md
    )
    assert "ensemble multi-modelo" not in md


def test_methods_no_atribuye_verificacion_a_la_cita_de_origen_por_campo() -> None:
    # La `source_quote` se pide al LLM y se guarda, pero nada la contrasta con el texto: no es
    # una defensa «anti-alucinación» (revisión de la Tarea 27).
    md = render_methods(protocol=load_protocol(EXAMPLE), counts=PrismaCounts())

    assert (
        "Se solicita al modelo una cita textual de origen por campo y se registra junto al "
        "valor; no se verifica automáticamente contra el texto." in md
    )
    assert "anti-alucinación" not in md


@pytest.mark.parametrize("declarada", ["A2", "A3"])
def test_reporte_a2_a3_sin_citas_marcadas_figura_como_auto_proceed_previsto(
    declarada: str,
) -> None:
    # Sin citas marcadas el gate final seguirá solo: no llegará ninguna decisión humana, así que
    # «pendiente de la decisión final» daba a entender lo contrario.
    protocol = load_protocol(EXAMPLE)
    efectiva = _efectiva(reporte=declarada)
    previsto = f"auto-proceed previsto ({declarada}): sin revisión humana"

    traice = render_traice_checklist([], efectiva)
    metodos = render_methods(protocol=protocol, counts=PrismaCounts(), autonomy_effective=efectiva)

    assert f"- reporte ({declarada}): {previsto}" in traice
    assert f"Reporte final: {previsto}." in metodos
    assert "pendiente de la decisión final" not in traice + metodos
    # En A0/A1 sí espera a un humano.
    assert "- reporte (A1): pendiente de la decisión final" in render_traice_checklist(
        [], _efectiva(reporte="A1")
    )


def test_reporte_forzado_no_figura_como_auto_proceed_aunque_se_declare_a2() -> None:
    # Con citas marcadas el gate exige humano y la autonomía efectiva es A1. Si un llamador
    # pasara A2 con `forced_human`, el aviso de la decisión humana manda sobre el auto-proceed.
    traice = render_traice_checklist([], _efectiva(reporte="A2"), forced_human=True)

    assert "- reporte (A2): pendiente de la decisión final · exige decisión humana" in traice
    assert "auto-proceed previsto" not in traice


def test_render_methods_sin_autonomy_effective_degrada_reporte_si_esta_forzado() -> None:
    # Sin `autonomy_effective` pero con `forced_human`, la autonomía de `reporte` no es la
    # declarada (A2 «exige decisión humana» se contradice): sale de `effective_autonomy`.
    protocol = load_protocol(EXAMPLE)
    protocol = protocol.model_copy(update={"autonomy": {**protocol.autonomy, "reporte": "A2"}})

    md = render_methods(protocol=protocol, counts=PrismaCounts(), forced_human=True)

    assert (
        "Reporte final: pendiente de la decisión final (autonomía A1) — exige decisión humana: "
        "el verificador marcó citas." in md
    )
    assert "autonomía A2" not in md
    # Sin forzar, la declarada (A2) manda: seguirá sola.
    sin_forzar = render_methods(protocol=protocol, counts=PrismaCounts())
    assert "Reporte final: auto-proceed previsto (A2): sin revisión humana." in sin_forzar


def test_describe_gate_con_autonomia_la_mete_en_el_mismo_parentesis() -> None:
    # `inline_autonomy`: para la prosa de metodologia.md, sin un segundo paréntesis pegado.
    def frase(stage: str, resumen: GateSummary | None, nivel: str) -> str:
        return describe_gate(stage, resumen, autonomy=nivel, inline_autonomy=True)

    assert frase("screening_ta", _gate(), "A1") == "aprobado por humano (human:ana; autonomía A1)"
    assert (
        frase("screening_ft", _gate("screening_ft", autonomy="A0", n_labels=2), "A0")
        == "aprobado por humano (human:ana; autonomía A0) · 2 etiqueta(s) por registro"
    )
    assert (
        frase("extraccion", _gate("extraccion", actor="ana"), "A0")
        == "aprobado por ana (no humano; autonomía A0)"
    )
    assert frase("rob", None, "A0") == "pendiente (sin decisión registrada; autonomía A0)"
    assert frase("reporte", None, "A1") == "pendiente de la decisión final (autonomía A1)"
    assert frase("reporte", None, "A2") == "auto-proceed previsto (A2): sin revisión humana"
    # Los que ya cierran con una frase propia conservan la autonomía como sufijo.
    assert (
        frase("rob", _gate("rob", actor=AUTO_APPROVE_ACTOR, autonomy="A0"), "A0")
        == "aprobado por auto-approve (demo): NO es una validación humana (autonomía A0)"
    )
    # Sin `inline_autonomy` la frase no cambia (el checklist ya pone la autonomía delante).
    assert describe_gate("screening_ta", _gate(), autonomy="A1") == (
        "aprobado por humano (human:ana)"
    )
    assert describe_gate("reporte", None, autonomy="A2") == (
        "auto-proceed previsto (A2): sin revisión humana"
    )


def test_corrida_con_reporte_a2_sin_citas_marcadas_dice_auto_proceed_previsto(
    tmp_path: Path, proveedor
) -> None:
    proto = _proto(tmp_path, reporte="A2")
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    result = run_pipeline(
        protocol, proto, ctx, auto_approve=True, search_fn=_busqueda_ft, fetch_fn=fetch_disponible
    )

    assert result.status == "completed"
    traice = _entregable(ctx, "checklist_traice.md")
    metodos = _entregable(ctx, "metodologia.md")
    assert "- reporte (A2): auto-proceed previsto (A2): sin revisión humana" in traice
    assert "Reporte final: auto-proceed previsto (A2): sin revisión humana." in metodos
    assert "pendiente de la decisión final" not in traice + metodos


# ── el CLI tras completar con citas marcadas ya adjudicadas (revisión de la Tarea 22) ──

_AVISO_CITAS = "⚠ El verificador marcó posibles citas no fundamentadas: revisar."


def test_pipeline_result_dice_quien_adjudico_las_citas_marcadas(
    tmp_path: Path, con_cita_inventada
) -> None:
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, proto, ctx, parar_en="reporte", **kwargs)
    (indice,) = leer_solicitud(ctx.run_dir, "reporte")["must_adjudicate"]
    responder_gate(
        ctx.run_dir,
        "reporte",
        actor="human:ana",
        flags={str(indice): {"verdict": "false_positive", "reason": "[2019] es un año"}},
    )

    result = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)

    assert (result.status, result.hallucination_flagged) == ("completed", True)
    assert result.flags_adjudicated_by == "human:ana"


def test_cli_completado_con_citas_adjudicadas_no_manda_revisarlas(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    con_cita_inventada,
) -> None:
    # Un humano ya adjudicó cada cita marcada (así lo exige el gate, M5): imprimir «revisar»
    # después de eso mandaba a repetir un trabajo hecho.
    monkeypatch.setattr(cli, "_load_dotenv", lambda: None)
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    correr_hasta(
        protocol,
        proto,
        ctx,
        parar_en="reporte",
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
    )
    (indice,) = leer_solicitud(ctx.run_dir, "reporte")["must_adjudicate"]
    responder_gate(
        ctx.run_dir,
        "reporte",
        flags={str(indice): {"verdict": "false_positive", "reason": "[2019] es un año"}},
    )

    assert cli.main(["run", "--resume", str(ctx.run_dir)]) == 0

    out = capsys.readouterr().out
    assert "COMPLETED" in out
    assert "citas marcadas adjudicadas por human:revisora" in out
    assert _AVISO_CITAS not in out
    assert "⚠" not in out


def test_cli_completado_con_citas_marcadas_sin_adjudicar_sigue_avisando(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Si ningún humano las adjudicó (`flags_adjudicated_by` vacío), el aviso se mantiene.
    monkeypatch.setattr(cli, "_load_dotenv", lambda: None)
    resultado = PipelineResult(
        "completed", "ok", counts=PrismaCounts(), hallucination_flagged=True, run_dir=tmp_path
    )
    monkeypatch.setattr("revisia.orchestration.flow.resume_review", lambda *_a, **_k: resultado)

    assert cli.main(["run", "--resume", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert _AVISO_CITAS in out
    assert "adjudicadas por" not in out
