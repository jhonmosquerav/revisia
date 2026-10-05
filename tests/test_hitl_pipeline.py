"""HITL por registro en el pipeline (Ola 1, PR-D; auditoría 2026-09-03, C1, M5 y M13;
spec 2026-10-04 §8)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import correr_hasta, leer_solicitud, responder_gate

from revisia.config import load_protocol
from revisia.metrics import compute_screening_metrics
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.gates import apply_labels, ta_payload, ta_policy
from revisia.orchestration.hitl import DecisionFileError, RecordLabel, render_decision_template
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import AUTO_APPROVE_ACTOR
from revisia.provenance.runmeta import canonical_sha256
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision, ScreeningVote

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


def _proto_a0(tmp_path: Path) -> Path:
    """Copia del demo con ``screening_ta`` en A0: el humano etiqueta cada registro (D1)."""
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["autonomy"]["screening_ta"] = "A0"
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
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    ficha = proto / "protocol.yml"
    raw = yaml.safe_load(ficha.read_text(encoding="utf-8"))
    raw["autonomy"]["screening_ta"] = autonomia
    ficha.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
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
    assert [e.target for e in ctx.ledger.read_all() if e.action == "label"] == ["rec-2"]
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
