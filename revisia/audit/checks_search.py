"""Checks de búsqueda y registro: ``search_log``, ``search_window``, ``registration``.

Desde la Ola 1 el motor registra la búsqueda en ``01_search/log.json``: una entrada por base
declarada, por fichero de ``imported/`` o por búsqueda inyectada, con la cadena efectiva, su
hash, los parámetros, las horas y cuántos registros devolvió (PRISMA-S 1/8/13/15; auditoría
2026-09-03, M12). Antes la fecha y las cadenas salían de lo que el humano tecleaba en
``protocol.yml``.

El log, ``failures.json``, ``records.json`` y el protocolo son entrada no confiable: ningún valor
leído de ellos entra en un detalle sin pasar por ``short_text`` ni sin acotar las listas que se
muestran, y la cadena de una base solo se lee de un fichero que existe de verdad en
``00_protocol/search_strings/`` (un ``db_key`` hostil con ``..`` o ``/`` no se sigue como ruta).
El fichero se busca por su nombre normalizado (``os.path.normcase``): donde el sistema de
ficheros no distingue mayúsculas (Windows, macOS) el motor encuentra ``OpenAlex.txt`` para la
base ``openalex`` y el auditor también; donde sí las distingue (Linux) la búsqueda es exacta.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

from revisia.agents import search_backends
from revisia.audit.artifacts import NA_PROTOCOLO, AuditContext, short_text, sufijo_mas
from revisia.audit.checks_timing import parse_utc
from revisia.audit.model import Verdict
from revisia.exports.checklist import engine_search_date, ran_in_engine
from revisia.orchestration.snapshot import SEARCH_STRINGS_DIR, SNAPSHOT_DIR
from revisia.provenance.runmeta import sha256_text
from revisia.schemas.artifacts import SearchLog, SearchLogEntry

LOG = "01_search/log.json"
FAILURES = "01_search/failures.json"
RECORDS = "01_search/records.json"
_CADENAS = f"{SNAPSHOT_DIR}/{SEARCH_STRINGS_DIR}"

_MAX = 5  # elementos que se listan en un detalle; el resto se cuenta
_MAX_REGISTROS = 10  # registros que se listan; el resto se cuenta
_LIMITE_REGISTRO = 40  # caracteres de una clave o de un valor de `registration`
_LIMITE_NOMBRE = 40  # caracteres de una base, una ruta o una fecha dentro de un detalle
_LIMITE_ERROR = 120  # caracteres del error de una base o de un artefacto ilegible


def _protocol_section(ctx: AuditContext, key: str) -> dict | None:
    """Sección del protocolo: de la instantánea ``00_protocol/`` si existe (D3).

    Sin instantánea (una corrida anterior a la Ola 1) sale del manifiesto. Con la
    instantánea ilegible el protocolo crudo es el del manifiesto, como en ``thresholds``.
    """
    protocol = ctx.protocol_raw
    if protocol is None:
        return None
    section = protocol.get(key)
    return section if isinstance(section, dict) else {}


def _nombre(value: object) -> str:
    """El nombre de una base (o de lo que venga del log) para un detalle: acotado."""
    return f"`{short_text(value, limit=_LIMITE_NOMBRE)}`"


def _limitar(items: list[str]) -> str:
    return "; ".join(items[:_MAX]) + sufijo_mas(len(items) - _MAX)


def _lista(items: list[str]) -> str:
    """``a, b, c (+N más)``: nombres del log, acotados en número y en longitud."""
    shown = ", ".join(short_text(item, limit=_LIMITE_NOMBRE) for item in items[:_MAX])
    return shown + sufijo_mas(len(items) - _MAX)


def _ficheros_de_cadenas(ctx: AuditContext) -> dict[str, str]:
    """Ficheros de ``00_protocol/search_strings/``, ``{nombre normalizado: nombre real}``.

    Son los únicos que se leen. El ``db_key`` de una entrada es del log y el log es entrada no
    confiable: construir con él la ruta de lectura permitiría salir de la carpeta (``../``) o
    abrir un dispositivo de Windows (``con.txt``). Una cadena solo se compara con un fichero que
    el directorio lista, y se lee con el nombre real que lista, no con el del log. La clave es
    ``os.path.normcase(nombre)``: la identidad en Linux y las minúsculas en Windows, donde
    ``OpenAlex.txt`` y ``openalex.txt`` son el mismo fichero (y el motor lo encuentra).
    """
    try:
        with os.scandir(ctx.run_dir / _CADENAS) as entradas:
            return {os.path.normcase(e.name): e.name for e in entradas if e.is_file()}
    except Exception:  # fail-closed: sin carpeta legible no hay cadena con la que comparar
        return {}


def _ruta_de_la_cadena(e: SearchLogEntry, cadenas: dict[str, str]) -> str | None:
    """Ruta relativa de ``search_strings/<db_key>.txt`` si el directorio la lista; si no, ``None``.

    Es siempre ``_CADENAS`` más un nombre que lista el directorio: nunca una ruta armada con el
    ``db_key`` ni con el ``query_file`` del log.
    """
    real = cadenas.get(os.path.normcase(f"{e.db_key}.txt"))
    return None if real is None else f"{_CADENAS}/{real}"


def _bases_declaradas(ctx: AuditContext) -> list[str] | None:
    """Bases del protocolo (de la instantánea o, sin ella, del manifiesto); ``None`` si no hay.

    Se lee el protocolo en crudo y no ``ctx.protocol``: con un protocolo que no valida (otra
    fila da el FAIL) las bases declaradas aún se pueden contrastar con el log.
    """
    protocol = ctx.protocol_raw
    if protocol is None:
        return None
    databases = protocol.get("databases")
    return [db for db in databases if isinstance(db, str)] if isinstance(databases, list) else []


def _cadena_del_fichero(
    ctx: AuditContext,
    e: SearchLogEntry,
    name: str,
    cadenas: dict[str, str],
    fails: list[str],
) -> None:
    """Relación 3: la cadena del log es la de ``00_protocol/search_strings/<db_key>.txt``."""
    esperado = f"{_CADENAS}/{e.db_key}.txt"
    ruta = _ruta_de_la_cadena(e, cadenas)
    # `query_file` se compara normalizado, como el nombre del fichero: donde no se distinguen
    # mayúsculas, `OpenAlex.txt` y `openalex.txt` son la misma ruta.
    mismo_fichero = e.query_file is not None and (
        os.path.normcase(e.query_file) == os.path.normcase(esperado)
    )
    if ruta is None or not mismo_fichero:
        fails.append(f"{name}: la cadena no está en `{short_text(esperado)}`")
        return
    text = ctx.art.text(ruta)
    if not text.ok:
        fails.append(f"{name}: no se pudo leer `{short_text(ruta)}`")
    elif text.value.strip() != e.query:
        fails.append(f"{name}: cadena distinta de `{short_text(e.query_file)}`")


def _nota_de_la_instantanea(ctx: AuditContext, e: SearchLogEntry, cadenas: dict[str, str]) -> str:
    """Aviso extra del fallback si la instantánea sí tiene una cadena no vacía para la base.

    El motor usa la pregunta solo cuando ``search_strings/<db_key>.txt`` falta o está vacío; que
    la instantánea la tenga con texto es una manipulación del log o un fallo del motor. Sigue
    siendo un WARN (el spec lo manda así), pero «sin cadena propia» sería falso.
    """
    ruta = _ruta_de_la_cadena(e, cadenas)
    if ruta is None:
        return ""
    text = ctx.art.text(ruta)
    if text.ok and text.value.strip():
        return " (la instantánea sí tiene una cadena no vacía para esta base)"
    return ""


def _revisar_entrada(
    ctx: AuditContext,
    e: SearchLogEntry,
    *,
    failed_dbs: set[str],
    importados: int,
    cadenas: dict[str, str],
    fails: list[str],
    warns: list[str],
) -> None:
    """Las relaciones 1-3 y la honestidad de una entrada del log, base a base."""
    name = _nombre(e.database)
    if e.n_returned < 0:
        fails.append(f"{name}: `n_returned` negativo ({short_text(e.n_returned)})")
    if e.kind == "database" and e.db_key != search_backends.db_key(e.database):
        fails.append(f"{name}: `db_key` no corresponde a la base")

    if e.status == "unknown":
        motivo = f" ({short_text(e.error, limit=_LIMITE_ERROR)})" if e.error else ""
        fails.append(f"{name}: status `unknown`{motivo}")
    elif e.status == "failed":
        error = short_text(e.error, limit=_LIMITE_ERROR) if e.error else "sin error"
        warns.append(f"{name} falló ({error})")
        if not e.error or e.n_returned != 0 or e.source_db:
            fails.append(f"{name}: `failed` sin error o con registros (relación 2)")
        if e.database not in failed_dbs:
            fails.append(f"{name}: `failed` y no está en {FAILURES} (relación 2)")
    elif e.status == "manual_only" and not importados:
        warns.append(f"{name} es de importación manual y no hay registros importados")

    if e.query_origin == "question_fallback":
        warns.append(
            f"{name}: sin cadena propia, se usó la pregunta (PRISMA-S 8)"
            f"{_nota_de_la_instantanea(ctx, e, cadenas)}"
        )
    if e.status == "ok" and e.max_results is not None and e.n_returned == e.max_results:
        warns.append(f"{name}: {short_text(e.n_returned)} resultados = max_results (¿truncados?)")

    # Una búsqueda que el motor dio por buena lleva su cadena y de dónde salió; quitárselas
    # esquivaría el aviso del fallback y la comparación con la instantánea (relación 3).
    sin_origen = e.kind == "database" and e.query_origin is None
    if e.status == "ok" and e.kind in ("database", "injected") and (e.query is None or sin_origen):
        fails.append(f"{name}: sin cadena o sin su origen registrados (PRISMA-S 8)")
    if e.query is not None and e.query_sha256 != sha256_text(e.query):
        fails.append(f"{name}: `query_sha256` no es el hash de la cadena (relación 3)")
    if (e.query_origin == "file") != (e.query_file is not None):
        fails.append(f"{name}: `query_origin` y `query_file` no concuerdan (relación 3)")
    if e.query_origin == "file" and e.query_file is not None:
        _cadena_del_fichero(ctx, e, name, cadenas, fails)
    if e.kind == "manual_import" and e.status == "ok" and not e.file_sha256:
        fails.append(f"{name}: importación sin huella del fichero (`file_sha256`)")


def check_search_log(ctx: AuditContext) -> Verdict:
    """PRISMA-S 1/8/13/15: la búsqueda quedó registrada por el motor, base a base.

    Relaciones 1-3 de §4.4: Σ ``n_returned`` de las entradas ``ok`` es el número de registros
    de ``01_search/records.json`` y sus ``source_db`` son los del log; toda entrada ``failed``
    lleva error, no devuelve registros y figura en ``failures.json`` (y al revés: un fallo de
    ``failures.json`` sin entrada ``failed`` es un log que lo oculta); y la cadena de cada
    base es la de ``00_protocol/search_strings/`` con su hash.
    """
    loaded = ctx.art.artifact(LOG)
    if not loaded.present:
        return "FAIL", (
            f"{LOG} ausente: la búsqueda no la registró el motor (cadenas, fechas y n por base; "
            "PRISMA-S 8/13)."
        )
    if not loaded.ok:
        return "FAIL", f"{LOG} inválido ({short_text(loaded.error, limit=_LIMITE_ERROR)})."
    entries = loaded.value.entries
    fails: list[str] = []
    warns: list[str] = []

    if not entries:
        fails.append("el log no tiene ninguna entrada")
    inyectada = any(e.kind == "injected" for e in entries)
    if inyectada:
        warns.append("búsqueda inyectada (`search_fn`): no corresponde a las bases declaradas")
    # Una búsqueda inyectada sustituye a las bases (nunca convive con entradas de base): las
    # declaradas no se buscaron y no hay entrada que echar en falta.
    if not (inyectada and not any(e.kind == "database" for e in entries)):
        declaradas = _bases_declaradas(ctx)
        if declaradas is None:
            warns.append("bases declaradas no verificables: sin protocolo legible")
        else:
            registradas = {e.db_key for e in entries if e.kind == "database"}
            sin_entrada = [
                db
                for db in dict.fromkeys(declaradas)
                if search_backends.db_key(db) not in registradas
            ]
            if sin_entrada:
                fails.append(f"bases declaradas sin entrada en el log: {_lista(sin_entrada)}")

    failures = ctx.art.artifact(FAILURES)
    if failures.present and not failures.ok:
        fails.append(f"{FAILURES} ilegible (ver `schemas`): no se pueden contrastar los fallos")
    failed_dbs = {f.db for f in failures.value} if failures.ok else set()
    huerfanas = sorted(failed_dbs - {e.database for e in entries if e.status == "failed"})
    if huerfanas:
        fails.append(f"{FAILURES} lista {_lista(huerfanas)} sin entrada `failed` en el log")

    importados = sum(
        e.n_returned for e in entries if e.kind == "manual_import" and e.status == "ok"
    )
    cadenas = _ficheros_de_cadenas(ctx)
    for e in entries:
        _revisar_entrada(
            ctx,
            e,
            failed_dbs=failed_dbs,
            importados=importados,
            cadenas=cadenas,
            fails=fails,
            warns=warns,
        )

    records = ctx.art.artifact(RECORDS)
    if not records.ok:
        fails.append(f"{RECORDS} ausente o inválido")
    else:
        devueltos = sum(e.n_returned for e in entries if e.status == "ok")
        if devueltos != len(records.value):
            fails.append(
                f"Σ n_returned {short_text(devueltos)} ≠ {len(records.value)} registros en "
                f"{RECORDS} (relación 1)"
            )
        en_registros = {r.source_db for r in records.value}
        en_log = {s for e in entries for s in e.source_db}
        if en_registros != en_log:
            fails.append(
                f"source_db del log [{_lista(sorted(en_log))}] ≠ los de records.json "
                f"[{_lista(sorted(en_registros))}]"
            )

    if fails:
        return "FAIL", f"{_limitar(fails)}."
    if warns:
        return "WARN", f"{_limitar(warns)}."
    ok = sum(1 for e in entries if e.status == "ok")
    n_entradas, n_registros = len(entries), len(records.value)
    return "PASS", (
        f"{n_entradas} {'entrada' if n_entradas == 1 else 'entradas'} en el log ({ok} `ok`), "
        "cada base con su cadena registrada; "
        f"{n_registros} {'registro' if n_registros == 1 else 'registros'}."
    )


def _como_fecha(value: object) -> date | None:
    """``value`` como fecha: una fecha YAML, o una cadena ``AAAA-MM-DD``; ``None`` si no lo es."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _fecha_utc(log: SearchLog) -> str | None:
    """Fecha UTC (``AAAA-MM-DD``) de la más temprana de las búsquedas del motor, por instante.

    Las mismas marcas que usa ``engine_search_date`` (las búsquedas que ejecutó el motor, o, si
    ninguna tiene hora, el inicio del log), pero leídas como instantes: ``engine_search_date``
    corta el texto en 10 caracteres y una marca con otra zona (``2026-10-03T20:00-12:00``) daría
    el día local y no el UTC. ``None`` si alguna marca no se puede leer o no tiene instante UTC
    representable: entonces vale la fecha textual de los exports.
    """
    marcas = [e.started_utc for e in log.entries if ran_in_engine(e) and e.started_utc]
    instantes: list[datetime] = []
    for marca in marcas or [log.started_utc]:
        instante, _ = parse_utc(marca)
        if instante is None:
            return None
        instantes.append(instante)
    try:
        return min(instantes).astimezone(UTC).date().isoformat()
    except (OverflowError, ValueError):  # p. ej. 0001-01-01T00:00+14:00 no existe en UTC
        return None


def _fecha_del_motor(ctx: AuditContext) -> tuple[str | None, str | None]:
    """``(fecha, None)`` o ``(None, motivo)``: la fecha en que el motor ejecutó la búsqueda.

    Es la definición de los exports (``revisia.exports.checklist.engine_search_date``: la más
    temprana de las búsquedas que ejecutó el motor, sin contar las importaciones), para que el
    entregable y el auditor no den dos fechas distintas. Es UTC (``AAAA-MM-DD``). Con las marcas
    que escribe el motor (siempre ``+00:00``) las dos definiciones coinciden; con una marca en
    otra zona el auditor da el día UTC del instante (``_fecha_utc``) y ``timing`` avisa.
    """
    log = ctx.art.artifact(LOG)
    if not log.present:
        return None, f"sin {LOG}"
    if not log.ok:
        return None, f"{LOG} ilegible, ver `schemas`"
    fecha = engine_search_date(log.value)
    if _como_fecha(fecha) is None:
        return None, f"fecha del motor ilegible (`{short_text(fecha, limit=_LIMITE_NOMBRE)}`)"
    return _fecha_utc(log.value) or fecha, None


def _dias_entre(tecleada: object, motor: str) -> int | None:
    """Días (en valor absoluto) entre la fecha tecleada y la del motor, si ambas se leen."""
    a, b = _como_fecha(tecleada), _como_fecha(motor)
    return None if a is None or b is None else abs((a - b).days)


def check_search_window(ctx: AuditContext) -> Verdict:
    """PRISMA-S 9/13: ventana de la búsqueda declarada y fecha de ejecución registrada.

    Sin ``01_search/log.json`` la fecha la tecleó un humano en el protocolo y nadie más la
    registró: el auditor anterior daba PASS por eso (auditoría 2026-09-03, C3/M12), así que
    es WARN. Desde la Ola 1 la registra el motor y el PASS es suyo: la fecha tecleada solo
    advierte si difiere. El motor registra UTC y quien revisa teclea su fecha local, así que
    una diferencia de un día se dice como tal.
    """
    window = _protocol_section(ctx, "search_window")
    if window is None:
        return "N/A", NA_PROTOCOLO
    warns: list[str] = []
    missing = [k for k in ("from", "to") if not window.get(k)]
    if missing:
        warns.append(f"ventana sin `{'` ni `'.join(missing)}` (PRISMA-S 9)")
    executed = window.get("executed")
    engine, motivo = _fecha_del_motor(ctx)
    if engine is None:
        if executed:
            # Valor no confiable del manifiesto: acotado, no interpolado crudo (una bomba de
            # alias, `*a` ×9 por nivel, cuelga el `str` del f-string; tercera revisión de la
            # Tarea 4).
            warns.append(
                f"fecha tecleada (`executed: {short_text(executed)}`), no registrada por el "
                f"motor ({motivo})"
            )
        elif motivo == f"sin {LOG}":
            warns.append(f"sin fecha de ejecución: ni `executed` ni {LOG}")
        else:
            warns.append(f"sin fecha de ejecución: ni `executed` ni fecha del motor ({motivo})")
    elif executed:
        # Una fecha YAML (`date` o `datetime`) se compara por su día, no por su ISO con hora.
        dia = _como_fecha(executed)
        tecleada = executed if isinstance(executed, str) or dia is None else dia.isoformat()
        if tecleada != engine:
            nota = ""
            if _dias_entre(executed, engine) == 1:
                nota = (
                    "; difieren en un día: la fecha del motor es UTC y la tecleada puede ser "
                    "local, si es el mismo día decláralo"
                )
            warns.append(
                f"`executed: {short_text(executed)}` tecleada distinta de la fecha del motor "
                f"({engine}, {LOG}): corrígela o declara por qué{nota}"
            )
    if warns:
        return "WARN", "; ".join(warns) + "."
    return "PASS", (
        f"búsqueda ejecutada por el motor el {engine} ({LOG}); ventana "
        f"{short_text(window.get('from'))} → {short_text(window.get('to'))}."
    )


def check_registration(ctx: AuditContext) -> Verdict:
    """PRISMA 24a: registro del protocolo."""
    registration = _protocol_section(ctx, "registration")
    if registration is None:
        return "N/A", NA_PROTOCOLO
    declared = [(k, v) for k, v in registration.items() if v]
    if declared:
        # Igual que arriba: la clave y el valor vienen del manifiesto, siempre acotados, y las
        # entradas también: 2 000 claves daban un detalle de ~50 KB.
        registro = ", ".join(
            f"{short_text(k, limit=_LIMITE_REGISTRO)}={short_text(v, limit=_LIMITE_REGISTRO)}"
            for k, v in declared[:_MAX_REGISTROS]
        )
        return "PASS", (
            f"Registro declarado: {registro}{sufijo_mas(len(declared) - _MAX_REGISTROS)}."
        )
    return "WARN", "Sin registro (PROSPERO/OSF): preregistra el protocolo antes de publicar."
