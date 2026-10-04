"""Infraestructura del auditor: carga que nunca lanza, estado, N/A, fail-closed y render.

Spec 2026-10-04 §9.1-§9.2. Las corridas salen de la fixture ``corrida``
(``tests/conftest.py``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import pytest
from audit_fixtures import auditar, fila, pausar_en_screening_ft
from pydantic import AfterValidator, TypeAdapter

import revisia.audit as audit_pkg
from revisia.audit import CHECKS, AuditCheck, AuditReport, CheckSpec, render_audit_md
from revisia.audit.artifacts import (
    AuditContext,
    Loaded,
    load_run,
    read_json,
    read_jsonl,
    read_text,
    read_yaml,
    validate,
)
from revisia.audit.render import _md_cell
from revisia.audit.state import derive_state
from revisia.config import STAGES
from revisia.provenance.ledger import DecisionEntry, DecisionLedger
from revisia.schemas.artifacts import GateSummary, RunInfo

REPO = Path(__file__).resolve().parent.parent

# ── Loaders: nunca lanzan ───────────────────────────────────────────────


def test_loaders_ausente_directorio_y_raiz_inesperada(tmp_path) -> None:
    (tmp_path / "carpeta.json").mkdir()
    (tmp_path / "lista.yml").write_text("- a\n- b\n", encoding="utf-8")
    (tmp_path / "texto.json").write_text('"hola"', encoding="utf-8")
    ausente = read_json(tmp_path, "no-existe.json")
    assert (ausente.present, ausente.ok, ausente.error) == (False, False, None)
    assert read_text(tmp_path, "carpeta.json").error == "no es un fichero"
    assert "la raíz es lista, no mapa" in read_yaml(tmp_path, "lista.yml").error
    assert "la raíz es str" in read_json(tmp_path, "texto.json").error


@pytest.mark.parametrize(
    "contenido",
    [b"{\n", "{}".encode("utf-16"), b"\x89PNG\r\n\x1a\n\x00\xff\xfe"],
    ids=["json-truncado", "utf16", "binario"],
)
def test_loaders_json_invalido_utf16_o_binario(tmp_path, contenido: bytes) -> None:
    (tmp_path / "x.json").write_bytes(contenido)
    loaded = read_json(tmp_path, "x.json")
    assert loaded.present and not loaded.ok and loaded.error


def test_read_jsonl_conserva_las_lineas_legibles_y_numera_las_corruptas(tmp_path) -> None:
    (tmp_path / "x.jsonl").write_text('{"a": 1}\n\nno-json\n{"b": 2}\n', encoding="utf-8")
    loaded = read_jsonl(tmp_path, "x.jsonl")
    assert loaded.value == [(1, {"a": 1}), (4, {"b": 2})]
    assert loaded.error.startswith("línea 3: JSON inválido")


def test_manifiesto_con_raiz_lista_no_revienta(corrida) -> None:
    (corrida / "manifest.yml").write_text("- slug: demo\n", encoding="utf-8")
    report = auditar(corrida)
    assert fila(report, "manifest").status == "FAIL"
    assert len(report.checks) == len(CHECKS)


@pytest.mark.parametrize(
    "contenido",
    ["slug: demo\n".encode("utf-16"), b"\x00\x01\xff\xfe binario"],
    ids=["utf16", "binario"],
)
def test_manifiesto_utf16_o_binario_no_revienta(corrida, contenido: bytes) -> None:
    (corrida / "manifest.yml").write_bytes(contenido)
    report = auditar(corrida)
    assert fila(report, "manifest").status == "FAIL"
    assert fila(report, "provenance").status == "N/A"


# Los loaders no lanzan ni con YAML hostil (spec §9.1; revisión de la Tarea 4).


@pytest.mark.parametrize(
    "contenido",
    ["x: !!timestamp foo\n", "x: !!bool maybe\n"],
    ids=["timestamp-AttributeError", "bool-KeyError"],
)
def test_manifiesto_con_etiqueta_yaml_hostil_es_fail_y_no_error_interno(
    corrida, contenido: str
) -> None:
    """PyYAML lanza ``AttributeError``/``KeyError`` (no ``YAMLError``) ante estas etiquetas."""
    (corrida / "manifest.yml").write_text(contenido, encoding="utf-8")
    cargado = read_yaml(corrida, "manifest.yml")
    assert cargado.present and not cargado.ok
    assert cargado.error.startswith("YAML inválido")
    report = auditar(corrida)
    manifiesto = fila(report, "manifest")
    assert manifiesto.status == "FAIL"
    assert "YAML inválido" in manifiesto.detail
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []
    assert len(report.checks) == len(CHECKS)


def test_read_text_no_lanza_si_el_sistema_de_ficheros_falla(tmp_path, monkeypatch) -> None:
    def _sin_acceso(self, *args, **kwargs):
        raise PermissionError("sin acceso")

    monkeypatch.setattr(Path, "exists", _sin_acceso)
    cargado = read_text(tmp_path, "x.json")
    assert cargado.present and not cargado.ok
    assert "PermissionError" in cargado.error


def test_read_json_y_read_jsonl_no_lanzan_ante_una_excepcion_inesperada(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "x.json").write_text("{}", encoding="utf-8")
    (tmp_path / "x.jsonl").write_text("{}\n", encoding="utf-8")

    def _roto(*args, **kwargs):
        raise TypeError("json roto")

    monkeypatch.setattr(json, "loads", _roto)
    assert "TypeError" in read_json(tmp_path, "x.json").error
    assert "línea 1" in read_jsonl(tmp_path, "x.jsonl").error


def test_validate_no_lanza_si_el_validador_revienta() -> None:
    def _revienta(_valor: int) -> int:
        raise TypeError("validador roto")

    adaptador = TypeAdapter(Annotated[int, AfterValidator(_revienta)])
    resultado = validate(Loaded("x.json", True, 1), adaptador)
    assert resultado.present and not resultado.ok
    assert "TypeError" in resultado.error


# Anidamiento profundo: `CSafeLoader` desborda la pila nativa a ~2 680 niveles y mata
# el proceso (0xC00000FD en Windows) sin que ningún `except` lo atrape. Cada vector
# corre en un subproceso: si el guarda falla, se ve un código de salida distinto de 0
# y no se cae la sesión de pytest.
_VECTORES_ANIDADOS = [
    pytest.param(lambda: "x: " + "[" * 10_000 + "\n", id="corchetes"),
    pytest.param(lambda: "- " * 10_000 + "x\n", id="indicadores-de-bloque-encadenados"),
    pytest.param(
        lambda: "".join(" " * i + "a:\n" for i in range(3_000)) + " " * 3_000 + "z: 1\n",
        id="sangria",
    ),
]

_SCRIPT_AUDITAR = (
    "import json, sys\n"
    "from revisia.audit import run_audit\n"
    "informe = run_audit(sys.argv[1])\n"
    "print(json.dumps([[c.check_id, c.status, c.detail] for c in informe.checks]))\n"
)


@pytest.mark.parametrize("texto", _VECTORES_ANIDADOS)
def test_manifiesto_muy_anidado_no_tumba_el_proceso_del_auditor(corrida, texto) -> None:
    (corrida / "manifest.yml").write_text(texto(), encoding="utf-8")
    proceso = subprocess.run(
        [sys.executable, "-c", _SCRIPT_AUDITAR, str(corrida)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )
    mensaje = f"el auditor murió (código {proceso.returncode}): {proceso.stderr[-500:]}"
    assert proceso.returncode == 0, mensaje
    filas = {i: (status, detalle) for i, status, detalle in json.loads(proceso.stdout)}
    assert filas["manifest"][0] == "FAIL"
    assert "anidada" in filas["manifest"][1]
    assert [i for i, (_, detalle) in filas.items() if "error interno" in detalle] == []
    assert len(filas) == len(CHECKS)


def test_guarda_de_anidamiento_respeta_sus_limites(tmp_path) -> None:
    def cargar(texto: str, **kwargs) -> Loaded:
        (tmp_path / "x.yml").write_text(texto, encoding="utf-8")
        return read_yaml(tmp_path, "x.yml", **kwargs)

    # 500 niveles de corchetes pasan; 501 se rechazan antes de cargar.
    assert cargar("x: " + "[" * 500 + "]" * 500 + "\n").ok
    assert "anidada" in cargar("x: " + "[" * 501 + "]" * 501 + "\n").error
    assert "anidada" in cargar("x: " + "{a: " * 501 + "1" + "}" * 501 + "\n").error
    # Los corchetes entre comillas o en un comentario no cuentan.
    assert cargar('x: "' + "[" * 5_000 + '"\n').ok
    assert cargar("x: '" + "{" * 5_000 + "'\n").ok
    assert cargar("x: 1  # " + "[" * 5_000 + "\n").ok
    # Una sangría de 2 000 espacios pasa; de 2 001 no.
    assert cargar("x: |\n" + " " * 2_000 + "t\n").ok
    assert "anidada" in cargar("x: |\n" + " " * 2_001 + "t\n").error
    # Hasta 500 indicadores `- ` encadenados en una línea pasan; 501 no.
    assert cargar("- " * 500 + "x\n", root=list).ok
    assert "anidada" in cargar("- " * 501 + "x\n", root=list).error
    # Un manifiesto normal (listas y mapas de profundidad < 20) no se toca.
    assert cargar("a:\n  - b: [1, 2, {c: d}]\n  - e: 'f'\n").value == {
        "a": [{"b": [1, 2, {"c": "d"}]}, {"e": "f"}]
    }


def test_ledger_con_separadores_unicode_en_el_texto_conserva_la_entrada(corrida) -> None:
    """``str.splitlines`` también corta en U+2028/U+2029/U+0085; el ledger los escribe tal cual."""
    ruta = corrida / "decisions_ledger.jsonl"
    antes = len(AuditContext(load_run(corrida)).ledger.entries)
    motivo = "uno\u2028dos\u2029tres\u0085cuatro"
    DecisionLedger(ruta).append(
        DecisionEntry(
            stage="screening_ta",
            actor="human:ana",
            autonomy="A1",
            action="label",
            target="10.1000/llm-1",
            detail={"reason": motivo},
        )
    )
    assert "\u2028" in ruta.read_text(encoding="utf-8")  # el separador va crudo en el fichero
    vista = AuditContext(load_run(corrida)).ledger
    assert vista.errors == ()
    assert len(vista.entries) == antes + 1
    assert vista.entries[-1][1].detail["reason"] == motivo


# ── Fail-closed e invariante N/A ⇒ FAIL ────────────────────────────────


def test_check_que_revienta_es_fail_y_el_resto_sigue(corrida, monkeypatch) -> None:
    def _roto(_ctx):
        raise KeyError("campo-que-no-existe")

    roto = tuple(
        CheckSpec(s.check_id, s.item_ref, s.stage, _roto) if s.check_id == "gold" else s
        for s in CHECKS
    )
    monkeypatch.setattr(audit_pkg, "CHECKS", roto)
    report = auditar(corrida)
    gold = fila(report, "gold")
    assert gold.status == "FAIL"
    assert "error interno del auditor (KeyError)" in gold.detail
    assert "no se considera verificada" in gold.detail
    assert len(report.checks) == len(CHECKS)
    assert fila(report, "final_gate").status == "PASS"


def test_invariante_na_sin_fail_se_convierte_en_fail() -> None:
    checks = [
        AuditCheck("a", "x", "PASS", "ok"),
        AuditCheck("b", "x", "N/A", "no aplica: algo"),
    ]
    resultado = audit_pkg._enforce_invariant(checks)
    assert [c.status for c in resultado] == ["PASS", "FAIL"]
    assert "N/A sin ningún FAIL" in resultado[1].detail
    con_fail = [*checks, AuditCheck("c", "x", "FAIL", "roto")]
    assert audit_pkg._enforce_invariant(con_fail) == con_fail


# ── Estado de la corrida ────────────────────────────────────────────────


def _gate(stage: str, action: str = "approve", actor: str = "human:ana") -> GateSummary:
    return GateSummary(
        stage=stage, action=action, actor=actor, autonomy="A1", timestamp_utc="2026-10-04T12:00Z"
    )


def _gates(*stages: str, **acciones: str) -> dict[str, GateSummary]:
    return {s: _gate(s, acciones.get(s, "approve")) for s in stages}


def test_derive_state_completada_y_desconocida() -> None:
    completa = _gates("screening_ta", "screening_ft", "extraccion", "rob", "reporte")
    estado = derive_state(run_info=None, gates=completa, requests=set(), ledger_ok=True)
    assert (estado.status, estado.reached) == ("completed", frozenset(STAGES))
    desconocido = derive_state(run_info=None, gates={}, requests=set(), ledger_ok=False)
    assert (desconocido.status, desconocido.reached) == ("unknown", frozenset(STAGES))
    assert "se exige todo" in desconocido.describe()


def test_derive_state_pausa_en_screening_ft() -> None:
    estado = derive_state(
        run_info=None,
        gates=_gates("screening_ta"),
        requests={"screening_ta", "screening_ft"},
        ledger_ok=True,
    )
    assert (estado.status, estado.pending_stage) == ("paused", "screening_ft")
    assert estado.reached == frozenset({"protocolo", "busqueda", "dedup", "screening_ta"})
    assert estado.na_detail() == (
        "no aplica: corrida en pausa en `screening_ft`; se verificará al reanudar."
    )


def test_derive_state_sin_solicitud_es_interrumpida_y_rechazo_gana() -> None:
    interrumpida = derive_state(
        run_info=None, gates=_gates("screening_ta"), requests={"screening_ta"}, ledger_ok=True
    )
    assert (interrumpida.status, interrumpida.pending_stage) == ("interrupted", "screening_ft")
    rechazada = derive_state(
        run_info=None,
        gates=_gates("screening_ta", "screening_ft", screening_ft="reject"),
        requests={"screening_ta", "screening_ft"},
        ledger_ok=True,
    )
    assert (rechazada.status, rechazada.pending_stage) == ("rejected", "screening_ft")
    assert "screening_ft" not in rechazada.reached


def test_derive_state_pausa_o_rechazo_en_reporte_audita_el_reporte() -> None:
    previas = _gates("screening_ta", "screening_ft", "extraccion", "rob")
    estado = derive_state(
        run_info=None, gates=previas, requests={"reporte", *previas}, ledger_ok=True
    )
    assert (estado.status, estado.pending_stage) == ("paused", "reporte")
    assert estado.reached == frozenset(STAGES)


def test_derive_state_run_json_interrumpida() -> None:
    info = RunInfo(
        slug="demo",
        timestamp="20261004-120000",
        started_utc="2026-10-04T12:00:00+00:00",
        engine_version="0.8.0",
        python_version="3.13.0",
        max_results=50,
        mailto_set=False,
        status="interrupted",
        stage="extraccion",
    )
    estado = derive_state(
        run_info=info, gates=_gates("screening_ta"), requests=set(), ledger_ok=False
    )
    assert (estado.status, estado.pending_stage) == ("interrupted", "extraccion")


def test_pausa_en_screening_ft_deja_na_las_etapas_posteriores(corrida) -> None:
    pausar_en_screening_ft(corrida)
    report = auditar(corrida)
    assert report.state is not None
    assert (report.state.status, report.state.pending_stage) == ("paused", "screening_ft")
    for check_id in ("exclusions", "deliverable", "grounding", "manifest", "provenance"):
        assert fila(report, check_id).status == "N/A", check_id
        assert "en pausa en `screening_ft`" in fila(report, check_id).detail
    assert fila(report, "gold").status != "N/A"  # T/A sí se alcanzó
    assert fila(report, "final_gate").status == "FAIL"
    assert not report.publishable


# ── Render ─────────────────────────────────────────────────────────────


def test_md_cell_escapa_barras_y_saltos() -> None:
    assert _md_cell("a|b\nc\r\nd") == "a\\|b<br>c<br>d"


def test_render_escapa_sin_cambiar_el_numero_de_filas(tmp_path) -> None:
    checks = [
        AuditCheck("schemas", "PRISMA 27", "FAIL", "x.json: loc|a: msg\nsegunda línea"),
        AuditCheck("gold", "trAIce M9/R2", "N/A", "no aplica"),
    ]
    markdown = render_audit_md(AuditReport(run_dir=tmp_path, checks=checks))
    filas = [line for line in markdown.splitlines() if line.startswith("| ") and "---" not in line]
    assert len(filas) == 1 + len(checks)  # cabecera + una por check
    assert all(line.count(" | ") == 3 for line in filas)
    assert "loc\\|a: msg<br>segunda línea" in markdown
    assert "➖ N/A" in markdown
    assert "N/A=1" in markdown


def test_render_incluye_el_estado(corrida) -> None:
    markdown = render_audit_md(auditar(corrida))
    assert "Estado deducido: completada" in markdown


def test_cli_audit_muestra_na(corrida, capsys) -> None:
    from revisia.cli import main

    pausar_en_screening_ft(corrida)
    assert main(["audit", str(corrida)]) == 1
    out = capsys.readouterr().out
    assert "➖ N/A  exclusions" in out
    assert "Traceback" not in out
