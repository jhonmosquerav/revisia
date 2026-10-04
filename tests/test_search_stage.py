"""Búsqueda con registro por base y congelada en 01_search/ (auditoría 2026-09-03,
M12 y M7; spec 2026-10-04 §7)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from revisia.agents import search_backends
from revisia.config import load_protocol
from revisia.orchestration.journal import JournalError
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.search_stage import run_search
from revisia.provenance.runmeta import sha256_text
from revisia.schemas.artifacts import SearchLog
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"

_RIS = "TY  - JOUR\nTI  - Estudio importado de Scopus\nDO  - 10.9/scopus\nER  -\n"


def _protocolo(tmp_path: Path, databases: list[str]) -> Path:
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["databases"] = databases
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    (proto / "search_strings" / "openalex.txt").write_text("cadena openalex\n", encoding="utf-8")
    return proto


def _log(ctx: RunContext) -> SearchLog:
    return SearchLog.model_validate_json(
        (ctx.run_dir / "01_search" / "log.json").read_text(encoding="utf-8")
    )


def test_search_log_por_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proto = _protocolo(tmp_path, ["OpenAlex", "Europe PMC", "BVS", "Scopus"])
    (proto / "imported").mkdir()
    (proto / "imported" / "scopus.ris").write_text(_RIS, encoding="utf-8")

    def fake_search_database(db, query, max_results, *, mailto=None):
        if db == "BVS":
            raise RuntimeError("503 para https://bvs.example/?q=x&api_key=SECRETO")
        n = 2 if db == "OpenAlex" else 1
        fuente = "OpenAlex" if db == "OpenAlex" else "EuropePMC"
        return [
            SearchRecord(record_id=f"{db}:{i}", title=f"{db} {i}", source_db=fuente)
            for i in range(n)
        ]

    monkeypatch.setattr(search_backends, "search_database", fake_search_database)
    ctx = RunContext("demo", tmp_path / "runs", "T")
    records = run_search(
        load_protocol(proto),
        source_dir=proto,
        strings_dir=proto / "search_strings",
        question="pregunta del protocolo",
        max_results=7,
        mailto=None,
        search_fn=None,
        run_ctx=ctx,
    )

    log = _log(ctx)
    por_base = {e.database: e for e in log.entries}
    assert list(por_base) == ["OpenAlex", "Europe PMC", "BVS", "Scopus", "imported/scopus.ris"]
    openalex = por_base["OpenAlex"]
    assert (openalex.kind, openalex.status, openalex.n_returned) == ("database", "ok", 2)
    assert (openalex.query, openalex.query_origin) == ("cadena openalex", "file")
    assert openalex.query_file == "00_protocol/search_strings/openalex.txt"
    assert openalex.query_sha256 == sha256_text("cadena openalex")
    assert (openalex.backend, openalex.max_results) == ("busqueda.search", 7)
    assert openalex.started_utc and openalex.finished_utc
    europe = por_base["Europe PMC"]
    assert (europe.query, europe.query_origin, europe.query_file) == (
        "pregunta del protocolo",
        "question_fallback",
        None,
    )
    assert europe.source_db == ["EuropePMC"]
    bvs = por_base["BVS"]
    assert (bvs.status, bvs.n_returned) == ("failed", 0)
    assert "api_key=<redacted>" in bvs.error and "SECRETO" not in bvs.error
    assert por_base["Scopus"].status == "manual_only"
    importado = por_base["imported/scopus.ris"]
    assert (importado.kind, importado.status, importado.n_returned) == ("manual_import", "ok", 1)
    ris_bytes = (proto / "imported" / "scopus.ris").read_bytes()
    assert importado.file_sha256 == hashlib.sha256(ris_bytes).hexdigest()

    # records.json = lo devuelto; Σ n_returned de las entradas ok (relación 1).
    guardados = json.loads((ctx.run_dir / "01_search" / "records.json").read_text("utf-8"))
    assert [r["record_id"] for r in guardados] == [r.record_id for r in records]
    assert len(records) == sum(e.n_returned for e in log.entries if e.status == "ok") == 4
    fallos = json.loads((ctx.run_dir / "01_search" / "failures.json").read_text("utf-8"))
    assert fallos == [{"db": "BVS", "error": bvs.error}]


def test_import_ris_utf16_no_aborta(tmp_path: Path) -> None:
    proto = _protocolo(tmp_path, ["Scopus"])
    imported = proto / "imported"
    imported.mkdir()
    (imported / "a.ris").write_bytes(_RIS.encode("utf-16"))  # export típico de EndNote
    (imported / "b.bib").write_text("@article{k, title = {Desde BibTeX}}\n", encoding="utf-8")
    ctx = RunContext("demo", tmp_path / "runs", "T")

    records = run_search(
        load_protocol(proto),
        source_dir=proto,
        strings_dir=proto / "search_strings",
        question="q",
        max_results=5,
        mailto=None,
        search_fn=None,
        run_ctx=ctx,
    )

    assert [r.title for r in records] == ["Desde BibTeX"]
    por_base = {e.database: e for e in _log(ctx).entries}
    assert por_base["imported/a.ris"].status == "failed"
    assert por_base["imported/a.ris"].error.startswith("UnicodeDecodeError")
    assert por_base["imported/a.ris"].file_sha256
    assert por_base["imported/b.bib"].status == "ok"


def test_search_no_se_repite_al_reanudar(tmp_path: Path) -> None:
    llamadas: list[str] = []

    def busqueda_unica(query: str, n: int) -> list[SearchRecord]:
        if llamadas:
            raise AssertionError("la búsqueda no debe repetirse al reanudar")
        llamadas.append(query)
        return [SearchRecord(record_id="rec-1", title="Uno", source_db="OpenAlex")]

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=busqueda_unica).status == "paused"
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=busqueda_unica).status == "paused"
    assert len(llamadas) == 1
    (entrada,) = _log(ctx).entries
    assert (entrada.kind, entrada.database, entrada.n_returned) == ("injected", "search_fn", 1)


# ── Mensajes de fallo, importaciones ilegibles y failures.json al reanudar (revisión de B14) ──


def _buscar(proto: Path, ctx: RunContext) -> list[SearchRecord]:
    return run_search(
        load_protocol(proto),
        source_dir=proto,
        strings_dir=proto / "search_strings",
        question="q",
        max_results=5,
        mailto=None,
        search_fn=None,
        run_ctx=ctx,
    )


def _bvs_falla(monkeypatch: pytest.MonkeyPatch, llamadas: list[str] | None = None) -> None:
    def fake_search_database(db, query, max_results, *, mailto=None):
        if llamadas is not None:
            llamadas.append(db)
        if db == "BVS":
            raise RuntimeError("503 Service Unavailable")
        return [SearchRecord(record_id=f"{db}:0", title=f"{db} 0", source_db=db)]

    monkeypatch.setattr(search_backends, "search_database", fake_search_database)


def test_mensaje_de_fallo_distingue_base_de_importacion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Una importación ilegible decía «<fichero> no respondió»: no es una base que responda.
    proto = _protocolo(tmp_path, ["OpenAlex", "BVS", "Scopus"])
    (proto / "imported").mkdir()
    (proto / "imported" / "a.ris").write_bytes(_RIS.encode("utf-16"))
    _bvs_falla(monkeypatch)

    _buscar(proto, RunContext("demo", tmp_path / "runs", "T"))

    salida = capsys.readouterr().out
    assert (
        "⚠️  búsqueda · BVS falló (RuntimeError: 503 Service Unavailable); queda fuera de esta "
        "corrida (búsqueda congelada): para incluirla, empieza una corrida nueva"
    ) in salida
    assert "⚠️  búsqueda · no se pudo importar imported/a.ris (UnicodeDecodeError: " in salida
    assert "queda fuera de esta corrida (búsqueda congelada)" in salida.split("importar")[1]
    assert "no respondió" not in salida
    assert "se continúa sin esa fuente" not in salida


def test_importacion_con_permiso_denegado_queda_en_el_log_y_no_tumba_la_busqueda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `file_sha256` se calculaba fuera del `try`: un PermissionError al leer el fichero
    # (p. ej. abierto por Excel en Windows) tumbaba la búsqueda entera.
    proto = _protocolo(tmp_path, ["Scopus"])
    (proto / "imported").mkdir()
    (proto / "imported" / "a.ris").write_text(_RIS, encoding="utf-8")
    (proto / "imported" / "b.bib").write_text("@article{k, title = {Desde BibTeX}}\n", "utf-8")
    leer = Path.read_bytes

    def read_bytes(self: Path) -> bytes:
        if self.name == "a.ris":
            raise PermissionError(13, "Permission denied", str(self))
        return leer(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    ctx = RunContext("demo", tmp_path / "runs", "T")

    records = _buscar(proto, ctx)

    assert [r.title for r in records] == ["Desde BibTeX"]
    por_base = {e.database: e for e in _log(ctx).entries}
    assert por_base["imported/a.ris"].status == "failed"
    assert por_base["imported/a.ris"].error.startswith("PermissionError")
    assert por_base["imported/a.ris"].file_sha256 is None
    assert por_base["imported/b.bib"].status == "ok"


def test_failures_json_se_rederiva_del_log_al_reanudar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # `log.json` se escribe antes que `failures.json`: una caída entre medias dejaba la
    # búsqueda «completa» y los fallos sin registrar para siempre.
    proto = _protocolo(tmp_path, ["OpenAlex", "BVS"])
    llamadas: list[str] = []
    _bvs_falla(monkeypatch, llamadas)
    ctx = RunContext("demo", tmp_path / "runs", "T")
    _buscar(proto, ctx)
    ruta = ctx.run_dir / "01_search" / "failures.json"
    esperado = json.loads(ruta.read_text("utf-8"))
    assert esperado == [{"db": "BVS", "error": "RuntimeError: 503 Service Unavailable"}]
    ruta.unlink()
    capsys.readouterr()

    _buscar(proto, ctx)

    assert json.loads(ruta.read_text("utf-8")) == esperado  # misma forma
    assert llamadas == ["OpenAlex", "BVS"]  # y sin repetir la búsqueda
    assert "BVS falló" in capsys.readouterr().out


def test_sin_fallos_la_reanudacion_no_crea_failures_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proto = _protocolo(tmp_path, ["OpenAlex"])
    _bvs_falla(monkeypatch)
    ctx = RunContext("demo", tmp_path / "runs", "T")
    _buscar(proto, ctx)

    _buscar(proto, ctx)

    assert not (ctx.run_dir / "01_search" / "failures.json").exists()


def test_log_de_busqueda_ilegible_al_reanudar_es_error_del_diario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proto = _protocolo(tmp_path, ["OpenAlex", "BVS"])
    _bvs_falla(monkeypatch)
    ctx = RunContext("demo", tmp_path / "runs", "T")
    _buscar(proto, ctx)
    (ctx.run_dir / "01_search" / "failures.json").unlink()
    (ctx.run_dir / "01_search" / "log.json").write_text('{"entries": 3}', encoding="utf-8")

    with pytest.raises(JournalError, match=r"log\.json.*empieza una nueva"):
        _buscar(proto, ctx)
