"""Errores deterministas: código 2 con qué corregir, nunca un rc 3 «reanuda» en bucle.

Revisión final de la Ola 1, grupo A. Un error de configuración o un artefacto dañado no es
una caída que se resuelva reanudando: si sale como ``RunInterrupted`` (rc 3), cada
reanudación falla igual y la corrida queda en un bucle sin salida. Aquí se fija que cada uno
sale como rc 2 con un mensaje accionable (o que la entrada hostil se sanea sin tumbar nada).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import types
import warnings
from datetime import date
from pathlib import Path

import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import leer_solicitud, responder_gate

from revisia import cli
from revisia.agents import fulltext, ncbi
from revisia.agents.fulltext import FullText
from revisia.config import load_protocol
from revisia.llm import preflight as preflight_mod
from revisia.llm.base import LLMRequest
from revisia.llm.preflight import PreflightReport
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.hitl import DecisionFileError, _read_decision
from revisia.orchestration.journal import JournalError
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunCancelled, RunContext
from revisia.orchestration.snapshot import (
    SNAPSHOT_DIR,
    protocol_fingerprint,
    read_run_info,
    write_run_info,
)
from revisia.protocol_files import ProtocolFilesError, load_protocol_files
from revisia.provenance.ledger import DecisionEntry, DecisionLedger
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"
SUSTITUTO = chr(0xD800)
REEMPLAZO = chr(0xFFFD)


@pytest.fixture(autouse=True)
def entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin .env real y con httpx/pypdf "instalados" para el preflight del demo (M6)."""
    monkeypatch.setattr(cli, "_load_dotenv", lambda: None)
    monkeypatch.setattr(preflight_mod, "_default_find_spec", lambda _name: object())


def _busqueda(_query: str, n: int) -> list[SearchRecord]:
    # Sin DOI, PMCID ni oa_url: la recuperación no toca la red.
    return [
        SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex"),
        SearchRecord(record_id="rec-2", title="Active learning", source_db="OpenAlex"),
    ][:n]


def _protocolo(tmp_path: Path) -> Path:
    destino = tmp_path / "proto"
    shutil.copytree(EXAMPLE, destino)
    return destino


def _corrida_en_pausa(tmp_path: Path, proto: Path = EXAMPLE, **kwargs) -> Path:
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    resultado = run_pipeline(protocol, proto, ctx, search_fn=_busqueda, **kwargs)
    assert resultado.status == "paused", resultado.message
    return ctx.run_dir


# ── A1 · decision.yml que no es UTF-8 ────────────────────────────────────────


def test_decision_en_cp1252_es_error_de_decision_con_consejo(tmp_path: Path) -> None:
    # El Bloc de notas en «ANSI» guarda `revisión` como 0xF3: era un UnicodeDecodeError (rc 3).
    path = tmp_path / "decision.yml"
    path.write_bytes("approved: true\nreason: revisión\n".encode("cp1252"))

    with pytest.raises(DecisionFileError, match="UTF-8"):
        _read_decision(path)


def test_resume_con_decision_en_cp1252_sale_2_y_conserva_la_pausa(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)
    sha = leer_solicitud(run_dir, "screening_ta")["request_sha256"]
    texto = f"request_sha256: {sha}\napproved: true\nactor: human:ana\nreason: revisión\n"
    (run_dir / "screening_ta" / "decision.yml").write_bytes(texto.encode("cp1252"))

    rc = cli.main(["run", "--resume", str(run_dir)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "UTF-8" in err and "Traceback" not in err
    info = read_run_info(run_dir)
    assert (info.status, info.stage, info.interruptions) == ("paused", "screening_ta", [])


# ── A2 · ledger con la disciplina del diario ─────────────────────────────────


def _entrada(n: int) -> DecisionEntry:
    return DecisionEntry(stage="screening_ta", actor="human:ana", autonomy="A1", action=f"a{n}")


def test_ledger_append_escribe_lf_y_hace_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas: list[int] = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (llamadas.append(fd), real(fd))[1])
    ledger = DecisionLedger(tmp_path / "decisions_ledger.jsonl")

    ledger.append(_entrada(1))
    ledger.append(_entrada(2))

    datos = ledger.path.read_bytes()
    assert b"\r\n" not in datos and datos.count(b"\n") == 2
    assert len(llamadas) == 2


def test_ledger_recorta_la_ultima_linea_truncada_y_avisa(tmp_path: Path) -> None:
    ledger = DecisionLedger(tmp_path / "decisions_ledger.jsonl")
    ledger.append(_entrada(1))
    ledger.append(_entrada(2))
    with ledger.path.open("ab") as fh:
        fh.write(b'{"stage": "screening_ta", "actor": "hum')  # caída a mitad de escritura

    with pytest.warns(RuntimeWarning, match="se recortó"):
        entradas = ledger.read_all()

    assert [e.action for e in entradas] == ["a1", "a2"]
    assert ledger.path.read_bytes().endswith(b"}\n")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert len(ledger.read_all()) == 2  # ya recortada: sin aviso


def test_ledger_con_una_linea_corrupta_en_medio_es_journal_error(tmp_path: Path) -> None:
    ledger = DecisionLedger(tmp_path / "decisions_ledger.jsonl")
    ledger.append(_entrada(1))
    with ledger.path.open("ab") as fh:
        fh.write(b"{esto no es json}\n")
    ledger.append(_entrada(2))

    with pytest.raises(JournalError, match="línea 2"):
        ledger.read_all()


def test_ledger_con_una_ultima_linea_completa_pero_invalida_es_journal_error(
    tmp_path: Path,
) -> None:
    # Una caída a mitad de escritura deja una línea SIN su salto final (o JSON cortado). Una línea
    # terminada con `\n` que es JSON pero no valida como decisión no es esa huella: se editó a
    # mano (o el modelo cambió) y recortarla borraría evidencia en silencio.
    ledger = DecisionLedger(tmp_path / "decisions_ledger.jsonl")
    ledger.append(_entrada(1))
    original = ledger.path.read_bytes()
    ledger.path.write_bytes(original + b'{"stage": "screening_ta", "actor": "human:ana"}\n')
    escrito = ledger.path.read_bytes()

    with pytest.raises(JournalError, match="línea 2.*completa"):
        ledger.read_all()

    assert ledger.path.read_bytes() == escrito  # no se tocó el fichero


def test_ledger_con_una_ultima_linea_sin_salto_que_no_valida_se_recorta(tmp_path: Path) -> None:
    # Misma línea, pero sin el `\n` final: sí es la huella de una escritura a medias.
    ledger = DecisionLedger(tmp_path / "decisions_ledger.jsonl")
    ledger.append(_entrada(1))
    original = ledger.path.read_bytes()
    ledger.path.write_bytes(original + b'{"stage": "screening_ta", "actor": "human:ana"}')

    with pytest.warns(RuntimeWarning, match="se recortó"):
        entradas = ledger.read_all()

    assert [e.action for e in entradas] == ["a1"]
    assert ledger.path.read_bytes() == original


def test_resume_con_ultima_linea_completa_pero_invalida_sale_2_sin_tocar_el_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)
    responder_gate(run_dir, "screening_ta")
    assert cli.main(["run", "--resume", str(run_dir)]) == 0  # pausa en screening_ft
    ledger = run_dir / "decisions_ledger.jsonl"
    alterado = ledger.read_bytes() + b'{"stage": "screening_ft", "actor": "human:ana"}\n'
    ledger.write_bytes(alterado)
    capsys.readouterr()

    rc = cli.main(["run", "--resume", str(run_dir)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "decisions_ledger.jsonl" in err and "Traceback" not in err
    assert ledger.read_bytes() == alterado


def test_resume_con_ledger_truncado_sigue_y_con_ledger_corrupto_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)
    responder_gate(run_dir, "screening_ta")
    assert cli.main(["run", "--resume", str(run_dir)]) == 0  # pausa en screening_ft
    ledger = run_dir / "decisions_ledger.jsonl"
    original = ledger.read_bytes()
    capsys.readouterr()

    ledger.write_bytes(original + b'{"stage": "screening_ft", "act')
    with pytest.warns(RuntimeWarning, match="se recortó"):
        assert cli.main(["run", "--resume", str(run_dir)]) == 0
    assert ledger.read_bytes() == original

    ledger.write_bytes(b"{roto\n" + original)  # dañada en medio, no la última
    rc = cli.main(["run", "--resume", str(run_dir)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "decisions_ledger.jsonl" in err and "Traceback" not in err


# ── A3 · ficheros auxiliares del protocolo validados al cargar ───────────────

_EFECTOS_UN_ESTUDIO = "measure: precomputed\neffects:\n  - {study_id: a, yi: 0.1, vi: 0.02}\n"
_EFECTOS_SIN_VI = (
    "measure: precomputed\neffects:\n  - {study_id: a, yi: 0.1}\n  - {study_id: b, yi: 0.2}\n"
)
_EFECTOS_VARIANZA_CERO = (
    "measure: precomputed\neffects:\n"
    "  - {study_id: a, yi: 0.1, vi: 0}\n  - {study_id: b, yi: 0.2, vi: 0.03}\n"
)

CASOS_INVALIDOS = {
    "gold-lista": ("gold.yml", "gold:\n  - rec-1\n  - rec-2\n", "no un mapa"),
    "gold-yaml-roto": ("gold.yml", "gold: [sin: cerrar\n", "YAML no válido"),
    "gold-false-entre-comillas": ("gold.yml", 'gold:\n  rec-1: "false"\n', "true/false"),
    "effects-un-estudio": ("effects.yml", _EFECTOS_UN_ESTUDIO, "k ≥ 2"),
    "effects-sin-vi": ("effects.yml", _EFECTOS_SIN_VI, "faltan yi/vi"),
    "effects-varianza-cero": ("effects.yml", _EFECTOS_VARIANZA_CERO, "varianza no positiva"),
    "criterios-lista": ("inclusion_exclusion.yml", "- poblacion\n- outcome\n", "no un mapa"),
    "criterios-texto": ("inclusion_exclusion.yml", "criteria: adultos\n", "no un mapa"),
    "formulario-lista": ("extraction_form.yml", "- key: diseno\n", "no un mapa"),
    # Claves de fusión (`<<`): el auditor no las admite al releer `00_protocol/`; el motor las
    # rechaza igual que en `protocol.yml`, en los cuatro ficheros auxiliares.
    "gold-fusion": (
        "gold.yml",
        "base: &b {rec-1: true}\ngold:\n  <<: *b\n  rec-2: false\n",
        "claves de fusión YAML (<<) no admitidas en gold.yml",
    ),
    "effects-fusion": (
        "effects.yml",
        "measure: precomputed\nbase: &b {study_id: a, yi: 0.1, vi: 0.02}\neffects:\n"
        "  - <<: *b\n  - {study_id: b, yi: 0.2, vi: 0.03}\n",
        "claves de fusión YAML (<<) no admitidas en effects.yml",
    ),
    "criterios-fusion": (
        "inclusion_exclusion.yml",
        "base: &b {poblacion: adultos}\ncriteria:\n  <<: *b\n  outcome: mortalidad\n",
        "claves de fusión YAML (<<) no admitidas en inclusion_exclusion.yml",
    ),
    "formulario-fusion": (
        "extraction_form.yml",
        "base: &b {key: diseno}\nfields:\n  - <<: *b\n    descripcion: Diseño del estudio\n",
        "claves de fusión YAML (<<) no admitidas en extraction_form.yml",
    ),
}


@pytest.mark.parametrize("caso", list(CASOS_INVALIDOS))
@pytest.mark.parametrize("orden", ["validate", "run"])
def test_fichero_auxiliar_invalido_sale_2_antes_de_crear_la_corrida(
    tmp_path: Path, capsys: pytest.CaptureFixture, caso: str, orden: str
) -> None:
    fichero, contenido, fragmento = CASOS_INVALIDOS[caso]
    proto = _protocolo(tmp_path)
    (proto / fichero).write_text(contenido, encoding="utf-8")
    runs = tmp_path / "runs"

    argv = [orden, str(proto)] + (["--runs-root", str(runs)] if orden == "run" else [])
    rc = cli.main(argv)

    salida = capsys.readouterr()
    assert rc == 2
    assert fichero in salida.err and fragmento in salida.err
    assert "Traceback" not in salida.err
    assert not runs.exists()  # D10: el preflight corre antes de crear la carpeta


def _dañar_instantanea(run_dir: Path, fichero: str, contenido: str) -> None:
    """Escribe ``contenido`` en ``00_protocol/<fichero>`` y ajusta su huella en run.json.

    Simula una corrida que empezó con un motor que aún no validaba ese fichero: la
    instantánea es coherente con run.json y solo la validación nueva la rechaza.
    """
    (run_dir / SNAPSHOT_DIR / fichero).write_text(contenido, encoding="utf-8")
    info = read_run_info(run_dir)
    huellas = {**info.protocol_sha256, **protocol_fingerprint(run_dir / SNAPSHOT_DIR)}
    write_run_info(run_dir, info.model_copy(update={"protocol_sha256": huellas}))


@pytest.mark.parametrize("caso", list(CASOS_INVALIDOS))
def test_fichero_auxiliar_invalido_al_reanudar_sale_2_y_conserva_la_pausa(
    tmp_path: Path, capsys: pytest.CaptureFixture, caso: str
) -> None:
    fichero, contenido, fragmento = CASOS_INVALIDOS[caso]
    run_dir = _corrida_en_pausa(tmp_path)
    _dañar_instantanea(run_dir, fichero, contenido)

    rc = cli.main(["run", "--resume", str(run_dir)])

    err = capsys.readouterr().err
    assert rc == 2
    assert fichero in err and fragmento in err and "Traceback" not in err
    info = read_run_info(run_dir)
    assert (info.status, info.stage, info.interruptions) == ("paused", "screening_ta", [])


@pytest.mark.parametrize("caso", ["gold-lista", "effects-fusion"])
def test_tras_la_instantanea_un_fichero_invalido_es_error_de_configuracion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caso: str
) -> None:
    # Segunda línea de defensa: aunque el preflight no lo viera, el pipeline valida
    # `00_protocol/` justo después de la instantánea y lo trata como error de configuración.
    fichero, contenido, fragmento = CASOS_INVALIDOS[caso]
    run_dir = _corrida_en_pausa(tmp_path)
    _dañar_instantanea(run_dir, fichero, contenido)
    monkeypatch.setattr(pipeline_mod, "preflight", lambda *_a, **_k: PreflightReport(()))
    ctx = RunContext.open(run_dir)
    protocol = load_protocol(run_dir / SNAPSHOT_DIR, default_slug=ctx.slug)

    with pytest.raises(ProtocolFilesError, match=fichero) as exc:
        run_pipeline(protocol, None, ctx)

    assert fragmento in str(exc.value)

    info = read_run_info(run_dir)
    assert (info.status, info.stage, info.interruptions) == ("paused", "screening_ta", [])


def test_gold_con_claves_mixtas_se_normaliza_a_texto(tmp_path: Path) -> None:
    # Un id numérico junto a uno de texto: `sorted` lanzaba TypeError al escribir gold.json.
    proto = _protocolo(tmp_path)
    (proto / "gold.yml").write_text("gold:\n  123: true\n  rec-1: false\n", encoding="utf-8")

    run_dir = _corrida_en_pausa(tmp_path, proto)

    gold = json.loads((run_dir / "03_screening" / "gold.json").read_text(encoding="utf-8"))
    assert gold == {"123": True, "rec-1": False}


def test_formulario_con_fecha_sin_comillas_llega_a_la_extraccion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `ejemplo: 2021-03-15` es un `date` de YAML: `canonical_sha256` del diario de extracción
    # lanzaba TypeError después de los gates de cribado.
    proto = _protocolo(tmp_path)
    formulario = yaml.safe_load((proto / "extraction_form.yml").read_text(encoding="utf-8"))
    formulario["fields"][0]["ejemplo"] = "__FECHA__"
    texto = yaml.safe_dump(formulario, allow_unicode=True).replace("__FECHA__", "2021-03-15")
    assert yaml.safe_load(texto)["fields"][0]["ejemplo"] == date(2021, 3, 15)
    (proto / "extraction_form.yml").write_text(texto, encoding="utf-8")
    assert load_protocol_files(proto).form_fields[0]["ejemplo"] == "2021-03-15"
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: ScriptedProvider())
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    resultado = run_pipeline(
        protocol,
        proto,
        ctx,
        auto_approve=True,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
    )

    assert resultado.status == "completed", resultado.message
    assert (ctx.run_dir / "05_extraction" / "journal.jsonl").exists()


# ── A4 · sustitutos sueltos de una API ───────────────────────────────────────


def _con_sustituto(texto: str) -> str:
    """``texto`` con un sustituto suelto, como lo deja ``httpx.Response.json()``."""
    return json.loads(json.dumps(texto + SUSTITUTO))


def test_search_record_cambia_los_sustitutos_sueltos_por_u_fffd() -> None:
    record = SearchRecord(
        record_id=_con_sustituto("r"),
        title=_con_sustituto("título"),
        authors=[_con_sustituto("Ana")],
        extra={_con_sustituto("clave"): [_con_sustituto("valor")], "n": 3},
    )

    assert record.title == "título" + REEMPLAZO
    assert record.authors == ["Ana" + REEMPLAZO]
    assert record.extra == {"clave" + REEMPLAZO: ["valor" + REEMPLAZO], "n": 3}
    json.dumps(record.model_dump(), ensure_ascii=False).encode("utf-8")  # ya no revienta


def test_busqueda_y_texto_completo_con_sustitutos_no_tumban_la_corrida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def busqueda(_query: str, _n: int) -> list[SearchRecord]:
        datos = json.loads(json.dumps({"record_id": "rec-1", "title": "T" + SUSTITUTO}))
        return [SearchRecord.model_validate({**datos, "source_db": "OpenAlex"})]

    def fetch(_record: SearchRecord) -> FullText:
        return FullText(text=_con_sustituto("Texto completo"), available=True)

    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: ScriptedProvider())
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    resultado = run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=busqueda, fetch_fn=fetch
    )

    assert resultado.status == "completed", resultado.message
    registros = json.loads((ctx.run_dir / "01_search" / "records.json").read_text("utf-8"))
    assert registros[0]["title"] == "T" + REEMPLAZO
    (texto,) = (ctx.run_dir / "04_fulltext" / "texts").iterdir()
    assert texto.read_bytes().decode("utf-8") == "Texto completo" + REEMPLAZO
    assert not list(ctx.run_dir.rglob("*.tmp"))


# ── A5 · motivos de «no recuperado» transitorios, no congelados ──────────────


class _Resp:
    def __init__(
        self,
        status: int = 200,
        data: object = None,
        *,
        content: bytes = b"",
        content_type: str = "",
    ) -> None:
        self.status_code = status
        self._data = data
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = RuntimeError(f"HTTP {self.status_code}")
            error.response = self  # como httpx.HTTPStatusError
            raise error

    def json(self) -> object:
        if self._data is None:
            raise ValueError("sin JSON")
        return self._data


class _Cliente:
    def __init__(self, respuesta: _Resp | Exception) -> None:
        self._respuesta = respuesta

    def __enter__(self) -> _Cliente:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def get(self, _url: str, params: dict | None = None) -> _Resp:
        if isinstance(self._respuesta, Exception):
            raise self._respuesta
        return self._respuesta


@pytest.fixture
def _ncbi_sin_esperas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ncbi, "_sleep", lambda _s: None)


def test_sin_httpx_con_mailto_y_solo_doi_es_sin_httpx(
    monkeypatch: pytest.MonkeyPatch, _ncbi_sin_esperas: None
) -> None:
    # Antes: el ID Converter y Unpaywall caían a «sin OA» y `sin_url_oa` (permanente) se
    # congelaba en el diario.
    monkeypatch.setitem(sys.modules, "httpx", None)
    record = SearchRecord(record_id="r", title="t", doi="10.1/abc", abstract="resumen")

    ft = fulltext.fetch_fulltext(record, mailto="ana@example.org")

    assert (ft.available, ft.reason) == (False, "sin_httpx")


@pytest.mark.parametrize(
    "respuesta",
    [ConnectionError("conexión rechazada"), _Resp(503), _Resp(429)],
    ids=["red", "503", "429"],
)
def test_fallo_de_red_del_id_converter_o_bioc_es_error_http(
    monkeypatch: pytest.MonkeyPatch, _ncbi_sin_esperas: None, respuesta: object
) -> None:
    monkeypatch.setattr(ncbi, "_client", lambda timeout=60.0: _Cliente(respuesta))
    # El DOI sin `oa_url` pasa también por Unpaywall (vía 2): ahí no hay nada (404), así que el
    # fallo de NCBI sigue mandando y es `error_http` (antes ni se llegaba a mirar Unpaywall).
    monkeypatch.setitem(sys.modules, "httpx", _httpx_unpaywall(_Resp(404)))
    por_doi = SearchRecord(record_id="r", title="t", doi="10.1/abc")
    por_pmcid = SearchRecord(record_id="p", title="t", extra={"pmcid": "PMC1"})

    assert fulltext.fetch_fulltext(por_doi, mailto="ana@example.org").reason == "error_http"
    assert fulltext.fetch_fulltext(por_pmcid).reason == "error_http"


_PAGINA_OA = _Resp(
    200, content=b"<html><body>Texto abierto</body></html>", content_type="text/html"
)


def test_oa_url_con_id_converter_caido_recupera_el_texto(
    monkeypatch: pytest.MonkeyPatch, _ncbi_sin_esperas: None
) -> None:
    # Antes de la ronda A5 un 503 del ID Converter no cortaba la vía de `extra.oa_url`; con A5
    # escapaba antes del paso 2 y el registro salía `error_http` aunque la URL abierta existía.
    monkeypatch.setattr(ncbi, "_client", lambda timeout=60.0: _Cliente(_Resp(503)))
    monkeypatch.setitem(sys.modules, "httpx", _httpx_unpaywall(_PAGINA_OA))
    record = SearchRecord(
        record_id="r", title="t", doi="10.1/abc", extra={"oa_url": "https://repo.org/p.html"}
    )

    ft = fulltext.fetch_fulltext(record, mailto="ana@example.org")

    assert (ft.available, ft.reason) == (True, None)
    assert ft.text == "Texto abierto" and ft.source_url == "https://repo.org/p.html"


def test_oa_url_con_bioc_caido_recupera_el_texto(
    monkeypatch: pytest.MonkeyPatch, _ncbi_sin_esperas: None
) -> None:
    monkeypatch.setattr(ncbi, "_client", lambda timeout=60.0: _Cliente(_Resp(500)))
    monkeypatch.setitem(sys.modules, "httpx", _httpx_unpaywall(_PAGINA_OA))
    record = SearchRecord(
        record_id="r", title="t", extra={"pmcid": "PMC1", "oa_url": "https://repo.org/p.html"}
    )

    ft = fulltext.fetch_fulltext(record)

    assert (ft.available, ft.reason) == (True, None)
    assert ft.text == "Texto abierto"


def test_solo_doi_con_id_converter_503_y_unpaywall_404_es_error_http(
    monkeypatch: pytest.MonkeyPatch, _ncbi_sin_esperas: None
) -> None:
    monkeypatch.setattr(ncbi, "_client", lambda timeout=60.0: _Cliente(_Resp(503)))
    monkeypatch.setitem(sys.modules, "httpx", _httpx_unpaywall(_Resp(404)))
    record = SearchRecord(record_id="r", title="t", doi="10.1/abc", abstract="resumen")

    ft = fulltext.fetch_fulltext(record, mailto="ana@example.org")

    assert (ft.available, ft.reason) == (False, "error_http")
    assert "ID Converter" in (ft.detail or "")  # el fallo de NCBI, no un «sin_url_oa» mudo


def test_fallo_de_ncbi_gana_a_un_paso_2_sin_texto(
    monkeypatch: pytest.MonkeyPatch, _ncbi_sin_esperas: None
) -> None:
    # La vía 2 llega a una página sin texto (`texto_vacio`) o sin `httpx` (`sin_httpx`), pero
    # BioC pudo tenerlo: el fallo transitorio previo manda y se reintenta al reanudar.
    monkeypatch.setattr(ncbi, "_client", lambda timeout=60.0: _Cliente(_Resp(500)))
    vacia = _Resp(200, content=b"<html><body> </body></html>", content_type="text/html")
    monkeypatch.setitem(sys.modules, "httpx", _httpx_unpaywall(vacia))
    record = SearchRecord(
        record_id="r", title="t", extra={"pmcid": "PMC1", "oa_url": "https://repo.org/p.html"}
    )

    ft = fulltext.fetch_fulltext(record)

    assert (ft.available, ft.reason) == (False, "error_http")
    assert "BioC-PMC" in (ft.detail or "")

    monkeypatch.setitem(sys.modules, "httpx", None)
    sin_httpx = fulltext.fetch_fulltext(record)

    assert (sin_httpx.available, sin_httpx.reason) == (False, "error_http")


def test_404_de_bioc_es_sin_acceso_abierto(
    monkeypatch: pytest.MonkeyPatch, _ncbi_sin_esperas: None
) -> None:
    monkeypatch.setattr(ncbi, "_client", lambda timeout=60.0: _Cliente(_Resp(404)))
    record = SearchRecord(record_id="p", title="t", extra={"pmcid": "PMC1"})

    assert fulltext.fetch_fulltext(record).reason == "sin_url_oa"


def _httpx_unpaywall(respuesta: _Resp | Exception) -> types.ModuleType:
    modulo = types.ModuleType("httpx")
    modulo.Client = lambda **_k: _Cliente(respuesta)  # type: ignore[attr-defined]
    return modulo


@pytest.mark.parametrize(
    ("respuesta", "esperado"),
    [
        (_Resp(404), "sin_url_oa"),
        (_Resp(200, {"best_oa_location": None}), "sin_url_oa"),
        (_Resp(503), "error_http"),
        (TimeoutError("lectura agotada"), "error_http"),
    ],
    ids=["404", "200-sin-url", "503", "timeout"],
)
def test_unpaywall_distingue_sin_oa_de_un_fallo(
    monkeypatch: pytest.MonkeyPatch, respuesta: object, esperado: str
) -> None:
    monkeypatch.setitem(sys.modules, "httpx", _httpx_unpaywall(respuesta))
    monkeypatch.setattr(fulltext, "_resolve_pmcid", lambda _r, *, mailto=None: None)
    record = SearchRecord(record_id="r", title="t", doi="10.1/abc")

    assert fulltext.fetch_fulltext(record, mailto="ana@example.org").reason == esperado


def test_preflight_avisa_si_falta_pypdf() -> None:
    protocol = load_protocol(EXAMPLE)
    sin_pypdf = preflight_mod.preflight(
        protocol, EXAMPLE, context="run", find_spec=lambda n: None if n == "pypdf" else object()
    )
    con_pypdf = preflight_mod.preflight(
        protocol, EXAMPLE, context="run", find_spec=lambda _n: object()
    )

    avisos = " ".join(i.message for i in sin_pypdf.warnings)
    assert "pypdf" in avisos and "no recuperados" in avisos
    assert "pypdf" not in " ".join(i.message for i in con_pypdf.warnings)
    assert not sin_pypdf.errors


# ── A6 · artefactos congelados editados a mano ───────────────────────────────


@pytest.mark.parametrize(
    "artefacto",
    ["01_search/records.json", "02_dedup/records.json", "02_dedup/dedup.json"],
)
@pytest.mark.parametrize("contenido", ["{no es json", '[{"title": 5}]'], ids=["json", "modelo"])
def test_artefacto_congelado_danado_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture, artefacto: str, contenido: str
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)
    (run_dir / artefacto).write_text(contenido, encoding="utf-8")

    rc = cli.main(["run", "--resume", str(run_dir)])

    err = capsys.readouterr().err
    assert rc == 2
    assert Path(artefacto).name in err and "Traceback" not in err
    assert read_run_info(run_dir).interruptions == []


# ── A7 · validate/run sin protocol.yml o con uno que no es UTF-8 ─────────────


@pytest.mark.parametrize("orden", ["validate", "run"])
def test_carpeta_sin_protocol_yml_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture, orden: str
) -> None:
    vacia = tmp_path / "vacia"
    vacia.mkdir()

    rc = cli.main([orden, str(vacia)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "protocol.yml" in err and "Traceback" not in err


@pytest.mark.parametrize("orden", ["validate", "run"])
def test_protocol_yml_que_no_es_utf8_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture, orden: str
) -> None:
    proto = _protocolo(tmp_path)
    texto = (proto / "protocol.yml").read_text(encoding="utf-8") + "\n# revisión\n"
    (proto / "protocol.yml").write_bytes(texto.encode("cp1252", errors="replace"))

    rc = cli.main([orden, str(proto)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "UTF-8" in err and "Traceback" not in err


# ── A8 · el gold efectivo sobrevive a la reanudación ─────────────────────────


def test_gold_labels_de_la_primera_invocacion_sobreviven_al_reanudar(tmp_path: Path) -> None:
    run_dir = _corrida_en_pausa(tmp_path, gold_labels={"rec-1": True, "rec-2": False})
    primera = leer_solicitud(run_dir, "screening_ta")
    assert primera["quality"] is not None  # con gold, la solicitud informa la calidad

    ctx = RunContext.open(run_dir)
    protocol = load_protocol(run_dir / SNAPSHOT_DIR, default_slug=ctx.slug)
    resultado = run_pipeline(protocol, None, ctx)  # sin `gold_labels`

    assert resultado.status == "paused"
    assert leer_solicitud(run_dir, "screening_ta") == primera


# ── A9 · Ctrl+C con la carpeta real y sin afirmar lo que no pasó ─────────────


class _ProveedorCtrlC(ScriptedProvider):
    def _llamar(self, req: LLMRequest) -> None:
        super()._llamar(req)
        raise KeyboardInterrupt


def test_ctrl_c_en_el_pipeline_lleva_la_carpeta_y_si_quedo_registrado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: _ProveedorCtrlC())
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    with pytest.raises(RunCancelled) as exc:
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)

    assert (exc.value.run_dir, exc.value.registered) == (ctx.run_dir, True)
    assert read_run_info(ctx.run_dir).status == "interrupted"


def test_ctrl_c_sin_poder_escribir_run_json_no_dice_que_quedo_registrado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: _ProveedorCtrlC())

    def _bloqueado(*_a, **_k):
        raise PermissionError("run.json bloqueado")

    monkeypatch.setattr(pipeline_mod, "write_run_info", _bloqueado)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    with pytest.raises(RunCancelled) as exc:
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)

    assert exc.value.registered is False


@pytest.mark.parametrize(
    ("registrado", "esperado", "prohibido"),
    [
        (True, "queda registrado en", "<carpeta de la corrida>"),
        (False, "sin registrarlo en run.json", "queda registrado"),
    ],
)
def test_cli_ctrl_c_imprime_la_ruta_real(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    registrado: bool,
    esperado: str,
    prohibido: str,
) -> None:
    run_dir = tmp_path / "runs" / "demo-mini-review-T"

    def _cancelada(*_a, **_k):
        raise RunCancelled(run_dir, registered=registrado)

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _cancelada)
    assert cli.main(["run", str(EXAMPLE)]) == 130

    err = capsys.readouterr().err
    assert esperado in err and prohibido not in err
    assert f"revisia run --resume {run_dir}" in err


def test_cli_ctrl_c_al_reanudar_fuera_del_pipeline_usa_la_carpeta_de_resume(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)

    def _ctrl_c(*_a, **_k):
        raise KeyboardInterrupt

    monkeypatch.setattr("revisia.orchestration.flow.resume_review", _ctrl_c)
    assert cli.main(["run", "--resume", str(run_dir)]) == 130

    err = capsys.readouterr().err
    assert f"revisia run --resume {run_dir}" in err
    assert "queda registrado" not in err
