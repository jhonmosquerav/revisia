"""Búsqueda registrada por el motor: ``search_log``, ``search_window`` y marcas de tiempo.

Spec 2026-10-04 §4.4 (relaciones 1-3 y 14) y §9.3 (filas 6, 18 y 19). La
corrida real usa una búsqueda inyectada (``search_fn``); ``_log_de_bases`` la
convierte en la de una base declarada, como la dejaría ``revisia run``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from audit_fixtures import (
    auditar,
    auditar_en_subproceso,
    edit_json,
    edit_yaml,
    editar_protocolo,
    fila,
)
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import correr_hasta

from revisia.audit import CHECKS
from revisia.audit.artifacts import AuditContext, load_run
from revisia.audit.checks_search import _ficheros_de_cadenas
from revisia.config import load_protocol
from revisia.exports.checklist import engine_search_date
from revisia.llm import preflight as preflight_mod
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext, RunInterrupted
from revisia.provenance.runmeta import sha256_text
from revisia.schemas.artifacts import SearchLog
from revisia.schemas.records import SearchRecord

LOG = "01_search/log.json"
DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _log_de_bases(run, **cambios) -> None:
    """El log de una búsqueda en OpenAlex con su cadena de ``00_protocol/``."""
    cadena = (run / "00_protocol" / "search_strings" / "openalex.txt").read_text("utf-8").strip()

    def _editar(log: dict) -> None:
        entry = log["entries"][0]
        entry.update(
            database="OpenAlex",
            db_key="openalex",
            kind="database",
            declared=True,
            backend="search_backends.openalex_search",
            query=cadena,
            query_origin="file",
            query_file="00_protocol/search_strings/openalex.txt",
            query_sha256=sha256_text(cadena),
        )
        entry.update(cambios)

    edit_json(run / LOG, _editar)


def _anadir_entrada(run, entrada: dict) -> None:
    """Añade al log una entrada de base declarada, sin cadena ni registros."""

    def _editar(log: dict) -> None:
        base = {
            "kind": "database",
            "declared": True,
            "source_db": [],
            "max_results": 25,
            "started_utc": log["started_utc"],
            "finished_utc": log["finished_utc"],
            "n_returned": 0,
        }
        log["entries"].append({**base, **entrada})

    edit_json(run / LOG, _editar)


def _renombrar_cadena(run, nuevo: str) -> None:
    """Cambia el nombre de la cadena congelada de OpenAlex (``openalex.txt``) a ``nuevo``."""
    carpeta = run / "00_protocol" / "search_strings"
    (carpeta / "openalex.txt").rename(carpeta / nuevo)


@pytest.fixture
def normcase_sin_mayusculas(monkeypatch: pytest.MonkeyPatch) -> None:
    """``os.path.normcase`` como en Windows (minúsculas), para que el test valga también en Linux.

    En Windows y macOS el sistema de ficheros no distingue mayúsculas y ``normcase`` lo refleja;
    en Linux es la identidad. Aquí se fija a minúsculas en todas partes.
    """
    monkeypatch.setattr(os.path, "normcase", lambda ruta: os.fspath(ruta).lower())


# ── search_log ─────────────────────────────────────────────────────────


def test_search_log_busqueda_inyectada_advierte(corrida) -> None:
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "búsqueda inyectada (`search_fn`)" in search_log.detail


def test_search_log_base_con_su_cadena_pasa(corrida) -> None:
    _log_de_bases(corrida)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "PASS"
    assert "cada base con su cadena registrada; 7 registros" in search_log.detail


def test_search_log_con_una_sola_entrada_va_en_singular(corrida) -> None:
    _log_de_bases(corrida)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "PASS"
    assert "1 entrada en el log (1 `ok`)" in search_log.detail
    assert "1 entradas" not in search_log.detail


def test_search_log_con_un_solo_registro_va_en_singular(corrida) -> None:
    def _dejar_uno(registros: list) -> None:
        del registros[1:]

    ruta = corrida / "01_search" / "records.json"
    source_db = json.loads(ruta.read_text(encoding="utf-8"))[0]["source_db"]
    edit_json(ruta, _dejar_uno)
    _log_de_bases(corrida, n_returned=1, source_db=[source_db])
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "PASS", search_log.detail
    assert "cada base con su cadena registrada; 1 registro." in search_log.detail


def test_search_log_ausente_falla(corrida) -> None:
    (corrida / LOG).unlink()
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "01_search/log.json ausente" in search_log.detail


def test_search_log_base_declarada_sin_entrada_falla(corrida) -> None:
    _log_de_bases(corrida)
    editar_protocolo(corrida, lambda p: p.update(databases=["OpenAlex", "Europe PMC"]))
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "bases declaradas sin entrada en el log: Europe PMC" in search_log.detail


def test_search_log_cadena_distinta_de_la_instantanea_falla(corrida) -> None:
    _log_de_bases(corrida, query="otra cadena", query_sha256=sha256_text("otra cadena"))
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "cadena distinta de `00_protocol/search_strings/openalex.txt`" in search_log.detail


def test_search_log_query_sha256_falso_falla(corrida) -> None:
    _log_de_bases(corrida, query_sha256="0" * 64)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`query_sha256` no es el hash de la cadena (relación 3)" in search_log.detail


def test_search_log_tope_de_max_results_advierte(corrida) -> None:
    _log_de_bases(corrida, max_results=7)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "7 resultados = max_results (¿truncados?)" in search_log.detail


def test_search_log_base_caida_advierte(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(
        corrida,
        {
            "database": "Crossref",
            "db_key": "crossref",
            "status": "failed",
            "error": "HTTPStatusError: 503",
            "n_returned": 0,
            "source_db": [],
        },
    )
    failures = [{"db": "Crossref", "error": "HTTPStatusError: 503"}]
    (corrida / "01_search" / "failures.json").write_text(json.dumps(failures), encoding="utf-8")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "`Crossref` falló (HTTPStatusError: 503)" in search_log.detail


def test_search_log_importacion_que_falla_advierte(corrida) -> None:
    # Un fichero de `imported/` ilegible (p. ej. un RIS en UTF-16) queda como `failed` en el log y
    # en `failures.json`, igual que una base; la fuente queda fuera de la corrida.
    _log_de_bases(corrida)
    error = "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff"
    _anadir_entrada(
        corrida,
        {
            "database": "imported/scopus.ris",
            "db_key": "imported",
            "kind": "manual_import",
            "status": "failed",
            "error": error,
        },
    )
    (corrida / "01_search" / "failures.json").write_text(
        json.dumps([{"db": "imported/scopus.ris", "error": error}]), encoding="utf-8"
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "`imported/scopus.ris` falló (UnicodeDecodeError" in search_log.detail


def test_search_log_fallo_que_no_esta_en_failures_json_falla(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(
        corrida,
        {"database": "Crossref", "db_key": "crossref", "status": "failed", "error": "x"},
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "no está en 01_search/failures.json (relación 2)" in search_log.detail


def _con_fallback_a_la_pregunta(run) -> None:
    pregunta = "machine learning and large language models for systematic review screening"
    _log_de_bases(
        run,
        query=pregunta,
        query_origin="question_fallback",
        query_file=None,
        query_sha256=sha256_text(pregunta),
    )


def test_search_log_fallback_a_la_pregunta_advierte(corrida) -> None:
    _con_fallback_a_la_pregunta(corrida)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "`OpenAlex`: sin cadena propia, se usó la pregunta (PRISMA-S 8)" in search_log.detail


NOTA_INSTANTANEA = "(la instantánea sí tiene una cadena no vacía para esta base)"


def test_search_log_fallback_con_cadena_no_vacia_en_la_instantanea_lo_dice(corrida) -> None:
    # El motor usa siempre una cadena no vacía: que la instantánea la tenga y el log diga que se
    # usó la pregunta es una manipulación o un fallo. Sigue siendo un WARN (lo manda el spec), pero
    # «sin cadena propia» sería falso y el aviso lo dice.
    _con_fallback_a_la_pregunta(corrida)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "sin cadena propia, se usó la pregunta (PRISMA-S 8) " + NOTA_INSTANTANEA in (
        search_log.detail
    )


def test_search_log_fallback_encuentra_la_cadena_de_la_instantanea_sin_mayusculas(
    corrida, normcase_sin_mayusculas
) -> None:
    _con_fallback_a_la_pregunta(corrida)
    _renombrar_cadena(corrida, "OpenAlex.txt")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert NOTA_INSTANTANEA in search_log.detail


@pytest.mark.parametrize("contenido", [None, "", "  \n"])
def test_search_log_fallback_sin_cadena_en_la_instantanea_no_dice_que_la_tenga(
    corrida, contenido: str | None
) -> None:
    _con_fallback_a_la_pregunta(corrida)
    fichero = corrida / "00_protocol" / "search_strings" / "openalex.txt"
    if contenido is None:
        fichero.unlink()
    else:
        fichero.write_text(contenido, encoding="utf-8")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "sin cadena propia, se usó la pregunta (PRISMA-S 8)" in search_log.detail
    assert NOTA_INSTANTANEA not in search_log.detail


def test_search_log_base_desconocida_falla(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(
        corrida,
        {"database": "Scopsu", "db_key": "scopsu", "status": "unknown", "n_returned": 0},
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`Scopsu`: status `unknown`" in search_log.detail


def test_search_log_registros_que_no_suman_falla(corrida) -> None:
    _log_de_bases(corrida, n_returned=9)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "Σ n_returned 9 ≠ 7 registros en 01_search/records.json (relación 1)" in (
        search_log.detail
    )


# ── search_window desde el log ─────────────────────────────────────────


def _fecha_del_motor(run) -> str:
    log = json.loads((run / LOG).read_text(encoding="utf-8"))
    return log["started_utc"][:10]


def test_search_window_fecha_tecleada_distinta_de_la_del_motor_advierte(corrida) -> None:
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "`executed: 2026-06-26` tecleada distinta de la fecha del motor" in window.detail


def test_search_window_con_la_fecha_del_motor_pasa(corrida) -> None:
    fecha = _fecha_del_motor(corrida)
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed=fecha))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "PASS"
    assert f"búsqueda ejecutada por el motor el {fecha}" in window.detail


# ── timing con run.json y el log ──────────────────────────────────────


def test_timing_log_que_termina_antes_de_empezar_falla(corrida) -> None:
    def _al_reves(log: dict) -> None:
        log["entries"][0]["finished_utc"] = "2026-01-01T00:00:00.5+00:00"

    edit_json(corrida / LOG, _al_reves)
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "finished_utc anterior a started_utc" in timing.detail


def test_timing_resumes_que_no_suben_fallan(corrida) -> None:
    edit_json(corrida / "run.json", lambda info: info["resumes"].reverse())
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "run.json: `resumes` no es ascendente" in timing.detail


def test_timing_reanudacion_anterior_al_inicio_falla(corrida) -> None:
    edit_json(
        corrida / "run.json",
        lambda info: info["resumes"].insert(0, "2026-01-01T00:00:00.5+00:00"),
    )
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "run.json resumes[0] anterior al inicio de la corrida" in timing.detail


# ═══ Más allá del brief: la entrada del log es hostil, y el motor real no da FAIL falso ═══

SIN_ERROR_INTERNO = "error interno"


def _fila_busqueda(run) -> dict[str, tuple[str, str]]:
    informe = auditar(run)
    return {c.check_id: (c.status, c.detail) for c in informe.checks}


# ── search_log: la honestidad de cada entrada ──────────────────────────


def test_search_log_busqueda_inyectada_con_bases_declaradas_no_falla(corrida) -> None:
    # Adaptación 2: una corrida con solo `search_fn` (tests, quien llama a la librería) no
    # buscó las bases declaradas, y eso es el aviso de la inyectada, no un FAIL.
    editar_protocolo(corrida, lambda p: p.update(databases=["OpenAlex", "Crossref", "PubMed"]))
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "sin entrada" not in search_log.detail


def test_search_log_inyectada_junto_a_bases_sigue_pidiendo_las_declaradas(corrida) -> None:
    # La inyectada no cubre bases: si convive con una entrada de base (el motor no lo escribe),
    # las declaradas que faltan se echan en falta igual.
    _anadir_entrada(corrida, {"database": "OpenAlex", "db_key": "openalex", "status": "ok"})
    editar_protocolo(corrida, lambda p: p.update(databases=["OpenAlex", "Crossref"]))
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "bases declaradas sin entrada en el log: Crossref" in search_log.detail


def test_search_log_sin_bases_declaradas_no_echa_nada_en_falta(corrida) -> None:
    # Sin `databases` el motor busca en OpenAlex (`declared: false`).
    _log_de_bases(corrida, declared=False)
    editar_protocolo(corrida, lambda p: p.update(databases=[]))
    assert fila(auditar(corrida), "search_log").status == "PASS"


def test_search_log_sin_protocolo_legible_advierte_y_no_da_pass(corrida) -> None:
    _log_de_bases(corrida)
    (corrida / "00_protocol" / "protocol.yml").unlink()

    def _sin_protocolo(manifiesto: dict) -> None:
        del manifiesto["protocol"]

    edit_yaml(corrida / "manifest.yml", _sin_protocolo)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "bases declaradas no verificables" in search_log.detail


def test_search_log_sin_entradas_falla(corrida) -> None:
    edit_json(corrida / LOG, lambda log: log.update(entries=[]))
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "el log no tiene ninguna entrada" in search_log.detail


def test_search_log_invalido_falla_con_el_motivo(corrida) -> None:
    (corrida / LOG).write_text('{"started_utc": 5', encoding="utf-8")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "inválido (JSON inválido" in search_log.detail


def test_search_log_base_caida_sin_error_falla(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(
        corrida, {"database": "Crossref", "db_key": "crossref", "status": "failed", "error": None}
    )
    (corrida / "01_search" / "failures.json").write_text(
        json.dumps([{"db": "Crossref", "error": ""}]), encoding="utf-8"
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`Crossref`: `failed` sin error o con registros (relación 2)" in search_log.detail


def test_search_log_base_caida_con_registros_falla(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(
        corrida,
        {
            "database": "Crossref",
            "db_key": "crossref",
            "status": "failed",
            "error": "HTTPStatusError: 503",
            "source_db": ["Crossref"],
        },
    )
    (corrida / "01_search" / "failures.json").write_text(
        json.dumps([{"db": "Crossref", "error": "HTTPStatusError: 503"}]), encoding="utf-8"
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`failed` sin error o con registros" in search_log.detail


def test_search_log_fallo_de_failures_json_sin_entrada_failed_falla(corrida) -> None:
    # Un log al que se le quitó el fallo (la base figura `ok` con 0 registros) dejaba todas las
    # demás relaciones en pie: lo delata `failures.json`, que el motor deriva del log.
    _log_de_bases(corrida)
    _anadir_entrada(corrida, {"database": "Crossref", "db_key": "crossref", "status": "ok"})
    (corrida / "01_search" / "failures.json").write_text(
        json.dumps([{"db": "Crossref", "error": "HTTPStatusError: 503"}]), encoding="utf-8"
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "failures.json lista Crossref sin entrada `failed` en el log" in search_log.detail


def test_search_log_failures_json_ilegible_falla(corrida) -> None:
    _log_de_bases(corrida)
    (corrida / "01_search" / "failures.json").write_text("{", encoding="utf-8")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "01_search/failures.json ilegible" in search_log.detail


def test_search_log_base_manual_sin_importados_advierte(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(corrida, {"database": "Scopus", "db_key": "scopus", "status": "manual_only"})
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "`Scopus` es de importación manual y no hay registros importados" in search_log.detail


def test_search_log_entrada_ok_sin_cadena_falla(corrida) -> None:
    # Quitarle la cadena a una búsqueda `ok` esquivaría la comparación con la instantánea.
    _log_de_bases(corrida, query=None, query_sha256=None, query_origin=None, query_file=None)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "sin cadena o sin su origen registrados (PRISMA-S 8)" in search_log.detail


def test_search_log_entrada_ok_sin_origen_de_la_cadena_falla(corrida) -> None:
    # Sin `query_origin` desaparecía el aviso del fallback a la pregunta.
    pregunta = "machine learning and large language models for systematic review screening"
    _log_de_bases(
        corrida,
        query=pregunta,
        query_sha256=sha256_text(pregunta),
        query_origin=None,
        query_file=None,
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "sin cadena o sin su origen registrados" in search_log.detail


def test_search_log_origen_y_fichero_que_no_concuerdan_falla(corrida) -> None:
    _log_de_bases(corrida, query_file=None)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`query_origin` y `query_file` no concuerdan (relación 3)" in search_log.detail


def test_search_log_cadena_en_otro_fichero_falla(corrida) -> None:
    _log_de_bases(corrida, query_file="00_protocol/search_strings/otra.txt")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "la cadena no está en `00_protocol/search_strings/openalex.txt`" in search_log.detail


def test_search_log_cadena_cuya_instantanea_desaparecio_falla(corrida) -> None:
    _log_de_bases(corrida)
    (corrida / "00_protocol" / "search_strings" / "openalex.txt").unlink()
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "la cadena no está en" in search_log.detail


def test_search_log_db_key_incoherente_con_la_base_falla(corrida) -> None:
    _log_de_bases(corrida, db_key="crossref")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`db_key` no corresponde a la base" in search_log.detail


def test_search_log_n_returned_negativo_falla(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(
        corrida, {"database": "Crossref", "db_key": "crossref", "status": "ok", "n_returned": -3}
    )
    _log_de_bases(corrida, n_returned=10)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`n_returned` negativo (-3)" in search_log.detail


def test_search_log_source_db_distinto_de_los_registros_falla(corrida) -> None:
    _log_de_bases(corrida, source_db=["OpenAlex"])
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "source_db del log [OpenAlex] ≠ los de records.json [Crossref, OpenAlex]" in (
        search_log.detail
    )


def test_search_log_sin_records_json_falla(corrida) -> None:
    _log_de_bases(corrida)
    (corrida / "01_search" / "records.json").unlink()
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "01_search/records.json ausente o inválido" in search_log.detail


def test_search_log_importacion_sin_huella_falla(corrida) -> None:
    _log_de_bases(corrida, n_returned=6, source_db=["OpenAlex"])
    _anadir_entrada(
        corrida,
        {
            "database": "imported/scopus.ris",
            "db_key": "imported",
            "kind": "manual_import",
            "status": "ok",
            "source_db": ["imported-RIS"],
            "n_returned": 1,
            "file_sha256": None,
        },
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`imported/scopus.ris`: importación sin huella del fichero" in search_log.detail


# ── search_log: entrada hostil ─────────────────────────────────────────


def _sin_error_interno(informe) -> None:
    assert [c.check_id for c in informe.checks if SIN_ERROR_INTERNO in c.detail] == []
    assert len(informe.checks) == len(CHECKS)


def test_search_log_con_cadena_de_50000_caracteres_se_acota(corrida) -> None:
    enorme = "q" * 50_000
    _log_de_bases(corrida, query=enorme, query_sha256=sha256_text(enorme))
    informe = auditar(corrida)
    search_log = fila(informe, "search_log")
    assert search_log.status == "FAIL"
    assert "cadena distinta de" in search_log.detail
    assert len(search_log.detail) < 1_000
    _sin_error_interno(informe)


def test_search_log_con_error_de_50000_caracteres_se_acota(corrida) -> None:
    _log_de_bases(corrida)
    enorme = "E" * 50_000
    _anadir_entrada(
        corrida,
        {"database": "Crossref", "db_key": "crossref", "status": "failed", "error": enorme},
    )
    (corrida / "01_search" / "failures.json").write_text(
        json.dumps([{"db": "Crossref", "error": enorme}]), encoding="utf-8"
    )
    informe = auditar(corrida)
    search_log = fila(informe, "search_log")
    assert search_log.status == "WARN"
    assert "`Crossref` falló (" in search_log.detail
    assert len(search_log.detail) < 400
    _sin_error_interno(informe)


def test_search_log_con_base_de_50000_caracteres_se_acota(corrida) -> None:
    _log_de_bases(corrida)
    enorme = "B" * 50_000
    _anadir_entrada(
        corrida,
        {"database": enorme, "db_key": enorme.lower(), "status": "unknown", "error": enorme},
    )
    (corrida / "01_search" / "failures.json").write_text(
        json.dumps([{"db": "C" * 50_000, "error": "x"}, {"db": "D" * 50_000, "error": "x"}]),
        encoding="utf-8",
    )
    editar_protocolo(corrida, lambda p: p.update(databases=["OpenAlex", "Z" * 50_000]))
    informe = auditar(corrida)
    search_log = fila(informe, "search_log")
    assert search_log.status == "FAIL"
    assert "status `unknown`" in search_log.detail
    assert "bases declaradas sin entrada en el log" in search_log.detail
    assert len(search_log.detail) < 2_000
    _sin_error_interno(informe)


def test_search_log_con_db_key_hostil_no_lee_fuera_de_la_instantanea(corrida) -> None:
    # Con la ruta armada desde el `db_key` del log, `../../` sacaba la lectura de la carpeta:
    # un fichero señuelo con la misma cadena habría dejado el log "coherente".
    cadena = (corrida / "00_protocol" / "search_strings" / "openalex.txt").read_text("utf-8")
    (corrida / "senuelo.txt").write_text(cadena, encoding="utf-8")
    _log_de_bases(
        corrida,
        db_key="../../senuelo",
        query_file="00_protocol/search_strings/../../senuelo.txt",
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "la cadena no está en `00_protocol/search_strings/../../senuelo.txt`" in (
        search_log.detail
    )


@pytest.mark.parametrize("clave", ["con", "nul", "aux", "a/b", "a\\b", "x\x00y", ""])
def test_search_log_con_db_key_de_dispositivo_o_ruta_no_se_abre(corrida, clave: str) -> None:
    _log_de_bases(corrida, db_key=clave, query_file=f"00_protocol/search_strings/{clave}.txt")
    informe = auditar(corrida)
    search_log = fila(informe, "search_log")
    assert search_log.status == "FAIL"
    assert "la cadena no está en" in search_log.detail
    _sin_error_interno(informe)


def test_ficheros_de_cadenas_solo_lista_ficheros_reales(corrida) -> None:
    carpeta = corrida / "00_protocol" / "search_strings"
    (carpeta / "subcarpeta.txt").mkdir()
    ctx = AuditContext(load_run(corrida))
    assert _ficheros_de_cadenas(ctx) == {"openalex.txt": "openalex.txt"}
    shutil.rmtree(carpeta)
    assert _ficheros_de_cadenas(AuditContext(load_run(corrida))) == {}


def test_ficheros_de_cadenas_indexa_por_nombre_normalizado_y_guarda_el_real(
    corrida, normcase_sin_mayusculas
) -> None:
    # Es lo que se lee: el nombre real que lista el directorio, buscado por su forma normalizada.
    _renombrar_cadena(corrida, "OpenAlex.txt")
    ctx = AuditContext(load_run(corrida))
    assert _ficheros_de_cadenas(ctx) == {"openalex.txt": "OpenAlex.txt"}


@pytest.mark.parametrize("query_file", ["openalex.txt", "OpenAlex.txt"])
def test_search_log_cadena_con_otras_mayusculas_que_el_db_key_se_encuentra(
    corrida, normcase_sin_mayusculas, query_file: str
) -> None:
    # Donde el sistema de ficheros no distingue mayúsculas el motor encuentra `OpenAlex.txt` para
    # la base `openalex` y el log dice `.../openalex.txt`: el auditor no puede dar FAIL por eso.
    _log_de_bases(corrida, query_file=f"00_protocol/search_strings/{query_file}")
    _renombrar_cadena(corrida, "OpenAlex.txt")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "PASS", search_log.detail


def test_search_log_cadena_de_otro_nombre_sigue_fallando_sin_mayusculas(
    corrida, normcase_sin_mayusculas
) -> None:
    _log_de_bases(corrida)
    _renombrar_cadena(corrida, "OtraBase.txt")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "la cadena no está en `00_protocol/search_strings/openalex.txt`" in search_log.detail


@pytest.mark.parametrize("clave", ["../../senuelo", "con", "nul", "a/b", "a\\b", "x\x00y", ""])
def test_search_log_sin_mayusculas_el_db_key_hostil_sigue_sin_abrirse(
    corrida, normcase_sin_mayusculas, clave: str
) -> None:
    # La normalización no relaja la defensa: solo se abre un nombre que lista el directorio.
    cadena = (corrida / "00_protocol" / "search_strings" / "openalex.txt").read_text("utf-8")
    (corrida / "senuelo.txt").write_text(cadena, encoding="utf-8")
    _log_de_bases(corrida, db_key=clave, query_file=f"00_protocol/search_strings/{clave}.txt")
    informe = auditar(corrida)
    search_log = fila(informe, "search_log")
    assert search_log.status == "FAIL"
    assert "la cadena no está en" in search_log.detail
    _sin_error_interno(informe)


def test_search_log_con_json_anidado_hasta_el_limite_no_cuelga_el_auditor(corrida) -> None:
    # 100 000 niveles: `json.loads` lanza `RecursionError`; el auditor no muere ni cuelga. En un
    # subproceso, por si el intérprete cayera.
    (corrida / LOG).write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=120)
    assert filas["search_log"][0] == "FAIL"
    assert "inválido" in filas["search_log"][1]
    assert filas["search_window"][0] == "WARN"
    assert "ilegible" in filas["search_window"][1]
    assert filas["timing"][0] == "PASS"
    assert [i for i, (_, d) in filas.items() if SIN_ERROR_INTERNO in d] == []
    assert len(filas) == len(CHECKS)
    assert all(len(d) < 2_000 for _, d in filas.values())


def test_log_de_10000_entradas_hostiles_se_audita_acotado_y_a_tiempo(corrida) -> None:
    def _hostil(log: dict) -> None:
        log["entries"] = [
            {
                "database": f"Base{i}-" + "b" * 200,
                "db_key": f"base{i}-" + "b" * 200,
                "kind": "database",
                "declared": True,
                "backend": "x.y",
                "status": ("failed", "ok", "unknown", "manual_only")[i % 4],
                "query": "q" * 2_000,
                "query_origin": "file",
                "query_file": f"00_protocol/search_strings/base{i}.txt",
                "query_sha256": "0" * 64,
                "max_results": 5,
                "started_utc": "2026-10-04T00:00:00+00:00" if i % 3 else "no es una fecha",
                "finished_utc": "2026-10-03T00:00:00+00:00",
                "n_returned": i % 7 - 1,
                "error": "e" * 2_000,
                "source_db": ["s" * 100],
            }
            for i in range(10_000)
        ]

    edit_json(corrida / LOG, _hostil)
    inicio = time.perf_counter()
    informe = auditar(corrida)
    transcurrido = time.perf_counter() - inicio
    assert transcurrido < 60, f"el auditor tardó {transcurrido:.1f} s"
    for check_id in ("search_log", "search_window", "timing"):
        assert len(fila(informe, check_id).detail) < 2_500, check_id
    assert fila(informe, "search_log").status == "FAIL"
    assert fila(informe, "timing").status == "FAIL"
    _sin_error_interno(informe)


# ── search_window: la fecha es la del motor, la misma que la de los exports ──


def _un_dia(fecha: str, dias: int) -> str:
    return (date.fromisoformat(fecha) + timedelta(days=dias)).isoformat()


def test_search_window_usa_la_definicion_de_los_exports(corrida) -> None:
    fecha = _fecha_del_motor(corrida)
    log = SearchLog.model_validate_json((corrida / LOG).read_text(encoding="utf-8"))
    assert engine_search_date(log) == fecha


def test_search_window_la_importacion_no_cambia_la_fecha_del_motor(corrida) -> None:
    # La importación lleva la hora de lectura del fichero, no la de la búsqueda: no cuenta para
    # la fecha del motor (la regla de `engine_search_date`).
    fecha = _fecha_del_motor(corrida)
    _anadir_entrada(
        corrida,
        {
            "database": "imported/scopus.ris",
            "db_key": "imported",
            "kind": "manual_import",
            "status": "ok",
            "started_utc": "2020-01-01T00:00:00+00:00",
            "finished_utc": "2020-01-01T00:00:01+00:00",
            "file_sha256": "a" * 64,
        },
    )
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed=fecha))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "PASS"
    assert f"el {fecha}" in window.detail


def test_search_window_sin_fecha_tecleada_pasa_con_la_del_motor(corrida) -> None:
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed=""))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "PASS"
    assert "2015-01-01 → 2026-06-26" in window.detail


def test_search_window_una_fecha_yaml_igual_a_la_del_motor_pasa(corrida) -> None:
    # `executed: 2026-10-04` sin comillas es un `datetime.date` para PyYAML.
    fecha = _fecha_del_motor(corrida)
    for ruta in ("manifest.yml", "00_protocol/protocol.yml"):
        path = corrida / ruta
        texto = path.read_text(encoding="utf-8")
        sin_comillas, cambios = re.subn(
            r"executed: ['\"]2026-06-26['\"]", f"executed: {fecha}", texto
        )
        assert cambios == 1, ruta
        path.write_text(sin_comillas, encoding="utf-8")
    window = fila(auditar(corrida), "search_window")
    assert window.status == "PASS"


@pytest.mark.parametrize("dias", [1, -1])
def test_search_window_un_dia_de_diferencia_avisa_de_utc_contra_local(corrida, dias: int) -> None:
    fecha = _un_dia(_fecha_del_motor(corrida), dias)
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed=fecha))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert f"`executed: {fecha}` tecleada distinta de la fecha del motor" in window.detail
    assert "difieren en un día: la fecha del motor es UTC" in window.detail


def test_search_window_dos_dias_de_diferencia_no_dice_que_sea_utc(corrida) -> None:
    fecha = _un_dia(_fecha_del_motor(corrida), 2)
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed=fecha))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "difieren en un día" not in window.detail


def test_search_window_una_fecha_yaml_con_hora_del_mismo_dia_pasa(corrida) -> None:
    # `executed: 2026-10-04T10:00:00` sin comillas es un `datetime.datetime` para PyYAML; se
    # compara por fecha, no por su ISO con hora.
    fecha = _fecha_del_motor(corrida)
    for ruta in ("manifest.yml", "00_protocol/protocol.yml"):
        path = corrida / ruta
        texto = path.read_text(encoding="utf-8")
        con_hora, cambios = re.subn(
            r"executed: ['\"]2026-06-26['\"]", f"executed: {fecha}T10:00:00", texto
        )
        assert cambios == 1, ruta
        path.write_text(con_hora, encoding="utf-8")
    window = fila(auditar(corrida), "search_window")
    assert window.status == "PASS", window.detail


def test_search_window_con_la_marca_en_otra_zona_da_la_fecha_utc(corrida) -> None:
    # 2026-10-03T20:00-12:00 es 2026-10-04T08:00Z: el texto da el 3 y el instante, el 4.
    edit_json(
        corrida / LOG,
        lambda log: log["entries"][0].update(started_utc="2026-10-03T20:00:00-12:00"),
    )
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed="2026-10-04"))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "PASS", window.detail
    assert "ejecutada por el motor el 2026-10-04" in window.detail


def test_search_window_toma_la_busqueda_mas_temprana_por_instante_no_por_texto(corrida) -> None:
    # "2026-10-04T01:00+14:00" (= 2026-10-03T11:00Z) es anterior al instante de la primera
    # entrada (2026-10-04T08:00Z) aunque, como texto, sea posterior.
    edit_json(
        corrida / LOG,
        lambda log: log["entries"][0].update(started_utc="2026-10-04T08:00:00+00:00"),
    )
    _anadir_entrada(
        corrida,
        {
            "database": "Crossref",
            "db_key": "crossref",
            "status": "ok",
            "backend": "search_backends.crossref_search",
            "started_utc": "2026-10-04T01:00:00+14:00",
        },
    )
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed="2026-10-03"))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "PASS", window.detail
    assert "ejecutada por el motor el 2026-10-03" in window.detail


def test_search_window_con_una_marca_fuera_de_rango_en_utc_no_falla_el_auditor(corrida) -> None:
    # 0001-01-01T00:00+14:00 no tiene instante UTC representable (OverflowError al convertirlo).
    edit_json(
        corrida / LOG,
        lambda log: log["entries"][0].update(started_utc="0001-01-01T00:00:00+14:00"),
    )
    informe = auditar(corrida)
    assert fila(informe, "search_window").status == "WARN"
    _sin_error_interno(informe)


def test_search_window_con_el_log_ilegible_no_da_pass(corrida) -> None:
    (corrida / LOG).write_text("{", encoding="utf-8")
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "no registrada por el motor (01_search/log.json ilegible, ver `schemas`)" in (
        window.detail
    )


def test_search_window_sin_log_ni_fecha_tecleada_advierte(corrida) -> None:
    (corrida / LOG).unlink()
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed=""))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "sin fecha de ejecución: ni `executed` ni 01_search/log.json" in window.detail


def test_search_window_con_log_ilegible_y_sin_fecha_tecleada_lo_dice(corrida) -> None:
    (corrida / LOG).write_text("{", encoding="utf-8")
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed=""))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "sin fecha de ejecución: ni `executed` ni fecha del motor (" in window.detail


def test_search_window_con_la_hora_del_log_ilegible_no_da_pass(corrida) -> None:
    # `engine_search_date` es textual: una hora que no es una fecha no puede dar el PASS.
    edit_json(corrida / LOG, lambda log: log["entries"][0].update(started_utc="no es una fecha"))
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed=""))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "fecha del motor ilegible (`no es una `)" in window.detail


def test_search_window_con_ventana_enorme_se_acota(corrida) -> None:
    fecha = _fecha_del_motor(corrida)
    editar_protocolo(
        corrida,
        lambda p: p["search_window"].update(executed=fecha, **{"from": "d" * 50_000, "to": 7}),
    )
    window = fila(auditar(corrida), "search_window")
    assert window.status == "PASS"
    assert len(window.detail) < 400


# ── timing: las marcas de run.json y del log entran en las mismas cotas ──


def _marca(corrida, delta: timedelta) -> str:
    inicio = json.loads((corrida / "run.json").read_text(encoding="utf-8"))["started_utc"]
    return (datetime.fromisoformat(inicio) + delta).isoformat()


def test_timing_corrida_real_con_log_y_run_json_pasa(corrida) -> None:
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS"


def test_timing_interrupcion_anterior_al_inicio_falla(corrida) -> None:
    interrupcion = {"utc": "2026-01-01T00:00:00+00:00", "stage": "busqueda", "error": "caída"}
    edit_json(corrida / "run.json", lambda info: info["interruptions"].append(interrupcion))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "run.json interruptions[0] anterior al inicio de la corrida" in timing.detail


def test_timing_interrupcion_posterior_al_manifiesto_falla(corrida) -> None:
    interrupcion = {"utc": _marca(corrida, timedelta(days=30)), "stage": None, "error": "caída"}
    edit_json(corrida / "run.json", lambda info: info["interruptions"].append(interrupcion))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "run.json interruptions[0] posterior al manifiesto" in timing.detail


def test_timing_marca_del_log_sin_zona_horaria_falla(corrida) -> None:
    edit_json(corrida / LOG, lambda log: log["entries"][0].update(started_utc="2026-10-04T10:00"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "sin zona horaria" in timing.detail


def _marcas_del_log_en(corrida, formato) -> None:
    """Reescribe todas las marcas del log (el mismo instante) con ``formato(datetime)``."""

    def _reescribir(log: dict) -> None:
        for tramo in (log, *log["entries"]):
            for campo in ("started_utc", "finished_utc"):
                if tramo.get(campo):
                    tramo[campo] = formato(datetime.fromisoformat(tramo[campo]))

    edit_json(corrida / LOG, _reescribir)


def test_timing_marcas_del_log_en_otra_zona_advierten(corrida) -> None:
    # El motor escribe siempre `+00:00`: una marca en `-12:00` (el mismo instante) es posible,
    # pero el log no lo escribió el motor y la fecha de la búsqueda puede salir corrida un día.
    _marcas_del_log_en(
        corrida, lambda marca: marca.astimezone(timezone(timedelta(hours=-12))).isoformat()
    )
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert "marca(s) de 01_search/log.json con zona distinta de UTC" in timing.detail
    assert "(el motor escribe +00:00)" in timing.detail


def test_timing_marcas_del_log_con_z_son_utc_y_no_advierten(corrida) -> None:
    _marcas_del_log_en(corrida, lambda marca: marca.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert fila(auditar(corrida), "timing").status == "PASS"


def test_timing_una_marca_imposible_manda_sobre_el_aviso_de_la_zona(corrida) -> None:
    # Con marcas en `-12:00` y una anterior al inicio de la corrida: FAIL, no WARN.
    _marcas_del_log_en(
        corrida, lambda marca: marca.astimezone(timezone(timedelta(hours=-12))).isoformat()
    )
    edit_json(corrida / LOG, lambda log: log.update(started_utc="2026-01-01T00:00:00+00:00"))
    assert fila(auditar(corrida), "timing").status == "FAIL"


def test_timing_marca_del_log_posterior_al_manifiesto_falla(corrida) -> None:
    futuro = _marca(corrida, timedelta(days=30))
    edit_json(corrida / LOG, lambda log: log["entries"][0].update(finished_utc=futuro))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "01_search/log.json entradas[0] `search_fn` finished_utc posterior al manifiesto" in (
        timing.detail
    )


def test_timing_marca_del_log_anterior_al_inicio_de_la_corrida_falla(corrida) -> None:
    edit_json(corrida / LOG, lambda log: log.update(started_utc="2026-01-01T00:00:00+00:00"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "01_search/log.json started_utc anterior al inicio de la corrida" in timing.detail


def test_timing_un_log_que_termina_unos_milisegundos_antes_no_falla(corrida) -> None:
    # La tolerancia de 2 s de la relación 14 también vale dentro del log: un reloj que se
    # corrige entre dos lecturas no es un log imposible.
    def _casi_igual(log: dict) -> None:
        entrada = log["entries"][0]
        inicio = datetime.fromisoformat(entrada["started_utc"])
        entrada["finished_utc"] = (inicio - timedelta(milliseconds=50)).isoformat()

    edit_json(corrida / LOG, _casi_igual)
    assert fila(auditar(corrida), "timing").status == "PASS"


def test_timing_con_el_log_ilegible_no_inventa_marcas(corrida) -> None:
    (corrida / LOG).write_text("{", encoding="utf-8")
    assert fila(auditar(corrida), "timing").status == "PASS"


def test_timing_con_reanudaciones_enormes_se_acota(corrida) -> None:
    basura = ["x" * 50_000] * 100
    edit_json(corrida / "run.json", lambda info: info.update(resumes=basura))
    informe = auditar(corrida)
    timing = fila(informe, "timing")
    assert timing.status == "FAIL"
    assert len(timing.detail) < 1_500
    _sin_error_interno(informe)


def test_timing_con_base_de_50000_caracteres_en_el_log_se_acota(corrida) -> None:
    def _enorme(log: dict) -> None:
        log["entries"][0].update(database="B" * 50_000, started_utc="no es una marca")

    edit_json(corrida / LOG, _enorme)
    informe = auditar(corrida)
    timing = fila(informe, "timing")
    assert timing.status == "FAIL"
    assert len(timing.detail) < 1_500
    _sin_error_interno(informe)


# ═══ Corridas reales del motor: ningún FAIL falso, y la manipulación sí se delata ═══
#
# Tres búsquedas distintas de la inyectada de `corrida`: (A) una base con backend, una base
# `manual_only` con su fichero de `imported/` y su cadena propia; (B) una base cuyo backend cae.
# Se ejecutan con `correr_hasta`, el mismo pipeline y la misma revisora que el resto de la suite;
# solo la búsqueda es distinta (`search_database` simulado, sin red).

_RIS = (
    "TY  - JOUR\nTI  - Estudio importado de Scopus sobre cribado\nPY  - 2023\n"
    "DO  - 10.9/scopus\nER  -\n"
)
_SCOPUS = 'TITLE-ABS-KEY ( "systematic review" AND screening )'


def _registros(db: str, n: int) -> list[SearchRecord]:
    return [
        SearchRecord(
            record_id=f"10.5/{db.lower()}-{i}",
            title=f"Cribado asistido por modelos de lenguaje {i}",
            abstract="Reduce la carga de trabajo del cribado.",
            year=2024,
            doi=f"10.5/{db.lower()}-{i}",
            source_db=db,
        )
        for i in range(n)
    ]


def _correr_real(
    base: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    databases: list[str],
    ris: bool,
    parar_en: str | None,
    nombre_cadena_openalex: str | None = None,
) -> Path:
    """Una corrida real (búsqueda por bases, sin ``search_fn``) hasta ``parar_en``.

    ``nombre_cadena_openalex`` renombra ``search_strings/openalex.txt`` del protocolo (p. ej. a
    ``OpenAlex.txt``) antes de correr.
    """
    from revisia.agents import search_backends

    protocolo = base / "proto"
    shutil.copytree(DEMO, protocolo)
    if nombre_cadena_openalex:
        carpeta = protocolo / "search_strings"
        (carpeta / "openalex.txt").rename(carpeta / nombre_cadena_openalex)
    crudo = yaml.safe_load((protocolo / "protocol.yml").read_text(encoding="utf-8"))
    crudo["databases"] = databases
    (protocolo / "protocol.yml").write_text(
        yaml.safe_dump(crudo, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (protocolo / "search_strings" / "scopus.txt").write_text(_SCOPUS + "\n", encoding="utf-8")
    if ris:
        (protocolo / "imported").mkdir()
        (protocolo / "imported" / "scopus.ris").write_text(_RIS, encoding="utf-8")

    def _busqueda(db, query, max_results, *, mailto=None):
        if db == "BVS":
            raise RuntimeError("503 para https://bvs.example/?q=x&api_key=SECRETO")
        return _registros("OpenAlex", 3)

    monkeypatch.setattr(search_backends, "search_database", _busqueda)
    # El preflight (M6) exige `httpx` para las bases con backend; el venv de pruebas no lo instala.
    monkeypatch.setattr(preflight_mod, "_default_find_spec", lambda _name: object())
    monkeypatch.setattr(
        pipeline_mod, "build_provider", lambda cfg: ScriptedProvider(model=cfg.model)
    )
    protocol = load_protocol(protocolo)
    marca = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    ctx = RunContext(protocol.slug, base / "runs", marca)
    resultado = correr_hasta(
        protocol,
        protocolo,
        ctx,
        search_fn=None,
        fetch_fn=fetch_disponible,
        parar_en=parar_en,
    )
    esperado = "paused" if parar_en else "completed"
    assert resultado.status == esperado, resultado.message
    return ctx.run_dir


@pytest.fixture(scope="module")
def corrida_con_bases(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """(A) OpenAlex + Scopus (``manual_only`` con su RIS), completada."""
    with pytest.MonkeyPatch.context() as mp:
        return _correr_real(
            tmp_path_factory.mktemp("bases"),
            mp,
            databases=["OpenAlex", "Scopus"],
            ris=True,
            parar_en=None,
        )


@pytest.fixture(scope="module")
def corrida_con_base_caida(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """(B) OpenAlex + BVS (el backend lanza), detenida en el cribado T/A."""
    with pytest.MonkeyPatch.context() as mp:
        return _correr_real(
            tmp_path_factory.mktemp("caida"),
            mp,
            databases=["OpenAlex", "BVS"],
            ris=False,
            parar_en="screening_ta",
        )


def _sistema_de_ficheros_sin_mayusculas() -> bool:
    """Si este sistema de ficheros no distingue mayúsculas (Windows, macOS): se comprueba."""
    with tempfile.TemporaryDirectory() as carpeta:
        (Path(carpeta) / "aB.txt").write_text("x", encoding="utf-8")
        return (Path(carpeta) / "AB.TXT").exists()


@pytest.fixture(scope="module")
def corrida_con_cadena_en_mayusculas(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """(C) OpenAlex cuya cadena el investigador guardó como ``search_strings/OpenAlex.txt``."""
    with pytest.MonkeyPatch.context() as mp:
        return _correr_real(
            tmp_path_factory.mktemp("mayusculas"),
            mp,
            databases=["OpenAlex"],
            ris=False,
            parar_en="screening_ta",
            nombre_cadena_openalex="OpenAlex.txt",
        )


def _copia(origen: Path, tmp_path: Path) -> Path:
    destino = tmp_path / "runs" / origen.name
    shutil.copytree(origen, destino)
    return destino


@pytest.fixture
def real_con_bases(corrida_con_bases: Path, tmp_path: Path) -> Path:
    return _copia(corrida_con_bases, tmp_path)


@pytest.fixture
def real_con_base_caida(corrida_con_base_caida: Path, tmp_path: Path) -> Path:
    return _copia(corrida_con_base_caida, tmp_path)


def test_real_inyectada_no_da_fail_en_busqueda_ni_en_timing(corrida) -> None:
    informe = auditar(corrida)
    assert fila(informe, "search_log").status == "WARN"
    assert fila(informe, "search_window").status == "WARN"
    assert fila(informe, "timing").status == "PASS"


def test_real_con_bases_y_manual_only_importada_pasa(real_con_bases) -> None:
    log = SearchLog.model_validate_json((real_con_bases / LOG).read_text(encoding="utf-8"))
    estados = {e.database: (e.kind, e.status, e.n_returned) for e in log.entries}
    assert estados == {
        "OpenAlex": ("database", "ok", 3),
        "Scopus": ("database", "manual_only", 0),
        "imported/scopus.ris": ("manual_import", "ok", 1),
    }
    informe = auditar(real_con_bases)
    search_log = fila(informe, "search_log")
    assert search_log.status == "PASS", search_log.detail
    assert "3 entradas en el log (2 `ok`)" in search_log.detail
    assert "4 registros" in search_log.detail
    assert fila(informe, "timing").status == "PASS"
    assert fila(informe, "search_window").status == "WARN"  # la fecha tecleada es 2026-06-26


def test_real_con_bases_la_fecha_del_motor_da_el_pass_de_la_ventana(real_con_bases) -> None:
    fecha = _fecha_del_motor(real_con_bases)
    editar_protocolo(real_con_bases, lambda p: p["search_window"].update(executed=fecha))
    window = fila(auditar(real_con_bases), "search_window")
    assert window.status == "PASS"
    assert fecha in window.detail


def test_real_con_bases_cadena_manipulada_falla(real_con_bases) -> None:
    def _otra(log: dict) -> None:
        log["entries"][0].update(query="otra cadena", query_sha256=sha256_text("otra cadena"))

    edit_json(real_con_bases / LOG, _otra)
    search_log = fila(auditar(real_con_bases), "search_log")
    assert search_log.status == "FAIL"
    assert "`OpenAlex`: cadena distinta de `00_protocol/search_strings/openalex.txt`" in (
        search_log.detail
    )


def test_real_con_bases_cadena_de_scopus_manipulada_falla(real_con_bases) -> None:
    # La cadena de una base `manual_only` también se compara con la instantánea.
    def _otra(log: dict) -> None:
        log["entries"][1].update(query="otra", query_sha256=sha256_text("otra"))

    edit_json(real_con_bases / LOG, _otra)
    search_log = fila(auditar(real_con_bases), "search_log")
    assert search_log.status == "FAIL"
    assert "`Scopus`: cadena distinta de `00_protocol/search_strings/scopus.txt`" in (
        search_log.detail
    )


def test_real_con_bases_hash_manipulado_falla(real_con_bases) -> None:
    edit_json(real_con_bases / LOG, lambda log: log["entries"][0].update(query_sha256="1" * 64))
    search_log = fila(auditar(real_con_bases), "search_log")
    assert search_log.status == "FAIL"
    assert "`OpenAlex`: `query_sha256` no es el hash de la cadena (relación 3)" in (
        search_log.detail
    )


def test_real_con_bases_instantanea_de_la_cadena_manipulada_falla(real_con_bases) -> None:
    # Editar la cadena congelada para que coincida con el log rompe además `protocol_snapshot`,
    # pero la fila `search_log` no la da por buena: el hash del log ya no es el del fichero.
    fichero = real_con_bases / "00_protocol" / "search_strings" / "openalex.txt"
    fichero.write_text("una cadena que el motor no ejecutó\n", encoding="utf-8")
    informe = auditar(real_con_bases)
    assert fila(informe, "search_log").status == "FAIL"
    assert fila(informe, "protocol_snapshot").status == "FAIL"


def test_real_con_bases_registros_borrados_fallan(real_con_bases) -> None:
    def _quitar_uno(registros: list) -> None:
        del registros[-1]

    edit_json(real_con_bases / "01_search" / "records.json", _quitar_uno)
    search_log = fila(auditar(real_con_bases), "search_log")
    assert search_log.status == "FAIL"
    assert "Σ n_returned 4 ≠ 3 registros" in search_log.detail


@pytest.mark.skipif(
    not _sistema_de_ficheros_sin_mayusculas(),
    reason="el sistema de ficheros distingue mayúsculas: el motor no encuentra `OpenAlex.txt`",
)
def test_real_con_cadena_en_mayusculas_la_busqueda_no_da_fail(
    corrida_con_cadena_en_mayusculas: Path, tmp_path: Path
) -> None:
    # Donde el sistema de ficheros no distingue mayúsculas, el motor encuentra
    # `search_strings/OpenAlex.txt` para la base `openalex` y registra `.../openalex.txt`; el
    # auditor no puede dar FAIL a una corrida legítima por la grafía del fichero.
    run = _copia(corrida_con_cadena_en_mayusculas, tmp_path)
    log = SearchLog.model_validate_json((run / LOG).read_text(encoding="utf-8"))
    entrada = log.entries[0]
    assert (entrada.query_origin, entrada.query_file) == (
        "file",
        "00_protocol/search_strings/openalex.txt",
    )
    nombres = [p.name for p in (run / "00_protocol" / "search_strings").iterdir()]
    assert "OpenAlex.txt" in nombres and "openalex.txt" not in nombres
    search_log = fila(auditar(run), "search_log")
    assert search_log.status == "PASS", search_log.detail


def test_real_con_base_caida_advierte_sin_fail_falso(real_con_base_caida) -> None:
    log = SearchLog.model_validate_json((real_con_base_caida / LOG).read_text(encoding="utf-8"))
    bvs = next(e for e in log.entries if e.database == "BVS")
    assert (bvs.status, bvs.n_returned) == ("failed", 0)
    assert "SECRETO" not in (bvs.error or "")
    informe = auditar(real_con_base_caida)
    search_log = fila(informe, "search_log")
    assert search_log.status == "WARN", search_log.detail
    assert "`BVS` falló (RuntimeError: 503" in search_log.detail
    assert "SECRETO" not in search_log.detail
    assert fila(informe, "search_window").status == "WARN"
    assert fila(informe, "timing").status != "FAIL"


def test_real_con_base_caida_ocultar_el_fallo_falla(real_con_base_caida) -> None:
    # Pasar la base a `ok` y borrar el error deja Σ n_returned y los registros en pie.
    def _ocultar(log: dict) -> None:
        bvs = next(e for e in log["entries"] if e["database"] == "BVS")
        bvs.update(status="ok", error=None)

    edit_json(real_con_base_caida / LOG, _ocultar)
    search_log = fila(auditar(real_con_base_caida), "search_log")
    assert search_log.status == "FAIL"
    assert "failures.json lista BVS sin entrada `failed` en el log" in search_log.detail


def test_real_con_base_caida_quitar_failures_json_falla(real_con_base_caida) -> None:
    (real_con_base_caida / "01_search" / "failures.json").unlink()
    search_log = fila(auditar(real_con_base_caida), "search_log")
    assert search_log.status == "FAIL"
    assert "`BVS`: `failed` y no está en 01_search/failures.json (relación 2)" in (
        search_log.detail
    )


def test_real_interrumpida_y_reanudada_deja_un_timing_sin_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Una caída real (un 429 a mitad del cribado) deja una interrupción y una reanudación en
    # `run.json`; ambas, junto con las horas del log, caen dentro de [inicio, manifiesto].
    protocol = load_protocol(DEMO)
    ctx = RunContext(protocol.slug, tmp_path / "runs", datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))

    def _busqueda(_query: str, n: int) -> list[SearchRecord]:
        return _registros("OpenAlex", 3)[:n]

    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: ScriptedProvider(fail_at=3))
    with pytest.raises(RunInterrupted):
        run_pipeline(protocol, DEMO, ctx, search_fn=_busqueda)
    monkeypatch.setattr(
        pipeline_mod, "build_provider", lambda cfg: ScriptedProvider(model=cfg.model)
    )
    resultado = correr_hasta(
        protocol,
        DEMO,
        RunContext.open(ctx.run_dir),
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
    )
    assert resultado.status == "completed", resultado.message
    info = json.loads((ctx.run_dir / "run.json").read_text(encoding="utf-8"))
    assert len(info["interruptions"]) == 1
    assert len(info["resumes"]) >= 2
    informe = auditar(ctx.run_dir)
    assert fila(informe, "timing").status == "PASS", fila(informe, "timing").detail
    assert fila(informe, "search_log").status == "WARN"


def test_manual_only_sin_cadena_avisa_aunque_haya_importaciones_de_otra_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PRISMA-S 8 pide la estrategia de cada base, también de las buscadas fuera del motor: el
    # RIS de Scopus no excusa a CINAHL, que no declara la suya (revisión final de la Ola 1, E6).
    run = _correr_real(
        tmp_path,
        monkeypatch,
        databases=["OpenAlex", "Scopus", "CINAHL"],
        ris=True,
        parar_en="screening_ta",
    )

    search_log = fila(auditar(run), "search_log")

    assert search_log.status == "WARN"
    assert "`CINAHL` es de importación manual y no declara su cadena" in search_log.detail
    assert "`Scopus` es de importación manual y no declara" not in search_log.detail
