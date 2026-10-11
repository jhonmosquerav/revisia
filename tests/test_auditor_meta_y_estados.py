"""El auditor ancla el meta-análisis a la instantánea y diagnostica bien los estados intermedios.

Revisión final de la Ola 1, grupo E, sobre corridas reales (``corrida``, ``detener_corrida`` y
``_correr`` de ``conftest``):

- E1: con efectos en ``00_protocol/effects.yml``, borrar el meta-análisis (fichero, copia,
  entregable y CSV) o inflarlo ya no deja la corrida APTA; sin efectos, no se exige nada.
- E2: una pausa en el primer gate y una interrupción dentro de ``reporte`` se auditan como lo
  que son (la reinclusión D14 tras completar la fija ``test_audit_hitl_registro.py``).
- E3/E4: ``human:desconocido`` en el gate final da WARN; un reporte rechazado no pide
  «adjudica o rechaza».
- E5: ``agreement.json``, los textos en caché y ``prisma_flow.md`` editados se detectan.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

import pytest
import yaml
from audit_fixtures import auditar, edit_json, edit_yaml, fila
from conftest import (
    _correr,
    adjudicar_auditoria,
    busqueda_auditoria,
    etiquetar_auditoria,
    proveedor_auditoria,
    proveedor_con_cita_marcada,
)
from fakes import fetch_disponible
from hitl_helpers import responder_gate

from revisia.audit.artifacts import AuditContext, load_run
from revisia.audit.checks_flow import collect_relations
from revisia.config import load_protocol
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext, RunInterrupted
from revisia.orchestration.snapshot import read_run_info

META = "08_meta/meta_analysis.json"
META_RECALCULADO = "§8.1 · 08_meta/meta_analysis.json == meta_analyze(00_protocol/effects.yml)"
DESCONOCIDO = "human:desconocido"


def _relaciones(run: Path) -> dict[str, tuple[bool | None, str]]:
    """Las relaciones de ``arithmetic`` (``nombre → (ok, detalle)``), sin nombres repetidos."""
    relaciones = collect_relations(AuditContext(load_run(run)))
    nombres = [r.name for r in relaciones]
    assert len(nombres) == len(set(nombres)), nombres
    return {r.name: (r.ok, r.detail) for r in relaciones}


def _sin_copia_del_meta(manifiesto: dict) -> None:
    manifiesto.pop("meta_analysis", None)


# ── E1 · el meta-análisis anclado a 00_protocol/effects.yml ──────────────────


def test_borrar_el_meta_analisis_entero_ya_no_deja_la_corrida_apta(corrida) -> None:
    # Antes: el fichero, su copia, el entregable y el CSV solo se exigían si el manifiesto traía
    # la clave, y borrar los cuatro dejaba la corrida APTA.
    (corrida / META).unlink()
    edit_yaml(corrida / "manifest.yml", _sin_copia_del_meta)
    (corrida / "deliverable" / "meta_analisis.md").unlink()
    (corrida / "deliverable" / "interop" / "effects_metafor.csv").unlink()

    report = auditar(corrida)

    assert not report.publishable
    stage = fila(report, "stage_artifacts")
    assert stage.status == "FAIL" and META in stage.detail
    deliverable = fila(report, "deliverable")
    assert deliverable.status == "FAIL"
    assert "meta_analisis.md (falta)" in deliverable.detail
    assert "interop/effects_metafor.csv (falta)" in deliverable.detail
    relaciones = _relaciones(corrida)
    assert relaciones["§9.3 · copia `meta_analysis` del manifiesto"][0] is False
    assert relaciones[META_RECALCULADO][0] is False


def test_inflar_la_estimacion_del_meta_analisis_falla(corrida) -> None:
    def _por_tres(meta: dict) -> None:
        meta["random"]["estimate"] *= 3

    edit_json(corrida / META, _por_tres)
    edit_yaml(corrida / "manifest.yml", lambda m: _por_tres(m["meta_analysis"]))

    report = auditar(corrida)

    assert not report.publishable
    ok, detalle = _relaciones(corrida)[META_RECALCULADO]
    assert ok is False and "random.estimate" in detalle
    assert META_RECALCULADO in fila(report, "arithmetic").detail


def test_el_csv_prisma2020_declara_los_k_estudios_del_meta_analisis(corrida) -> None:
    relaciones = _relaciones(corrida)
    clave = "11 · CSV total_studies_ma == k de 00_protocol/effects.yml"
    assert relaciones[clave][0] is True

    ruta = corrida / "deliverable" / "interop" / "prisma2020_flow.csv"
    filas = list(csv.reader(io.StringIO(ruta.read_text(encoding="utf-8"))))
    columna = filas[0].index("n")
    (fila_ma,) = [f for f in filas if f[0] == "total_studies_ma"]
    assert fila_ma[columna] == "4"
    fila_ma[columna] = "40"
    salida = io.StringIO()
    csv.writer(salida, lineterminator="\n").writerows(filas)
    ruta.write_text(salida.getvalue(), encoding="utf-8")

    assert _relaciones(corrida)[clave][0] is False


@pytest.fixture(scope="module")
def _corrida_sin_efectos(tmp_path_factory: pytest.TempPathFactory, protocolo_auditoria) -> Path:
    protocolo = tmp_path_factory.mktemp("sin-efectos") / "proto"
    shutil.copytree(protocolo_auditoria, protocolo)
    (protocolo / "effects.yml").unlink()
    return _correr(tmp_path_factory.mktemp("sin-efectos-runs"), protocolo, parar_en=None)


@pytest.fixture
def corrida_sin_efectos(_corrida_sin_efectos: Path, tmp_path: Path) -> Path:
    destino = tmp_path / "runs" / _corrida_sin_efectos.name
    shutil.copytree(_corrida_sin_efectos, destino)
    return destino


def test_sin_efectos_no_se_exige_meta_analisis_ni_se_avisa(corrida_sin_efectos) -> None:
    report = auditar(corrida_sin_efectos)

    assert report.publishable
    assert not (corrida_sin_efectos / META).exists()
    assert fila(report, "deliverable").status == "PASS"  # sin k > incluidos que avisar
    relaciones = _relaciones(corrida_sin_efectos)
    assert relaciones["11 · CSV total_studies_ma == k de 00_protocol/effects.yml"][0] is True
    assert META_RECALCULADO not in relaciones


def test_sin_efectos_un_meta_analisis_en_disco_es_inventado(corrida_sin_efectos, corrida) -> None:
    (corrida_sin_efectos / META).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(corrida / META, corrida_sin_efectos / META)

    ok, detalle = _relaciones(corrida_sin_efectos)[META_RECALCULADO]

    assert ok is False and "sin efectos" in detalle
    assert not auditar(corrida_sin_efectos).publishable


# ── E2 · estados intermedios ─────────────────────────────────────────────────


def test_pausa_en_el_primer_gate_falla_el_gate_final_en_vez_de_no_aplicar(
    detener_corrida,
) -> None:
    # Con el ledger aún vacío, `final_gate` devolvía N/A antes de mirar el estado (§9.2).
    run = detener_corrida(aprobados=())

    report = auditar(run)

    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "corrida en pausa en `screening_ta`: sin decisión final" in final_gate.detail


def test_interrumpida_dentro_del_reporte_no_exige_el_manifiesto(
    detener_corrida, protocolo_auditoria: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Interrumpida en `reporte` antes de escribir el entregable y el manifiesto: antes `reporte`
    # contaba como alcanzado también en una interrupción y daba FAIL falsos por lo que no existe.
    run = detener_corrida(aprobados=("screening_ta", "screening_ft", "extraccion"))
    responder_gate(run, "rob")

    def _disco_lleno(*_a, **_k):
        raise OSError("No queda espacio en el disco")

    monkeypatch.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
    monkeypatch.setattr(pipeline_mod, "_write_deliverables", _disco_lleno)
    protocol = load_protocol(protocolo_auditoria)
    with pytest.raises(RunInterrupted):
        run_pipeline(
            protocol,
            protocolo_auditoria,
            RunContext.open(run),
            search_fn=busqueda_auditoria,
            fetch_fn=fetch_disponible,
        )
    info = read_run_info(run)
    assert (info.status, info.stage) == ("interrupted", "reporte")
    assert not (run / "manifest.yml").exists()

    report = auditar(run)

    assert report.state is not None
    assert (report.state.status, report.state.pending_stage) == ("interrupted", "reporte")
    assert "reporte" not in report.state.reached
    stage = fila(report, "stage_artifacts")
    assert stage.status == "PASS", stage.detail
    assert fila(report, "deliverable").status == "N/A"
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "corrida interrumpida en `reporte`" in final_gate.detail


# ── E3 · `human:desconocido` en el gate final y en las adjudicaciones ────────


def _revisora_sin_nombre_en_el_reporte(stage: str, solicitud: dict) -> dict | None:
    respuesta = adjudicar_auditoria(stage, solicitud)
    if stage != "reporte":
        return respuesta
    return {**(respuesta or {}), "actor": DESCONOCIDO}


def test_gate_final_aprobado_por_human_desconocido_da_warn(
    tmp_path: Path, protocolo_auditoria: Path
) -> None:
    run = _correr(
        tmp_path,
        protocolo_auditoria,
        parar_en=None,
        etiquetar=lambda s, sol: (
            {"actor": DESCONOCIDO} if s == "reporte" else etiquetar_auditoria(s, sol)
        ),
    )

    report = auditar(run)

    final_gate = fila(report, "final_gate")
    assert final_gate.status == "WARN"
    assert f"actor `{DESCONOCIDO}` (declara `actor:` en decision.yml)" in final_gate.detail
    assert report.publishable  # un WARN: no bloquea, pero hay que declararlo


def test_citas_adjudicadas_por_human_desconocido_dan_el_mismo_aviso(
    tmp_path: Path, protocolo_con_cita_marcada: Path
) -> None:
    run = _correr(
        tmp_path,
        protocolo_con_cita_marcada,
        parar_en=None,
        proveedor=proveedor_con_cita_marcada,
        etiquetar=_revisora_sin_nombre_en_el_reporte,
    )

    report = auditar(run)

    grounding = fila(report, "grounding")
    assert grounding.status == "WARN"
    assert f"actor `{DESCONOCIDO}` (declara `actor:` en decision.yml)" in grounding.detail
    assert fila(report, "final_gate").status == "WARN"


# ── E4 · grounding de un reporte rechazado ───────────────────────────────────


def test_grounding_de_un_reporte_rechazado_no_pide_rechazarlo(
    tmp_path: Path, protocolo_con_cita_marcada: Path
) -> None:
    run = _correr(
        tmp_path,
        protocolo_con_cita_marcada,
        parar_en=None,
        rechazar="reporte",
        proveedor=proveedor_con_cita_marcada,
    )

    grounding = fila(auditar(run), "grounding")

    assert grounding.status == "FAIL"
    assert "quedaron sin aprobar: el reporte se rechazó" in grounding.detail
    assert "rechaza el reporte" not in grounding.detail


# ── E5 · derivados editados ──────────────────────────────────────────────────


def test_agreement_editado_con_su_copia_no_es_el_acuerdo_aprobado(corrida) -> None:
    # FG5: la relación de copias solo los comparaba entre sí; la solicitud (hasheada) no.
    def _otro(acuerdo: dict) -> None:
        acuerdo["value_agreement"] = 0.123

    edit_json(corrida / "05_extraction" / "agreement.json", _otro)
    edit_yaml(corrida / "manifest.yml", lambda m: _otro(m["extraction_agreement"]))

    report = auditar(corrida)

    request_hash = fila(report, "request_hash")
    assert request_hash.status == "FAIL"
    assert "no es el acuerdo de la solicitud aprobada" in request_hash.detail
    assert "value_agreement" in request_hash.detail
    assert not report.publishable


@pytest.mark.parametrize("cambio", ["editado", "borrado"])
def test_texto_completo_en_cache_editado_o_borrado_falla(corrida, cambio: str) -> None:
    # FG2: lo que la IA cribó, extrajo y verificó salía de esos textos.
    (texto,) = sorted((corrida / "04_fulltext" / "texts").iterdir())[:1]
    if cambio == "editado":
        texto.write_bytes(texto.read_bytes() + b" (editado)")
    else:
        texto.unlink()

    ok, detalle = _relaciones(corrida)[
        "7 · textos de 04_fulltext/texts == text_sha256/n_chars de 04_fulltext/retrieval.json"
    ]

    assert ok is False and "texto ausente, ilegible o distinto" in detalle
    assert not auditar(corrida).publishable


def test_diagrama_prisma_editado_falla(corrida) -> None:
    # FG6: el diagrama del entregable es el de manifest.counts.
    nombre = "16a · deliverable/prisma_flow.md == render(manifest.counts)"
    assert _relaciones(corrida)[nombre][0] is True
    ruta = corrida / "deliverable" / "prisma_flow.md"
    texto = ruta.read_text(encoding="utf-8")
    assert "Registros identificados (n = 7)" in texto
    ruta.write_text(texto.replace("(n = 7)", "(n = 70)", 1), encoding="utf-8")

    assert _relaciones(corrida)[nombre][0] is False
    assert not auditar(corrida).publishable


def test_las_relaciones_nuevas_pasan_en_la_corrida_real(corrida) -> None:
    relaciones = _relaciones(corrida)
    nuevas = [
        META_RECALCULADO,
        "11 · CSV total_studies_ma == k de 00_protocol/effects.yml",
        "11 · CSV total_reports_ma == k de 00_protocol/effects.yml",
        "7 · textos de 04_fulltext/texts == text_sha256/n_chars de 04_fulltext/retrieval.json",
        "16a · deliverable/prisma_flow.md == render(manifest.counts)",
    ]
    assert [(n, relaciones[n][0]) for n in nuevas] == [(n, True) for n in nuevas]
    meta = json.loads((corrida / META).read_text(encoding="utf-8"))
    assert meta["k"] == len(
        yaml.safe_load((corrida / "00_protocol" / "effects.yml").read_text(encoding="utf-8"))[
            "effects"
        ]
    )
