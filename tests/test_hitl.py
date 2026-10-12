"""Tests del checkpoint humano file-based (auditoría 2026-09-03, C1 y bajos; Ola 1,
`request_sha256`, ledger idempotente: spec 2026-10-04 §4.3 y §7)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from revisia.orchestration.hitl import DecisionFileError, GateResult, review_gate
from revisia.orchestration.run_context import RunContext
from revisia.provenance.runmeta import canonical_sha256


def _solicitar(
    ctx: RunContext,
    *,
    payload: dict | None = None,
    autonomy: str = "A1",
    auto_approve: bool = False,
) -> GateResult:
    return review_gate(
        stage="reporte",
        autonomy=autonomy,
        run_ctx=ctx,
        review_payload={"included": 1} if payload is None else payload,
        auto_approve=auto_approve,
    )


def _decidir(ctx: RunContext, texto: str, sha: str) -> None:
    """Escribe decision.yml; ``@SHA@`` se sustituye por el hash de la solicitud."""
    path = ctx.stage_dir("reporte") / "decision.yml"
    path.write_text(texto.replace("@SHA@", sha), encoding="utf-8")


def _gate(tmp_path: Path, decision_text: str | None, *, auto_approve: bool = False):
    ctx = RunContext("demo", tmp_path, "T")
    if decision_text is None:
        return ctx, _solicitar(ctx, auto_approve=auto_approve)
    pausa = _solicitar(ctx)  # primera vuelta: escribe la solicitud y pausa
    _decidir(ctx, decision_text, pausa.request_sha256)
    return ctx, _solicitar(ctx, auto_approve=auto_approve)


def test_decision_string_false_does_not_approve(tmp_path: Path) -> None:
    # bool("false") es True: antes, esta decisión APROBABA.
    # El mensaje de Pydantic, no `booleano`: esa palabra va en la pista que acompaña
    # a TODO error de decision.yml y casaría aunque el rechazo fuera por otra causa.
    with pytest.raises(DecisionFileError, match="approved: Input should be a valid boolean"):
        _gate(tmp_path, 'request_sha256: "@SHA@"\napproved: "false"\n')


def test_decision_false_rechaza(tmp_path: Path) -> None:
    ctx, result = _gate(
        tmp_path, 'request_sha256: "@SHA@"\napproved: false\nactor: human:revisora\n'
    )
    assert result.status == "rejected"
    entry = ctx.ledger.read_all()[-1]
    assert entry.action == "reject"
    assert entry.actor == "human:revisora"


def test_decision_booleana_aprueba_y_registra_actor(tmp_path: Path) -> None:
    ctx, result = _gate(
        tmp_path, 'request_sha256: "@SHA@"\napproved: true\nactor: human:jhon\nreason: ok\n'
    )
    assert result.status == "approved"
    entry = ctx.ledger.read_all()[-1]
    assert entry.actor == "human:jhon"
    assert {"reason": "ok", "request_sha256": result.request_sha256}.items() <= entry.detail.items()


def test_campos_extra_se_conservan_en_el_ledger(tmp_path: Path) -> None:
    ctx, _ = _gate(tmp_path, 'request_sha256: "@SHA@"\napproved: true\nnota: revisado a mano\n')
    assert ctx.ledger.read_all()[-1].detail["nota"] == "revisado a mano"


@pytest.mark.parametrize(
    ("text", "causa"),
    [
        ("- approved: true\n", "la raíz es list, no un mapa"),  # antes: AttributeError
        ("", "está vacío"),  # antes: rechazo silencioso de human:desconocido
        ("approved: [\n", "YAML inválido"),  # antes: traceback de yaml
        ('request_sha256: "@SHA@"\nactor: human:x\n', "approved: Field required"),
    ],
)
def test_malformed_decision_yaml_is_actionable(tmp_path: Path, text: str, causa: str) -> None:
    # `decision.yml` va en la ruta de TODOS los errores: la causa concreta es lo que
    # distingue un caso de otro.
    with pytest.raises(DecisionFileError, match=rf"decision\.yml: .*{causa}"):
        _gate(tmp_path, text)


def test_auto_approve_sin_decision(tmp_path: Path) -> None:
    ctx, result = _gate(tmp_path, None, auto_approve=True)
    assert result.status == "approved"
    entry = ctx.ledger.read_all()[-1]
    assert entry.actor == "auto-approve (demo)"
    assert set(entry.detail) == {"request_sha256", "decision_sha256", "n_labels", "forced_human"}
    assert (entry.detail["n_labels"], entry.detail["forced_human"]) == (0, False)


def test_sin_decision_pausa(tmp_path: Path) -> None:
    _, result = _gate(tmp_path, None)
    assert result.status == "paused"


# ── request_sha256 y ledger idempotente (Ola 1, spec 2026-10-04 §7) ─────────


def test_gate_exige_request_sha256(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _solicitar(ctx)
    plantilla = (ctx.run_dir / "reporte" / "decision.template.yml").read_text(encoding="utf-8")
    assert f'request_sha256: "{pausa.request_sha256}"' in plantilla
    assert "approved: null" in plantilla
    assert "revisia run --resume" in pausa.message and "decision.template.yml" in pausa.message

    _decidir(ctx, "approved: true\nactor: human:x\n", pausa.request_sha256)  # sin el hash
    # `request_sha256` también va en la pista de todo error: se exige el de Pydantic.
    with pytest.raises(DecisionFileError, match="request_sha256: Field required"):
        _solicitar(ctx)
    assert ctx.ledger.read_all() == []


def test_decision_obsoleta_pausa_sin_aplicar(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    vieja = _solicitar(ctx, payload={"included": 1})
    _decidir(ctx, 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n', vieja.request_sha256)

    nueva = _solicitar(ctx, payload={"included": 2})  # la solicitud cambió

    assert nueva.status == "paused"
    assert nueva.request_sha256 != vieja.request_sha256
    assert "otra solicitud" in nueva.message
    assert ctx.ledger.read_all() == []  # no se aplicó nada
    solicitud = yaml.safe_load(
        (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")
    )
    assert solicitud["request_sha256"] == nueva.request_sha256


def test_ledger_idempotente_al_reanudar(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _solicitar(ctx)
    _decidir(ctx, 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n', pausa.request_sha256)
    for _ in range(3):  # tres reanudaciones con la misma decisión
        assert _solicitar(ctx).status == "approved"
    assert [e.action for e in ctx.ledger.read_all()] == ["approve"]

    # Cambiar de opinión es legítimo y queda registrado (D14).
    _decidir(
        ctx, 'request_sha256: "@SHA@"\napproved: false\nactor: human:x\n', pausa.request_sha256
    )
    assert _solicitar(ctx).status == "rejected"
    assert _solicitar(ctx).status == "rejected"
    assert [e.action for e in ctx.ledger.read_all()] == ["approve", "reject"]

    # auto-proceed (A2) tampoco se duplica.
    for _ in range(2):
        _solicitar(ctx, autonomy="A2")
    assert [e.action for e in ctx.ledger.read_all()].count("auto-proceed") == 1


def test_ledger_reconstruye_decision_sin_decision_yml(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _solicitar(ctx)
    _decidir(ctx, 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n', pausa.request_sha256)
    assert _solicitar(ctx).status == "approved"
    (ctx.run_dir / "reporte" / "decision.yml").unlink()  # el canal de entrada desaparece

    result = _solicitar(ctx)

    assert (result.status, result.actor) == ("approved", "human:x")  # el ledger manda
    assert len(ctx.ledger.read_all()) == 1
    # Una solicitud distinta no hereda esa decisión.
    assert _solicitar(ctx, payload={"included": 2}).status == "paused"


def test_request_sha256_recomputable_desde_yaml(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    payload = {"records": [{"record_id": "10.1/ñ", "votes": [{"label": "include"}]}], "n": 1}
    result = _solicitar(ctx, payload=payload)
    solicitud = yaml.safe_load(
        (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")
    )
    sha = solicitud.pop("request_sha256")
    assert sha == result.request_sha256 == canonical_sha256(solicitud)
    assert (solicitud["schema_version"], solicitud["stage"], solicitud["autonomy"]) == (
        1,
        "reporte",
        "A1",
    )


def test_request_sha256_recomputable_con_texto_que_yaml_deforma(tmp_path: Path) -> None:
    # Con allow_unicode=True, PyYAML escribe U+0085 (NEL) crudo y safe_load lo lee
    # como un salto de línea plegado a espacio: el título volvía con otro texto y el
    # hash dejaba de recalcularse (spec, relación 15). Es mojibake frecuente: el «…»
    # de cp1252 leído como latin-1. PR-D mete títulos y rationales en la solicitud.
    ctx = RunContext("demo", tmp_path, "T")
    payload = {
        "titulo": "Efecto de la intervención\x85",
        "medio": "x\x85y",
        "separadores": ["a\u2028b", "a\u2029b"],
        "controles": "\x00\x1b\x7f\x9f\ufeff",
        "multilinea": "línea 1\nlínea 2\n",
        "con_espacios": "  ni al principio ni al final  ",
        "parece_fecha": "2026-10-04",
        "ratio": 1 / 3,
        "nada": None,
        "anidado": {"clave\x85": [{"record_id": "10.1/ñ", "nota": "\x85"}]},
    }
    result = _solicitar(ctx, payload=payload)

    # Releído del disco, como lo haría el auditor o PR-D, no volcado en memoria.
    solicitud = yaml.safe_load(
        (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")
    )
    sha = solicitud.pop("request_sha256")
    assert solicitud == {"schema_version": 1, "stage": "reporte", "autonomy": "A1", **payload}
    assert sha == result.request_sha256 == canonical_sha256(solicitud)


@pytest.mark.parametrize("autonomy", ["A1", "A2"])
@pytest.mark.parametrize("clave", ["schema_version", "stage", "autonomy", "request_sha256"])
def test_payload_no_puede_pisar_las_claves_comunes(
    tmp_path: Path, clave: str, autonomy: str
) -> None:
    # Pisarlas en silencio cambiaría lo que se hashea sin que el gate lo notara
    # (y `request_sha256` rompería la relación 15): es un error de programación.
    ctx = RunContext("demo", tmp_path, "T")
    with pytest.raises(ValueError, match=rf"{clave}.*claves comunes de la solicitud"):
        _solicitar(ctx, payload={clave: "otro", "included": 1}, autonomy=autonomy)
    assert not (ctx.run_dir / "reporte" / "review_request.yml").exists()
    assert ctx.ledger.read_all() == []


def test_auto_approve_repetido_tras_oscilar_explica_la_aprobacion_de_demostracion(
    tmp_path: Path,
) -> None:
    # X → Y → X con --auto-approve: no hay decision.yml donde "cambiar `reason`"; la
    # decisión es la sintética de la demostración y lo que falta es una humana.
    ctx = RunContext("demo", tmp_path, "T")
    for incluidos in (1, 2):  # la solicitud cambia y la demostración aprueba cada una
        resultado = _solicitar(ctx, payload={"included": incluidos}, auto_approve=True)
        assert resultado.status == "approved"

    with pytest.raises(DecisionFileError) as excinfo:
        _solicitar(ctx, payload={"included": 1}, auto_approve=True)

    mensaje = str(excinfo.value)
    assert "aprobación de demostración" in mensaje
    assert str(ctx.stage_dir("reporte") / "decision.yml") in mensaje
    assert "`reason`" not in mensaje
    assert [e.action for e in ctx.ledger.read_all()] == ["approve", "approve"]


def test_decision_humana_repetida_tras_oscilar_pide_cambiar_reason(tmp_path: Path) -> None:
    # Guarda del otro camino: con un decision.yml humano, el mensaje sigue pidiendo
    # cambiar `reason` (ahí sí hay un fichero que editar).
    ctx = RunContext("demo", tmp_path, "T")
    texto = 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n'
    primera = _solicitar(ctx, payload={"included": 1})
    _decidir(ctx, texto, primera.request_sha256)
    assert _solicitar(ctx, payload={"included": 1}).status == "approved"
    segunda = _solicitar(ctx, payload={"included": 2})  # decision.yml obsoleta: pausa
    assert segunda.status == "paused"
    _decidir(ctx, texto, segunda.request_sha256)
    assert _solicitar(ctx, payload={"included": 2}).status == "approved"

    _decidir(ctx, texto, primera.request_sha256)  # vuelve a la primera, decisión idéntica
    with pytest.raises(DecisionFileError, match="cambia `reason` en decision.yml"):
        _solicitar(ctx, payload={"included": 1})
