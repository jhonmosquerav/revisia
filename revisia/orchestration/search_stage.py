"""Búsqueda multi-base con registro por base, congelada en ``01_search/`` (Ola 1).

Hasta la Ola 1 los registros crudos no se guardaban, ``01_search/`` solo existía
si alguna base fallaba, la pregunta sustituía en silencio a una cadena ausente
y una base sin backend (o mal escrita) se saltaba sin avisar; la cadena, la
fecha, los parámetros y el número de resultados por base no quedaban en ningún
sitio (auditoría 2026-09-03, M12; PRISMA-S 1, 8, 13 y 15).

Ahora cada fuente deja una entrada ``SearchLogEntry`` en ``01_search/log.json``
(una por base declarada, una por fichero de ``imported/`` y una ``injected`` si
la búsqueda la dio ``search_fn``) y los registros, **antes** del dedup (que muta
el registro conservado), van a ``01_search/records.json``. ``log.json`` es la
marca de búsqueda completa: si existe, al reanudar se cargan los registros y no
se vuelve a buscar (D3).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from revisia.agents import _http, search_backends
from revisia.ingest.manual_import import IMPORT_SUFFIXES, import_file
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import (
    SEARCH_STRINGS_DIR,
    SNAPSHOT_DIR,
    ProtocolMismatchError,
)
from revisia.provenance.runmeta import sha256_text, utc_now_iso
from revisia.schemas.artifacts import QueryOrigin, SearchLog, SearchLogEntry
from revisia.schemas.records import SearchRecord

SearchFn = Callable[[str, int], list[SearchRecord]]

SEARCH_DIR = "01_search"


def _error(exc: BaseException) -> str:
    """Mensaje del fallo, redactado: httpx incluye la URL con api_key/email."""
    return _http.redact_secrets(f"{type(exc).__name__}: {exc}")


def _query_for(strings_dir: Path, key: str, question: str) -> tuple[str, QueryOrigin, str | None]:
    """Cadena efectiva de una base: su ``search_strings/<key>.txt`` o la pregunta."""
    path = strings_dir / f"{key}.txt"
    text = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    if text:
        return text, "file", f"{SNAPSHOT_DIR}/{SEARCH_STRINGS_DIR}/{key}.txt"
    return question, "question_fallback", None


def _backend_name(key: str) -> str:
    fn = search_backends.BACKENDS[key]
    return f"{fn.__module__.rsplit('.', 1)[-1]}.{fn.__name__}"


def _search_database(
    db: str,
    *,
    declared: bool,
    strings_dir: Path,
    question: str,
    max_results: int,
    mailto: str | None,
) -> tuple[list[SearchRecord], SearchLogEntry]:
    """Busca en una base declarada y devuelve sus registros y su entrada del log."""
    key = search_backends.db_key(db)
    entry = SearchLogEntry(database=db, db_key=key, kind="database", declared=declared, status="ok")
    if key in search_backends.BACKENDS:
        query, origin, query_file = _query_for(strings_dir, key, question)
        entry.backend = _backend_name(key)
        entry.query, entry.query_origin, entry.query_file = query, origin, query_file
        entry.query_sha256 = sha256_text(query)
        entry.max_results = max_results
        entry.started_utc = utc_now_iso()
        try:
            records = search_backends.search_database(db, query, max_results, mailto=mailto)
        except Exception as exc:  # red, 5xx, JSON o validación: degradar, nunca abortar
            entry.status, entry.error = "failed", _error(exc)
            records = []
        entry.finished_utc = utc_now_iso()
        entry.n_returned = len(records)
        entry.source_db = sorted({r.source_db for r in records})
        return records, entry
    if key in search_backends.MANUAL_ONLY:
        # Se incorpora por importación (imported/); si hay cadena, se registra
        # igualmente: PRISMA-S 8 pide la estrategia de cada base.
        entry.status = "manual_only"
        query, origin, query_file = _query_for(strings_dir, key, question)
        if origin == "file":
            entry.query, entry.query_origin, entry.query_file = query, origin, query_file
            entry.query_sha256 = sha256_text(query)
        return [], entry
    entry.status = "unknown"
    entry.error = "base desconocida: sin backend ni importación manual (revisa el nombre)"
    return [], entry


def _import(path: Path) -> tuple[list[SearchRecord], SearchLogEntry]:
    """Importa un fichero de ``imported/``; un fallo queda en el log, no aborta (M7)."""
    entry = SearchLogEntry(
        database=f"imported/{path.name}",
        db_key="imported",
        kind="manual_import",
        declared=True,
        status="ok",
        started_utc=utc_now_iso(),
        file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    try:
        records = import_file(path)
    except Exception as exc:  # p. ej. un RIS exportado en UTF-16
        entry.status, entry.error = "failed", _error(exc)
        records = []
    entry.finished_utc = utc_now_iso()
    entry.n_returned = len(records)
    entry.source_db = sorted({r.source_db for r in records})
    return records, entry


def multi_database_search(
    protocol,
    *,
    strings_dir: Path,
    imported_dir: Path | None,
    question: str,
    max_results: int,
    mailto: str | None,
) -> tuple[list[SearchRecord], list[SearchLogEntry]]:
    """Busca en cada base declarada (con su cadena) e importa ``imported/``.

    Sin bases declaradas se busca en OpenAlex (``declared: false``). Una base
    que falla, un fichero que no se puede leer o una base desconocida quedan en
    su entrada del log: la corrida nunca se aborta por una fuente.
    """
    declared = list(protocol.databases)
    records: list[SearchRecord] = []
    entries: list[SearchLogEntry] = []
    for db in declared or ["openalex"]:
        found, entry = _search_database(
            db,
            declared=bool(declared),
            strings_dir=strings_dir,
            question=question,
            max_results=max_results,
            mailto=mailto,
        )
        records += found
        entries.append(entry)
    if imported_dir is not None and imported_dir.is_dir():
        for path in sorted(imported_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in IMPORT_SUFFIXES:
                found, entry = _import(path)
                records += found
                entries.append(entry)
    return records, entries


def run_search(
    protocol,
    *,
    source_dir: Path | None,
    strings_dir: Path,
    question: str,
    max_results: int,
    mailto: str | None,
    search_fn: SearchFn | None,
    run_ctx: RunContext,
) -> list[SearchRecord]:
    """Registros de la búsqueda de la corrida: de ``01_search/`` o buscándolos.

    Si ``01_search/log.json`` existe, carga ``records.json`` sin llamar a nada
    (tampoco a ``search_fn``). Si no, busca y escribe, en este orden,
    ``records.json``, ``log.json`` (marca de completitud) y ``failures.json``
    (derivado del log, solo si alguna entrada falló).

    Raises:
        ProtocolMismatchError: si hay que buscar y no se tiene la carpeta del
            protocolo original (``imported/`` no entra en la instantánea).
    """
    search_dir = run_ctx.run_dir / SEARCH_DIR
    if (search_dir / "log.json").exists():
        raw = json.loads((search_dir / "records.json").read_text(encoding="utf-8"))
        return [SearchRecord.model_validate(r) for r in raw]

    started = utc_now_iso()
    if search_fn is not None:
        records = search_fn(question, max_results)
        entries = [
            SearchLogEntry(
                database="search_fn",
                db_key="search_fn",
                kind="injected",
                declared=False,
                backend=getattr(search_fn, "__name__", None),
                status="ok",
                source_db=sorted({r.source_db for r in records}),
                query=question,
                query_sha256=sha256_text(question),
                max_results=max_results,
                started_utc=started,
                finished_utc=utc_now_iso(),
                n_returned=len(records),
            )
        ]
    else:
        if source_dir is None:
            raise ProtocolMismatchError(
                "la búsqueda de esta corrida no terminó (falta 01_search/log.json) y hay que "
                "repetirla: reanuda pasando también la carpeta del protocolo "
                "(`revisia run <protocolo> --resume <run_dir>`), que contiene imported/."
            )
        records, entries = multi_database_search(
            protocol,
            strings_dir=strings_dir,
            imported_dir=Path(source_dir) / "imported",
            question=question,
            max_results=max_results,
            mailto=mailto,
        )

    run_ctx.write_json(f"{SEARCH_DIR}/records.json", [r.model_dump(mode="json") for r in records])
    log = SearchLog(
        started_utc=started,
        finished_utc=utc_now_iso(),
        max_results=max_results,
        mailto_set=bool(mailto),
        entries=entries,
    )
    run_ctx.write_json(f"{SEARCH_DIR}/log.json", log.model_dump(mode="json"))
    failures = [{"db": e.database, "error": e.error or ""} for e in entries if e.status == "failed"]
    if failures:
        run_ctx.write_json(f"{SEARCH_DIR}/failures.json", failures)
        for failure in failures:
            print(
                f"⚠️  búsqueda · {failure['db']} no respondió ({failure['error']}); "
                "se continúa sin esa fuente"
            )
    return records
