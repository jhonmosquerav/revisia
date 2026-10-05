"""Decisión humana por registro y por cita en decision.yml (Ola 1, PR-D; auditoría
2026-09-03, C1 y M5; spec 2026-10-04 §4.3 y §8)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from revisia.orchestration.hitl import (
    DecisionFileError,
    FlaggedClaim,
    FlagPolicy,
    GateResult,
    HumanDecision,
    RecordHint,
    RecordPolicy,
    review_gate,
)
from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import summarize_gates

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
