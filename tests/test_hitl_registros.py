"""Decisión humana por registro y por cita en decision.yml (Ola 1, PR-D; auditoría
2026-09-03, C1 y M5; spec 2026-10-04 §4.3 y §8)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from revisia.orchestration.hitl import (
    _MAX_COMENTARIO,
    _MAX_NOTA,
    DecisionFileError,
    FlaggedClaim,
    FlagPolicy,
    GateResult,
    HumanDecision,
    RecordHint,
    RecordPolicy,
    _acotar,
    render_decision_template,
    review_gate,
)
from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import DecisionEntry, summarize_gates

_HINTS = (
    RecordHint("a", "Estudio A", "include"),
    RecordHint("b", "Estudio B", "exclude"),
    RecordHint("c", "Estudio C (no recuperado)", None),
)
_MARCAS = FlagPolicy(
    flagged=(
        FlaggedClaim(0, "2019", "Según [2019] la IA reduce la carga.", "id citado no está"),
        FlaggedClaim(3, "rec-9", "Otro estudio [rec-9] lo confirma.", "id citado no está"),
    )
)


def _gate(
    ctx: RunContext,
    stage: str,
    *,
    politica: RecordPolicy | None = None,
    marcas: FlagPolicy | None = None,
    autonomy: str = "A1",
    auto_approve: bool = False,
    force_human: bool = False,
) -> GateResult:
    return review_gate(
        stage=stage,
        autonomy=autonomy,
        run_ctx=ctx,
        review_payload={"n": 1},
        auto_approve=auto_approve,
        records=politica,
        flags=marcas,
        force_human=force_human,
    )


def _responder(
    tmp_path: Path,
    stage: str,
    *,
    politica: RecordPolicy | None = None,
    marcas: FlagPolicy | None = None,
    force_human: bool = False,
    **decision,
) -> tuple[RunContext, GateResult]:
    """Primera vuelta (pausa), decision.yml con el hash vigente y segunda vuelta.

    ``decision`` son los campos de decision.yml (``approved`` por defecto ``True``).
    """
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _gate(ctx, stage, politica=politica, marcas=marcas, force_human=force_human)
    assert pausa.status == "paused"
    contenido = {
        "request_sha256": pausa.request_sha256,
        "approved": True,
        "actor": "human:ana",
        **decision,
    }
    (ctx.stage_dir(stage) / "decision.yml").write_text(
        yaml.safe_dump(contenido, allow_unicode=True), encoding="utf-8"
    )
    return ctx, _gate(ctx, stage, politica=politica, marcas=marcas, force_human=force_human)


def _responder_texto(
    tmp_path: Path,
    stage: str,
    cuerpo: str,
    *,
    politica: RecordPolicy | None = None,
    marcas: FlagPolicy | None = None,
    force_human: bool = False,
) -> tuple[RunContext, GateResult]:
    """Como ``_responder``, pero con el YAML escrito a mano (claves sin comillas).

    ``cuerpo`` va tras ``request_sha256``, ``approved: true`` y ``actor``.
    """
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _gate(ctx, stage, politica=politica, marcas=marcas, force_human=force_human)
    assert pausa.status == "paused"
    (ctx.stage_dir(stage) / "decision.yml").write_text(
        f'request_sha256: "{pausa.request_sha256}"\napproved: true\nactor: human:ana\n{cuerpo}',
        encoding="utf-8",
    )
    return ctx, _gate(ctx, stage, politica=politica, marcas=marcas, force_human=force_human)


# ── records (cribado por registro) ─────────────────────────────────────────


def test_decision_records_id_desconocido_es_error(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match="zzz"):
        _responder(
            tmp_path,
            "screening_ft",
            politica=RecordPolicy(hints=_HINTS),
            records={"zzz": {"label": "include"}},
        )


def test_records_en_gate_sin_registros_es_error(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match="`records` solo vale"):
        _responder(tmp_path, "rob", records={"a": {"label": "include"}})


def test_ft_exclude_sin_reason_es_error(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS, reason_on_exclude=True)
    with pytest.raises(DecisionFileError, match="'a' se excluye sin `reason`"):
        _responder(tmp_path, "screening_ft", politica=politica, records={"a": {"label": "exclude"}})


def test_rescate_sin_razon_es_error(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS, rescue_ids=frozenset({"c"}))
    with pytest.raises(DecisionFileError, match="'c' no se recuperó"):
        _responder(tmp_path, "screening_ft", politica=politica, records={"c": {"label": "include"}})


def test_ft_a0_aprobar_sin_etiquetar_todo_es_error(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS, must_label=frozenset({"a", "b"}))
    with pytest.raises(DecisionFileError, match=r"falta etiquetar o adjudicar: b \(1 en total\)"):
        _responder(
            tmp_path,
            "screening_ft",
            politica=politica,
            records={"a": {"label": "include"}, "b": {"label": None}},  # null = sin etiqueta
        )


def test_etiquetas_en_el_ledger_antes_del_approve(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS, rescue_ids=frozenset({"c"}), reason_on_exclude=True)
    ctx, result = _responder(
        tmp_path,
        "screening_ft",
        politica=politica,
        records={
            "b": {"label": "exclude", "reason": "población"},
            "c": {"label": "include", "reason": "texto pedido al autor"},
            "a": {"label": None},
        },
    )
    assert result.status == "approved"
    assert {k: v.label for k, v in result.labels.items()} == {"b": "exclude", "c": "include"}
    ledger = ctx.ledger.read_all()
    assert [(e.action, e.target) for e in ledger] == [
        ("label", "b"),
        ("label", "c"),
        ("approve", None),
    ]
    rescate = ledger[1].detail
    assert (rescate["from"], rescate["to"], rescate["rescue"]) == (None, "include", True)
    assert ledger[0].detail["from"] == "exclude"
    assert ledger[0].detail["decision_sha256"] == ledger[2].detail["decision_sha256"]
    assert ledger[2].detail["n_labels"] == 2
    assert summarize_gates(ledger)["screening_ft"].n_labels == 2


def test_rechazo_no_lleva_etiquetas(tmp_path: Path) -> None:
    ctx, result = _responder(
        tmp_path,
        "screening_ft",
        politica=RecordPolicy(hints=_HINTS),
        approved=False,
        records={"a": {"label": "exclude"}},
    )
    assert (result.status, result.labels) == ("rejected", {})
    assert [e.action for e in ctx.ledger.read_all()] == ["reject"]


def test_etiquetas_se_reconstruyen_desde_el_ledger(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS)
    ctx, _ = _responder(
        tmp_path, "screening_ta", politica=politica, records={"b": {"label": "include"}}
    )
    (ctx.run_dir / "screening_ta" / "decision.yml").unlink()
    result = _gate(ctx, "screening_ta", politica=politica)
    assert result.status == "approved"
    assert {k: v.label for k, v in result.labels.items()} == {"b": "include"}
    assert len(ctx.ledger.read_all()) == 2  # nada nuevo


def test_auto_approve_pausa_con_registros_por_resolver(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_resolve=frozenset({"b"}))
    result = _gate(ctx, "screening_ft", politica=politica, auto_approve=True)
    assert result.status == "paused"
    assert "`unclear` solo los resuelve un humano" in result.message
    assert ctx.ledger.read_all() == []


def test_auto_approve_no_exige_la_completitud_a0(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_label=frozenset({"a", "b"}))
    result = _gate(ctx, "screening_ft", politica=politica, auto_approve=True)
    assert (result.status, result.actor, result.labels) == ("approved", "auto-approve (demo)", {})


# ── flags (citas marcadas en el reporte, D8) ──────────────────────────────


def test_aprobar_con_citas_marcadas_exige_adjudicar_cada_una(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match=r"cita 3 \(1 en total\)"):
        _responder(
            tmp_path,
            "reporte",
            marcas=_MARCAS,
            force_human=True,
            flags={"0": {"verdict": "false_positive", "reason": "[2019] es un año"}},
        )


def test_adjudicacion_sin_razon_es_error(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match=r"cita 0 \(1 en total\)"):
        _responder(
            tmp_path,
            "reporte",
            marcas=_MARCAS,
            force_human=True,
            flags={
                "0": {"verdict": "false_positive", "reason": " "},
                "3": {"verdict": "false_positive", "reason": "rec-9 es una errata de rec-1"},
            },
        )


def test_rechazar_con_citas_marcadas_no_exige_adjudicar(tmp_path: Path) -> None:
    ctx, result = _responder(
        tmp_path, "reporte", marcas=_MARCAS, force_human=True, approved=False, reason="inventa"
    )
    assert result.status == "rejected"
    (rechazo,) = ctx.ledger.read_all()
    assert (rechazo.action, rechazo.detail["forced_human"]) == ("reject", True)


def test_flags_en_gate_sin_marcas_es_error(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match="`flags` solo vale"):
        _responder(tmp_path, "reporte", flags={"0": {"verdict": "false_positive", "reason": "x"}})


def test_flag_review_en_el_ledger_antes_del_approve(tmp_path: Path) -> None:
    ctx, result = _responder(
        tmp_path,
        "reporte",
        marcas=_MARCAS,
        force_human=True,
        flags={
            "3": {"verdict": "false_positive", "reason": "rec-9 es una errata de rec-1"},
            "0": {"verdict": "false_positive", "reason": "[2019] es un año, no un id"},
        },
    )
    assert result.status == "approved"
    ledger = ctx.ledger.read_all()
    assert [(e.action, e.target) for e in ledger] == [
        ("flag_review", "flag:0"),
        ("flag_review", "flag:3"),
        ("approve", None),
    ]
    marca = ledger[0].detail
    assert (marca["cited_id"], marca["verdict"]) == ("2019", "false_positive")
    assert marca["claim"] == "Según [2019] la IA reduce la carga."
    assert marca["reason"] == "[2019] es un año, no un id"
    assert {e.actor for e in ledger} == {"human:ana"}
    resumen = summarize_gates(ledger)["reporte"]
    assert (resumen.n_flag_reviews, resumen.forced_human) == (2, True)


def test_force_human_ignora_auto_approve_y_a2(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    result = _gate(
        ctx, "reporte", marcas=_MARCAS, autonomy="A2", auto_approve=True, force_human=True
    )
    assert result.status == "paused"
    assert "exige una decisión humana" in result.message
    solicitud = yaml.safe_load(
        (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")
    )
    assert solicitud["autonomy"] == "A1"  # la efectiva: A1 cuando está forzada
    assert ctx.ledger.read_all() == []


# ── casos que el plan no cubría: claves, índices, caídas a medias y A2 forzada ─


def test_claves_sin_comillas_llegan_como_texto(tmp_path: Path) -> None:
    # Un humano escribe `2019:` y `3:` sin comillas: YAML las lee como enteros. Las
    # claves de `records` y `flags` se leen como texto, no como "id desconocido".
    hints = (RecordHint("2019", "Estudio 2019", "include"),)
    ctx, result = _responder_texto(
        tmp_path,
        "screening_ta",
        "records:\n  2019: {label: exclude}\n",
        politica=RecordPolicy(hints=hints),
    )
    assert {k: v.label for k, v in result.labels.items()} == {"2019": "exclude"}
    assert [(e.action, e.target) for e in ctx.ledger.read_all()] == [
        ("label", "2019"),
        ("approve", None),
    ]

    ctx, result = _responder_texto(
        tmp_path / "flags",
        "reporte",
        "flags:\n  0: {verdict: false_positive, reason: es un año}\n"
        "  3: {verdict: false_positive, reason: errata}\n",
        marcas=_MARCAS,
        force_human=True,
    )
    assert sorted(result.flag_reviews) == ["0", "3"]
    assert [e.target for e in ctx.ledger.read_all()] == ["flag:0", "flag:3", None]


def test_flags_con_indice_desconocido_es_error(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match=r"índices que no son citas marcadas: 7"):
        _responder(
            tmp_path,
            "reporte",
            marcas=_MARCAS,
            force_human=True,
            flags={"7": {"verdict": "false_positive", "reason": "x"}},
        )


def test_clave_nula_de_records_es_error_de_decision(tmp_path: Path) -> None:
    # `~:` es una clave YAML nula: no es un id y no debe volverse el texto "None".
    with pytest.raises(DecisionFileError, match=r"records: .*no es un id válido"):
        _responder_texto(
            tmp_path,
            "screening_ta",
            "records:\n  ~: {label: include}\n",
            politica=RecordPolicy(hints=_HINTS),
        )


@pytest.mark.parametrize(
    "clave",
    [("a", "b"), frozenset({"a"}), None, b"a"],
    ids=["tupla", "conjunto", "nula", "binaria"],
)
@pytest.mark.parametrize("campo", ["records", "flags"])
def test_claves_no_escalares_son_error_de_validacion(campo: str, clave: object) -> None:
    # Una clave que no es texto ni número no se convierte con str() (daría "('a', 'b')"):
    # es un error de validación, que `_read_decision` traduce a DecisionFileError.
    with pytest.raises(ValidationError, match="no es un id válido"):
        HumanDecision.model_validate({"request_sha256": "x", "approved": True, campo: {clave: {}}})


@pytest.mark.parametrize("clave", ["[a, b]", "{x: 1}"], ids=["lista", "mapa"])
def test_clave_lista_o_mapa_en_decision_yml_es_error_accionable(tmp_path: Path, clave: str) -> None:
    # PyYAML ya rechaza esas claves (no son hashables) antes de llegar al modelo: el
    # humano ve un DecisionFileError con la ruta, no un traceback.
    with pytest.raises(DecisionFileError, match=r"decision\.yml: YAML inválido"):
        _responder_texto(
            tmp_path,
            "screening_ta",
            f"records:\n  ? {clave}\n  : {{label: include}}\n",
            politica=RecordPolicy(hints=_HINTS),
        )


def test_caida_a_medias_al_reanudar_solo_escribe_lo_que_falta(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS)
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _gate(ctx, "screening_ta", politica=politica)
    decision = {
        "request_sha256": pausa.request_sha256,
        "approved": True,
        "actor": "human:ana",
        "records": {"a": {"label": "include"}, "b": {"label": "exclude"}},
    }
    (ctx.stage_dir("screening_ta") / "decision.yml").write_text(
        yaml.safe_dump(decision), encoding="utf-8"
    )

    escribir = ctx.ledger.append
    escritas: list[str] = []

    def cae_tras_la_primera(entry) -> None:
        if escritas:
            raise OSError("disco lleno")  # cae tras la primera etiqueta
        escribir(entry)
        escritas.append(entry.action)

    ctx.ledger.append = cae_tras_la_primera  # type: ignore[method-assign]
    with pytest.raises(OSError, match="disco lleno"):
        _gate(ctx, "screening_ta", politica=politica)
    assert [(e.action, e.target) for e in ctx.ledger.read_all()] == [("label", "a")]

    ctx.ledger.append = escribir  # type: ignore[method-assign]
    result = _gate(ctx, "screening_ta", politica=politica)  # reanuda con el mismo decision.yml

    assert result.status == "approved"
    assert [(e.action, e.target) for e in ctx.ledger.read_all()] == [
        ("label", "a"),
        ("label", "b"),
        ("approve", None),
    ]
    assert summarize_gates(ctx.ledger.read_all())["screening_ta"].n_labels == 2
    assert _gate(ctx, "screening_ta", politica=politica).status == "approved"
    assert len(ctx.ledger.read_all()) == 3  # reanudar de nuevo no duplica nada


def test_force_human_con_a2_registra_a1_en_el_ledger(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _gate(ctx, "reporte", marcas=_MARCAS, autonomy="A2", force_human=True)
    assert pausa.status == "paused"
    decision = {
        "request_sha256": pausa.request_sha256,
        "approved": True,
        "actor": "human:ana",
        "flags": {
            "0": {"verdict": "false_positive", "reason": "es un año"},
            "3": {"verdict": "false_positive", "reason": "errata"},
        },
    }
    (ctx.stage_dir("reporte") / "decision.yml").write_text(
        yaml.safe_dump(decision), encoding="utf-8"
    )

    result = _gate(ctx, "reporte", marcas=_MARCAS, autonomy="A2", force_human=True)

    assert result.status == "approved"
    ledger = ctx.ledger.read_all()
    assert {e.autonomy for e in ledger} == {"A1"}  # nunca "A2": hubo humano
    assert [e.action for e in ledger] == ["flag_review", "flag_review", "approve"]
    assert ledger[-1].detail["forced_human"] is True


def test_records_y_flags_no_se_cuelan_al_detalle_del_approve(tmp_path: Path) -> None:
    # `records` y `flags` no se cuelan al `detail` del approve (viajan en sus entradas).
    ctx, _ = _responder(
        tmp_path,
        "screening_ta",
        politica=RecordPolicy(hints=_HINTS),
        reason="ok",
        records={"a": {"label": "include"}},
    )
    approve = ctx.ledger.read_all()[-1]
    assert set(approve.detail) == {
        "reason",
        "request_sha256",
        "decision_sha256",
        "n_labels",
        "forced_human",
    }


# ── el ledger manda, completitud y reetiquetado (revisión de la Tarea 20) ──


def test_force_human_no_reutiliza_una_aprobacion_de_demostracion(tmp_path: Path) -> None:
    # M5/D8: una cita marcada la resuelve un humano. Una aprobación de demostración
    # (--auto-approve) de la MISMA solicitud no se reutiliza con `force_human`: solo vale
    # del ledger la decisión efectiva cuyo actor es humano.
    ctx = RunContext("demo", tmp_path, "T")
    demo = _gate(ctx, "reporte", marcas=_MARCAS, auto_approve=True)
    assert (demo.status, demo.actor) == ("approved", "auto-approve (demo)")

    forzada = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert forzada.status == "paused"
    assert forzada.request_sha256 == demo.request_sha256  # es la misma solicitud
    assert len(ctx.ledger.read_all()) == 1  # no se registró nada nuevo

    decision = {
        "request_sha256": demo.request_sha256,
        "approved": True,
        "actor": "human:ana",
        "flags": {
            "0": {"verdict": "false_positive", "reason": "[2019] es un año"},
            "3": {"verdict": "false_positive", "reason": "errata"},
        },
    }
    (ctx.stage_dir("reporte") / "decision.yml").write_text(
        yaml.safe_dump(decision, allow_unicode=True), encoding="utf-8"
    )
    humana = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert (humana.status, humana.actor) == ("approved", "human:ana")
    assert sorted(humana.flag_reviews) == ["0", "3"]
    efectiva = summarize_gates(ctx.ledger.read_all())["reporte"]
    assert (efectiva.actor, efectiva.forced_human) == ("human:ana", True)

    # La decisión humana sí se reutiliza del ledger, sin decision.yml.
    (ctx.stage_dir("reporte") / "decision.yml").unlink()
    total = len(ctx.ledger.read_all())
    reutilizada = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert (reutilizada.status, reutilizada.actor) == ("approved", "human:ana")
    assert len(ctx.ledger.read_all()) == total


@pytest.mark.parametrize("actor", ["ana", "auto-approve (demo)", "agent:reporte"])
@pytest.mark.parametrize("approved", [True, False])
def test_force_human_rechaza_un_decision_yml_sin_actor_humano(
    tmp_path: Path, actor: str, approved: bool
) -> None:
    # "Humano" se define igual al entrar que al reutilizar del ledger: el actor empieza por
    # `human:`. Un decision.yml con otro actor no se acepta (ni se registra como
    # `forced_human`: sería una decisión que luego el ledger no reutilizaría).
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    decision = {"request_sha256": pausa.request_sha256, "approved": approved, "actor": actor}
    (ctx.stage_dir("reporte") / "decision.yml").write_text(
        yaml.safe_dump(decision), encoding="utf-8"
    )

    with pytest.raises(DecisionFileError, match=r"decisión humana.*human:<nombre>"):
        _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert ctx.ledger.read_all() == []


def test_force_human_acepta_un_actor_humano(tmp_path: Path) -> None:
    _, result = _responder(
        tmp_path,
        "reporte",
        marcas=_MARCAS,
        force_human=True,
        flags={
            "0": {"verdict": "false_positive", "reason": "es un año"},
            "3": {"verdict": "false_positive", "reason": "errata"},
        },
    )
    assert (result.status, result.actor) == ("approved", "human:ana")


_SIN_NOMBRE = ["human:", "human:   ", "human:\t", "human:" + chr(0xA0)]


@pytest.mark.parametrize("actor", _SIN_NOMBRE, ids=["vacio", "espacios", "tab", "nbsp"])
@pytest.mark.parametrize("approved", [True, False])
def test_force_human_rechaza_un_actor_humano_sin_nombre(
    tmp_path: Path, actor: str, approved: bool
) -> None:
    # `human:` a secas empezaba por el prefijo y contaba como humano: una decisión anónima
    # cerraba el gate forzado por una cita marcada. Hace falta al menos un carácter no blanco
    # tras el prefijo; el mensaje dice qué poner.
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    decision = {"request_sha256": pausa.request_sha256, "approved": approved, "actor": actor}
    if approved:
        decision["flags"] = {
            "0": {"verdict": "false_positive", "reason": "es un año"},
            "3": {"verdict": "false_positive", "reason": "errata"},
        }
    (ctx.stage_dir("reporte") / "decision.yml").write_text(
        yaml.safe_dump(decision), encoding="utf-8"
    )

    with pytest.raises(DecisionFileError, match=r"sin nombre.*`actor: human:ana`"):
        _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert ctx.ledger.read_all() == []


def test_force_human_no_reutiliza_del_ledger_una_decision_de_actor_humano_sin_nombre(
    tmp_path: Path,
) -> None:
    # La misma definición de «humano» al reutilizar la decisión ya registrada: una aprobación
    # de `human:` de esta misma solicitud no cierra el gate forzado.
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert pausa.status == "paused"

    def registrar(actor: str) -> None:
        ctx.ledger.append(
            DecisionEntry(
                stage="reporte",
                actor=actor,
                autonomy="A1",
                action="approve",
                detail={
                    "request_sha256": pausa.request_sha256,
                    "decision_sha256": "d" * 64,
                    "forced_human": True,
                },
            )
        )

    registrar("human:")
    anonima = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert (anonima.status, anonima.request_sha256) == ("paused", pausa.request_sha256)

    registrar("human:ana")
    nombrada = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert (nombrada.status, nombrada.actor) == ("approved", "human:ana")


def test_sin_force_human_el_actor_no_se_exige_humano(tmp_path: Path) -> None:
    # Fuera de un gate forzado, el actor sigue siendo informativo (compatibilidad).
    _, result = _responder(tmp_path, "screening_ta", actor="ana")
    assert (result.status, result.actor) == ("approved", "ana")


def test_adjudicaciones_se_reconstruyen_desde_el_ledger(tmp_path: Path) -> None:
    ctx, _ = _responder(
        tmp_path,
        "reporte",
        marcas=_MARCAS,
        force_human=True,
        flags={
            "0": {"verdict": "false_positive", "reason": "[2019] es un año"},
            "3": {"verdict": "false_positive", "reason": "errata de rec-1"},
        },
    )
    (ctx.run_dir / "reporte" / "decision.yml").unlink()
    result = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert (result.status, result.actor) == ("approved", "human:ana")
    assert {k: (v.verdict, v.reason) for k, v in result.flag_reviews.items()} == {
        "0": ("false_positive", "[2019] es un año"),
        "3": ("false_positive", "errata de rec-1"),
    }
    assert len(ctx.ledger.read_all()) == 3  # nada nuevo


def test_unclear_sin_etiquetar_con_decision_de_fichero_es_error(tmp_path: Path) -> None:
    # `must_resolve` pesa igual que `must_label` al aprobar desde decision.yml: el
    # `unclear` lo resuelve un humano (D9) y el fichero no puede dejarlo pendiente.
    politica = RecordPolicy(hints=_HINTS, must_resolve=frozenset({"b"}))
    with pytest.raises(DecisionFileError, match=r"para aprobar falta etiquetar o adjudicar: b "):
        _responder(tmp_path, "screening_ft", politica=politica, records={"a": {"label": "include"}})


def test_unclear_etiquetado_con_decision_de_fichero_se_aprueba(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS, must_resolve=frozenset({"b"}))
    _, result = _responder(
        tmp_path, "screening_ft", politica=politica, records={"b": {"label": "exclude"}}
    )
    assert result.status == "approved"
    assert {k: v.label for k, v in result.labels.items()} == {"b": "exclude"}


def test_reetiquetar_tras_aprobar_registra_label_y_approve_nuevos(tmp_path: Path) -> None:
    # D14: un decision.yml nuevo para la misma solicitud (otra etiqueta) es otra decisión;
    # la efectiva y sus etiquetas son las nuevas, y las viejas quedan en el ledger sin
    # colarse en la decisión efectiva (la `a` de la primera no está en la segunda).
    politica = RecordPolicy(hints=_HINTS)
    ctx, primera = _responder(
        tmp_path,
        "screening_ta",
        politica=politica,
        records={"a": {"label": "include"}, "b": {"label": "include"}},
    )
    assert {k: v.label for k, v in primera.labels.items()} == {"a": "include", "b": "include"}

    decision = {
        "request_sha256": primera.request_sha256,
        "approved": True,
        "actor": "human:ana",
        "records": {"b": {"label": "exclude"}},
    }
    ruta = ctx.stage_dir("screening_ta") / "decision.yml"
    ruta.write_text(yaml.safe_dump(decision), encoding="utf-8")
    segunda = _gate(ctx, "screening_ta", politica=politica)

    assert segunda.status == "approved"
    assert {k: v.label for k, v in segunda.labels.items()} == {"b": "exclude"}
    ledger = ctx.ledger.read_all()
    assert [(e.action, e.target) for e in ledger] == [
        ("label", "a"),
        ("label", "b"),
        ("approve", None),
        ("label", "b"),
        ("approve", None),
    ]
    assert [e.detail["to"] for e in ledger if e.target == "b"] == ["include", "exclude"]
    assert summarize_gates(ledger)["screening_ta"].n_labels == 1  # solo las de la efectiva

    ruta.unlink()  # sin decision.yml, el ledger devuelve las etiquetas nuevas
    reconstruida = _gate(ctx, "screening_ta", politica=politica)
    assert {k: v.label for k, v in reconstruida.labels.items()} == {"b": "exclude"}
    assert len(ctx.ledger.read_all()) == 5


def test_indices_de_flags_desconocidos_se_listan_en_orden_numerico(tmp_path: Path) -> None:
    # Como texto "10" < "2": el humano ve los índices en el orden en que los cuenta.
    with pytest.raises(DecisionFileError, match=r"citas marcadas: 2, 10 \(2 en total\)"):
        _responder(
            tmp_path,
            "reporte",
            marcas=_MARCAS,
            force_human=True,
            flags={
                "10": {"verdict": "false_positive", "reason": "x"},
                "2": {"verdict": "false_positive", "reason": "x"},
            },
        )


def test_citas_sin_adjudicar_se_listan_en_orden_numerico(tmp_path: Path) -> None:
    marcas = FlagPolicy(flagged=tuple(FlaggedClaim(i, None, f"afirmación {i}") for i in (10, 2)))
    with pytest.raises(DecisionFileError, match=r"adjudicar: cita 2, cita 10 \(2 en total\)"):
        _responder(tmp_path, "reporte", marcas=marcas, force_human=True)


# ── decision.template.yml (D4) ────────────────────────────────────────────

_RAIZ = {"request_sha256", "approved", "actor", "reason"}
# Saltos de línea de YAML 1.1: PyYAML y libyaml cierran un comentario con cualquiera.
_SALTOS = "\r\n\x85" + chr(0x2028) + chr(0x2029)
# Separadores y controles que un título o un rationale del LLM puede traer.
_SEPARADORES = {
    "LF": "\n",
    "CR": "\r",
    "CRLF": "\r\n",
    "NEL": "\x85",
    "LS": chr(0x2028),
    "PS": chr(0x2029),
    "VT": "\x0b",
    "FF": "\x0c",
    "FS": "\x1c",
    "NUL": "\x00",
    "DEL": "\x7f",
    "C1": "\x9f",
    "sustituto": chr(0xD800),
}
# Marcas de formato (categoría Cf): no son saltos de línea; en un comentario se borran.
_FORMATO = {
    "SHY": chr(0xAD),
    "ZWSP": chr(0x200B),
    "ZWNJ": chr(0x200C),
    "ZWJ": chr(0x200D),
    "WJ": chr(0x2060),
    "RLO": chr(0x202E),
    "BOM": chr(0xFEFF),
}


def _plantilla(
    *, records: RecordPolicy | None = None, flags: FlagPolicy | None = None, stage: str = "reporte"
) -> str:
    return render_decision_template(
        stage=stage, autonomy="A1", request_sha256="h", records=records, flags=flags
    )


def test_template_invalido_hasta_rellenarlo(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_label=frozenset({"a", "b"}))
    _gate(ctx, "screening_ft", politica=politica)
    carpeta = ctx.run_dir / "screening_ft"
    plantilla = (carpeta / "decision.template.yml").read_text(encoding="utf-8")
    datos = yaml.safe_load(plantilla)
    assert datos["approved"] is None
    assert datos["records"] == {
        "a": {"label": None, "reason": None},
        "b": {"label": None, "reason": None},
        "c": {"label": None, "reason": None},
    }

    (carpeta / "decision.yml").write_text(plantilla, encoding="utf-8")  # copiada tal cual
    with pytest.raises(DecisionFileError, match="booleano"):
        _gate(ctx, "screening_ft", politica=politica)

    datos["approved"] = True
    datos["records"]["a"]["label"] = "include"
    datos["records"]["b"] = {"label": "exclude", "reason": "diseño"}
    (carpeta / "decision.yml").write_text(yaml.safe_dump(datos), encoding="utf-8")
    assert _gate(ctx, "screening_ft", politica=politica).status == "approved"


def test_template_de_citas_se_rellena_y_aprueba(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    carpeta = ctx.run_dir / "reporte"
    datos = yaml.safe_load((carpeta / "decision.template.yml").read_text(encoding="utf-8"))
    assert datos["flags"] == {
        "0": {"verdict": None, "reason": None},
        "3": {"verdict": None, "reason": None},
    }

    datos["approved"] = True
    for adjudicacion in datos["flags"].values():
        adjudicacion.update(verdict="false_positive", reason="errata")
    (carpeta / "decision.yml").write_text(yaml.safe_dump(datos), encoding="utf-8")
    result = _gate(ctx, "reporte", marcas=_MARCAS, force_human=True)
    assert result.status == "approved"
    assert sorted(result.flag_reviews) == ["0", "3"]


def test_template_sanea_saltos_de_linea_del_llm() -> None:
    inyeccion = "fuera\napproved: true\nrecords: {a: x} actor: human:mallory\r\n"
    politica = RecordPolicy(
        hints=(RecordHint("10.1000/123", f"Título {inyeccion}", "exclude", inyeccion),),
        must_label=frozenset({"10.1000/123"}),
    )
    marcas = FlagPolicy(flagged=(FlaggedClaim(2, "2019", f"afirmación {inyeccion}", inyeccion),))
    plantilla = render_decision_template(
        stage="screening_ft", autonomy="A0", request_sha256="h", records=politica, flags=marcas
    )

    datos = yaml.safe_load(plantilla)
    assert datos["approved"] is None
    assert datos["actor"] == "human:desconocido"
    assert datos["records"] == {"10.1000/123": {"label": None, "reason": None}}
    assert datos["flags"] == {"2": {"verdict": None, "reason": None}}
    lineas = [x.strip() for x in plantilla.splitlines()]  # splitlines también corta en U+2028
    assert [x for x in lineas if x.startswith(("approved:", "actor:"))] == [
        "approved: null",
        'actor: "human:desconocido"',
    ]


@pytest.mark.parametrize("sep", list(_SEPARADORES.values()), ids=list(_SEPARADORES))
def test_template_sanea_cada_separador_y_control_en_los_comentarios(sep: str) -> None:
    inyeccion = f"x{sep}approved: true{sep}actor: human:mallory{sep}records: {{a: x}}"
    politica = RecordPolicy(
        hints=(RecordHint("r1", f"Título {inyeccion}", inyeccion, inyeccion),),
        must_label=frozenset({"r1"}),
    )
    marcas = FlagPolicy(flagged=(FlaggedClaim(1, inyeccion, inyeccion, inyeccion),))
    plantilla = _plantilla(records=politica, flags=marcas)

    plantilla.encode("utf-8")  # sin sustitutos sueltos: se puede escribir a disco
    datos = yaml.safe_load(plantilla)
    assert set(datos) == _RAIZ | {"records", "flags"}  # ninguna clave inyectada
    assert datos["approved"] is None
    assert datos["actor"] == "human:desconocido"
    assert datos["records"] == {"r1": {"label": None, "reason": None}}
    assert datos["flags"] == {"1": {"verdict": None, "reason": None}}
    for linea in re.split(f"[{_SALTOS}]", plantilla):  # líneas físicas según YAML 1.1
        if "approved: true" in linea or "mallory" in linea:
            assert linea.lstrip().startswith("#"), linea


@pytest.mark.parametrize("sep", list(_SEPARADORES.values()), ids=list(_SEPARADORES))
def test_template_sanea_la_etapa_y_la_autonomia(sep: str) -> None:
    plantilla = render_decision_template(
        stage=f"reporte{sep}approved: true",
        autonomy=f"A1{sep}actor: human:mallory",
        request_sha256="h",
        records=None,
        flags=None,
    )
    datos = yaml.safe_load(plantilla)
    assert set(datos) == _RAIZ
    assert (datos["approved"], datos["actor"]) == (None, "human:desconocido")


def test_template_claves_entre_comillas_vuelven_como_texto() -> None:
    assert yaml.safe_load("010: x") == {8: "x"}  # sin comillas, YAML 1.1 lo lee como octal
    ids = [
        "010",
        "10.1000/123",
        "2019",
        "yes",
        "null",
        "~",
        "a: b",
        "a #b",
        '"entre comillas"',
        "con\\barra",
        "ñandú",
        "id-" + chr(0x1F600),  # fuera del plano básico: sin pares de sustitutos
        "x" + chr(0xFFFE) + "y",
        "x" + chr(0xFEFF) + "y",
        "x" + chr(0xA0) + "y",
    ] + [f"id{sep}x" for sep in _SEPARADORES.values()]
    politica = RecordPolicy(hints=tuple(RecordHint(i, "t", "include") for i in ids))
    # El índice de una cita es un entero, pero la clave es texto: "010" no es 8 ni 10.
    marcas = FlagPolicy(
        flagged=(FlaggedClaim(10, "x", "c"), FlaggedClaim("010", "x", "c"))  # type: ignore[arg-type]
    )

    datos = yaml.safe_load(_plantilla(records=politica, flags=marcas))

    assert list(datos["records"]) == ids
    assert all(v == {"label": None, "reason": None} for v in datos["records"].values())
    assert list(datos["flags"]) == ["10", "010"]


def test_template_sin_registros_ni_citas_deja_mapas_vacios() -> None:
    # `records:` sin nada debajo se leería como null y la decisión copiada no validaría.
    datos = yaml.safe_load(_plantilla(records=RecordPolicy(hints=()), flags=FlagPolicy(flagged=())))
    assert datos["records"] == {}
    assert datos["flags"] == {}


@pytest.mark.parametrize(
    ("records", "flags"),
    [(None, None), (RecordPolicy(hints=_HINTS), None), (None, _MARCAS)],
    ids=["solo_decision", "con_registros", "con_citas"],
)
def test_template_pide_sustituir_desconocido_por_el_nombre_al_pie(
    records: RecordPolicy | None, flags: FlagPolicy | None
) -> None:
    # El default `human:desconocido` no cambia (el auditor le da WARN), pero la plantilla acaba
    # con una línea que pide poner el nombre de verdad, que es lo último que se lee.
    plantilla = _plantilla(records=records, flags=flags)

    ultima = plantilla.rstrip("\n").splitlines()[-1]
    assert ultima.startswith("#")
    assert "desconocido" in ultima and "human:<nombre>" in ultima
    assert 'actor: "human:desconocido"' in plantilla
    assert yaml.safe_load(plantilla)["actor"] == "human:desconocido"


def test_template_sin_citas_marcadas_no_imprime_la_cabecera_de_las_citas() -> None:
    # `FlagPolicy(flagged=())` deja el bloque `flags: {}` (la decisión copiada tiene que
    # validar), pero la cabecera «Citas marcadas por el verificador: adjudica cada una…» hablaba
    # de citas que no hay.
    vacia = _plantilla(flags=FlagPolicy(flagged=()))
    assert "Citas marcadas por el verificador" not in vacia
    assert "false_positive" not in vacia
    assert yaml.safe_load(vacia)["flags"] == {}
    assert "flags: {}" in vacia

    con_citas = _plantilla(flags=_MARCAS)
    assert "Citas marcadas por el verificador" in con_citas
    assert "`verdict: false_positive`" in con_citas


def test_acotar_corta_dentro_del_limite_y_sin_espacio_antes_de_los_puntos_suspensivos() -> None:
    assert _acotar("corto", 10) == "corto"  # dentro del límite, tal cual
    assert _acotar("x" * 50, 20) == "x" * 19 + "…"  # el «…» cuenta dentro del límite
    # Cortar justo detrás de un espacio dejaba «abcdefgh …».
    assert _acotar("abcdefgh ijklmnop", 10) == "abcdefgh…"
    assert " …" not in _acotar("palabra " * 40, 17)


@pytest.mark.parametrize(
    "id_citado",
    ["x" * 200, "x" * 57 + "\\" * 5, "x" * 59 + "'\"", "ñ" * 80, "x" * 58 + chr(0x1F600) * 4],
    ids=["largo", "barras_inversas", "comillas", "no_ascii", "emoji"],
)
def test_template_acota_el_id_citado_antes_del_repr_y_no_corta_un_escape(id_citado: str) -> None:
    # `repr(id)` y después cortar partía un escape (`'xx\`, sin la barra que lo cierra) y dejaba
    # el literal sin su comilla final; se acota el id y luego se le hace el `repr`: el literal
    # de la plantilla siempre es válido y vuelve al id acotado.
    comentario = _linea(
        _plantilla(flags=FlagPolicy(flagged=(FlaggedClaim(1, id_citado, "c", None),))), "cita "
    )
    literal = re.search(r"cita (.+?) · «", comentario)
    assert literal is not None, comentario
    assert ast.literal_eval(literal.group(1)) == _acotar(id_citado, 60)


def test_template_con_id_citado_nulo_dice_none() -> None:
    comentario = _linea(
        _plantilla(flags=FlagPolicy(flagged=(FlaggedClaim(2, None, "afirmación", "sin id"),))),
        "cita ",
    )
    assert comentario == "# [2] cita None · sin id · «afirmación»"


def test_template_sin_politicas_solo_lleva_la_decision() -> None:
    plantilla = _plantilla(stage="rob")
    assert set(yaml.safe_load(plantilla)) == _RAIZ
    assert "records" not in plantilla and "flags" not in plantilla


def test_template_comenta_propuesta_marcas_y_nota_de_cada_registro_y_cita() -> None:
    hints = (
        RecordHint("a", "Estudio A", "include", "3/3 votos"),
        RecordHint("b", "Estudio B", "unclear"),
        RecordHint("c", "Estudio C", None, "sin PDF"),
    )
    politica = RecordPolicy(
        hints=hints,
        must_label=frozenset({"a"}),
        must_resolve=frozenset({"b"}),
        rescue_ids=frozenset({"c"}),
    )
    marcas = FlagPolicy(
        flagged=(FlaggedClaim(2, "2019", "La IA reduce la carga.", "id citado no está"),)
    )
    lineas = [x.strip() for x in _plantilla(records=politica, flags=marcas).splitlines()]

    # Lo estructurado (propuesta, marcas) va primero y el texto libre (título, nota) después.
    comentarios = {
        "a": "# propuesta IA: include · obligatorio · «Estudio A» · 3/3 votos",
        "b": "# propuesta IA: unclear · unclear: resuélvelo · «Estudio B»",
        "c": "# propuesta IA: — · no recuperado: rescatable · «Estudio C» · sin PDF",
    }
    for clave, comentario in comentarios.items():  # justo encima de su clave
        assert lineas[lineas.index(comentario) + 1] == f'"{clave}": {{label: null, reason: null}}'
    cita = "# [2] cita '2019' · id citado no está · «La IA reduce la carga.»"
    assert lineas[lineas.index(cita) + 1] == '"2": {verdict: null, reason: null}'
    assert (
        "# Obligatorio etiquetar: 1 · `unclear` por resolver: 1 · no recuperados rescatables: 1."
    ) in lineas
    # Si una marca es real, la cabecera manda rechazar: no hay veredicto «aceptar el riesgo».
    assert any(x.startswith("#") and "rechaza (`approved: false`)" in x for x in lineas)


def _linea(plantilla: str, fragmento: str) -> str:
    """La primera línea de la plantilla que contiene ``fragmento``, sin sangría."""
    return next(x for x in plantilla.splitlines() if fragmento in x).strip()


def test_template_acota_el_titulo_y_conserva_propuesta_marcas_y_nota() -> None:
    # Revisión de la Tarea 21: con un título realista de ~200 caracteres, acotar la línea
    # entera borraba justo lo que el humano necesita (propuesta, marcas, nota). Se acota
    # el texto libre, no la línea.
    politica = RecordPolicy(
        hints=(RecordHint("r1", "T" * 300, "unclear", "3/3 votos"),),
        must_label=frozenset({"r1"}),
        must_resolve=frozenset({"r1"}),
    )
    comentario = _linea(_plantilla(records=politica), "propuesta IA")
    for conserva in ("propuesta IA: unclear", "obligatorio", "unclear: resuélvelo", "3/3 votos"):
        assert conserva in comentario
    assert "«" + "T" * 119 + "…»" in comentario  # el título, a 120 caracteres con su «…»


def test_template_acota_la_afirmacion_y_conserva_la_cita_y_su_motivo() -> None:
    marcas = FlagPolicy(flagged=(FlaggedClaim(4, "rec-9", "C" * 300, "id citado no está"),))
    comentario = _linea(_plantilla(flags=marcas), "cita 'rec-9'")
    assert comentario.startswith("# [4] cita 'rec-9' · id citado no está · «")
    assert "«" + "C" * 119 + "…»" in comentario


def test_template_con_todo_el_texto_libre_largo_no_pierde_nada_estructurado() -> None:
    # El peor caso: título, propuesta y nota enormes y las tres marcas a la vez. La línea
    # cabe en el tope sin que este corte nada: las marcas están enteras y la nota llega a
    # su propio límite (``_MAX_NOTA``), no al del tope (``_MAX_COMENTARIO``).
    politica = RecordPolicy(
        hints=(RecordHint("r1", "T" * 5000, "P" * 500, "n" * 5000),),
        must_label=frozenset({"r1"}),
        must_resolve=frozenset({"r1"}),
        rescue_ids=frozenset({"r1"}),
    )
    comentario = _linea(_plantilla(records=politica), "propuesta IA")
    for marca in ("obligatorio", "unclear: resuélvelo", "no recuperado: rescatable"):
        assert marca in comentario
    assert comentario.endswith("n" * (_MAX_NOTA - 1) + "…")
    assert len(comentario) < _MAX_COMENTARIO


@pytest.mark.parametrize("marca", list(_FORMATO.values()), ids=list(_FORMATO))
def test_template_borra_las_marcas_de_formato_de_los_comentarios(marca: str) -> None:
    # U+00AD, ZWNJ, ZWJ, U+200B, U+FEFF… no separan palabras: una marca invisible dentro
    # de una palabra no la parte en dos ("inter vention"); se borra.
    politica = RecordPolicy(
        hints=(RecordHint("r1", f"inter{marca}vention", "include", f"vo{marca}tos"),)
    )
    marcas = FlagPolicy(flagged=(FlaggedClaim(1, "x", f"afirma{marca}ción", f"mo{marca}tivo"),))
    plantilla = _plantilla(records=politica, flags=marcas)
    assert "«intervention»" in plantilla and "· votos" in plantilla
    assert "«afirmación»" in plantilla and "· motivo" in plantilla
    assert marca not in plantilla


@pytest.mark.parametrize("sep", list(_SEPARADORES.values()), ids=list(_SEPARADORES))
def test_template_sigue_separando_con_un_espacio_los_saltos_y_controles(sep: str) -> None:
    # Los saltos de línea y los controles no son parte de la palabra: separan.
    politica = RecordPolicy(hints=(RecordHint("r1", f"uno{sep}dos", "include"),))
    assert "«uno dos»" in _plantilla(records=politica)


def _claves_largas() -> dict[str, str]:
    return {
        "500": "a" * 500,
        "998": "a" * 998,
        "1000": "a" * 1000,
        "1100": "a" * 1100,
        "5000": "a" * 5000,
        "ñ1100": "ñ" * 1100,
        "emoji1100": chr(0x1F600) * 1100,
        # Pocos caracteres, pero cada U+0085 se escribe como un escape de 6: mide la clave
        # ya escapada, no el id.
        "escapes": "x" + chr(0x85) * 200,
        # Un id con `: ` y ` #` (en YAML plano serían un mapa y un comentario): en comillas,
        # en la forma implícita (800 caracteres), en la frontera (998, cerrado con una `b`) y en
        # la explícita (1100, 5000).
        "dos_puntos_y_almohadilla_800": "a: #" * 200,
        "dos_puntos_y_almohadilla_998": ("k: v #c " * 125)[:997] + "b",
        "dos_puntos_y_almohadilla_1100": ("k: v #c " * 138)[:1100],
        "dos_puntos_y_almohadilla_5000": ("k: v #c " * 625)[:5000],
    }


# ``yaml.safe_load`` usa el ``SafeLoader`` de Python puro; con libyaml existe además
# ``CSafeLoader`` (el que usan muchas herramientas), que lee distinto en los bordes (la clave
# implícita de 1024, los escapes). Los dos tienen que devolver la plantilla idéntica.
_CARGADORES = [
    pytest.param(yaml.SafeLoader, id="SafeLoader"),
    pytest.param(
        getattr(yaml, "CSafeLoader", None),
        id="CSafeLoader",
        marks=pytest.mark.skipif(
            not hasattr(yaml, "CSafeLoader"), reason="PyYAML sin libyaml (CSafeLoader)"
        ),
    ),
]


@pytest.mark.parametrize("cargador", _CARGADORES)
@pytest.mark.parametrize("id_largo", list(_claves_largas().values()), ids=list(_claves_largas()))
def test_template_con_claves_de_mas_de_1024_caracteres_sigue_siendo_legible(
    id_largo: str, cargador: type
) -> None:
    # YAML limita a 1024 caracteres la clave implícita (`clave: valor` en una línea): una
    # más larga dejaba toda la plantilla ilegible (ScannerError). Esas van con la forma
    # explícita (`? clave` / `: valor`).
    politica = RecordPolicy(
        hints=(
            RecordHint("corto", "t", "include"),
            RecordHint(id_largo, "t", "include"),
            RecordHint("otro", "t", None),
        )
    )
    datos = yaml.load(_plantilla(records=politica), Loader=cargador)
    assert datos["approved"] is None
    assert list(datos["records"]) == ["corto", id_largo, "otro"]
    assert all(v == {"label": None, "reason": None} for v in datos["records"].values())


@pytest.mark.parametrize("cargador", _CARGADORES)
def test_template_con_indice_de_cita_de_mas_de_1024_caracteres_sigue_siendo_legible(
    cargador: type,
) -> None:
    indice = int("9" * 1100)
    marcas = FlagPolicy(flagged=(FlaggedClaim(1, "x", "c"), FlaggedClaim(indice, "x", "c")))
    datos = yaml.load(_plantilla(flags=marcas), Loader=cargador)
    assert list(datos["flags"]) == ["1", str(indice)]
    assert all(v == {"verdict": None, "reason": None} for v in datos["flags"].values())


def test_template_con_id_de_mas_de_1024_caracteres_se_rellena_y_aprueba(tmp_path: Path) -> None:
    id_largo = "rec-" + "9" * 1100
    politica = RecordPolicy(
        hints=(RecordHint(id_largo, "t", "include"),), must_label=frozenset({id_largo})
    )
    ctx = RunContext("demo", tmp_path, "T")
    assert _gate(ctx, "screening_ft", politica=politica).status == "paused"
    carpeta = ctx.run_dir / "screening_ft"
    datos = yaml.safe_load((carpeta / "decision.template.yml").read_text(encoding="utf-8"))
    datos["approved"] = True
    datos["records"][id_largo]["label"] = "include"

    decision = HumanDecision.model_validate(datos)
    assert decision.records[id_largo].label == "include"

    (carpeta / "decision.yml").write_text(yaml.safe_dump(datos), encoding="utf-8")
    result = _gate(ctx, "screening_ft", politica=politica)
    assert result.status == "approved"
    assert list(result.labels) == [id_largo]


# ── pausa: no sugerir --auto-approve cuando volvería a pausar ──────────────


@pytest.mark.parametrize("auto_approve", [False, True])
def test_pausa_por_citas_marcadas_pide_una_decision_humana(
    tmp_path: Path, auto_approve: bool
) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    result = _gate(ctx, "reporte", marcas=_MARCAS, auto_approve=auto_approve, force_human=True)
    assert result.status == "paused"
    assert "exige una decisión humana" in result.message
    assert "`flags`" in result.message and "decision.yml" in result.message
    # Solo se nombra --auto-approve (para decir que no aplica) si el humano lo pasó.
    assert ("--auto-approve no aplica" in result.message) is auto_approve
    assert ("--auto-approve" in result.message) is auto_approve


@pytest.mark.parametrize("auto_approve", [False, True])
def test_pausa_por_unclear_pide_una_decision_humana(tmp_path: Path, auto_approve: bool) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_resolve=frozenset({"b"}))
    result = _gate(ctx, "screening_ft", politica=politica, auto_approve=auto_approve)
    assert result.status == "paused"
    assert "`unclear` solo los resuelve un humano" in result.message
    assert "`records`" in result.message and "decision.yml" in result.message
    assert ("--auto-approve no aplica" in result.message) is auto_approve
    assert ("--auto-approve" in result.message) is auto_approve


@pytest.mark.parametrize(
    "marcas", [None, FlagPolicy(flagged=())], ids=["sin_politica", "sin_citas_marcadas"]
)
def test_pausa_forzada_sin_citas_marcadas_no_manda_adjudicar_en_flags(
    tmp_path: Path, marcas: FlagPolicy | None
) -> None:
    # La plantilla no tiene bloque `flags` (o lo tiene vacío): el mensaje no puede mandar a
    # adjudicar en él ni decir que el verificador marcó citas. Tampoco menciona `records`
    # si no hay registros `unclear` que resolver.
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_label=frozenset({"a"}))
    result = _gate(ctx, "reporte", politica=politica, marcas=marcas, force_human=True)
    assert result.status == "paused"
    assert "exige una decisión humana" in result.message
    assert "`flags`" not in result.message and "marcó citas" not in result.message
    assert "`records`" not in result.message
    assert "approved: true" in result.message and "approved: false" in result.message


def test_pausa_forzada_con_citas_marcadas_y_unclear_nombra_cada_bloque(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_resolve=frozenset({"b"}))
    result = _gate(ctx, "reporte", politica=politica, marcas=_MARCAS, force_human=True)
    assert result.status == "paused"
    assert "`flags`" in result.message and "`records`" in result.message


def test_pausa_generica_sigue_ofreciendo_auto_approve(tmp_path: Path) -> None:
    # Con `must_label` (A0) --auto-approve sí aprueba (D9): ahí la sugerencia es cierta.
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_label=frozenset({"a"}))
    result = _gate(ctx, "screening_ft", politica=politica)
    assert result.status == "paused"
    assert "o vuelve a correr con --auto-approve" in result.message
