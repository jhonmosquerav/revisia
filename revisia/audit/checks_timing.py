"""Checks de plausibilidad temporal: ``timing``, ``response_overlap``.

La reconstrucción de la auditoría 2026-09-03 (C3) tenía 140 llamadas en
1,3 ms, un ledger fechado una semana antes de la corrida y a horas redondas,
y los 46 hashes de respuesta de Sonnet dentro de los 94 de Opus. Ninguna de
esas huellas es una firma, pero juntas encarecen mucho fabricar una corrida.

Reglas (spec 2026-10-04 §9.3):

- **FAIL** si una marca no tiene zona horaria o no se puede leer; si cae fuera
  de [inicio de la corrida, ``manifest.created_utc``] con 2 s de tolerancia;
  si el ledger retrocede más de 2 s; si una llamada declara
  ``deterministic: true`` con un proveedor que no es ``fake`` (ningún
  proveedor real lo garantiza: todos ponen ``False``).
- **WARN** (heurísticas, nunca FAIL): ≥ 20 llamadas no exentas con una
  mediana de separación < 5 ms; ≥ 4 marcas del ledger con ≥ 50 % sin
  fracción de segundo; límite inferior o superior no verificable (sin ``run.json`` válido ni
  ``manifest.timestamp`` con forma de corrida; sin ``manifest.created_utc`` o con el
  manifiesto ilegible). Un límite que no se puede comprobar nunca da PASS en silencio
  (revisión de la Tarea 6): borrar ``created_utc`` de un manifiesto editado a mano no
  relaja el límite superior.
- Solo ``provider == "fake" and deterministic`` está exento de las
  heurísticas (las corridas de demostración son instantáneas).

El manifiesto, el ledger y las llamadas son entrada no confiable (revisiones de
la Tarea 4): ningún check lanza ni cuelga con un valor hostil, y ningún valor
leído de ellos entra en un detalle sin pasar por ``short_text``/``short_repr``
(cadenas enormes, bombas de alias) ni sin acotar las listas que se muestran.
Las marcas se comparan **restando**, no sumando la tolerancia: ``marca + 2 s``
desborda (``OverflowError``) con una fecha del año 9999.
"""

from __future__ import annotations

import re
import statistics
from datetime import UTC, datetime, timedelta
from itertools import combinations

from revisia.audit.artifacts import (
    LLM_CALLS_ILEGIBLE,
    NA_MANIFIESTO,
    AuditContext,
    short_repr,
    short_text,
)
from revisia.audit.model import Verdict

TOLERANCIA = timedelta(seconds=2)
MIN_LLAMADAS_HEURISTICA = 20
MEDIANA_MINIMA = timedelta(milliseconds=5)
MIN_MARCAS_LEDGER = 4
MIN_LLAMADAS_SOLAPE = 10
UMBRAL_SOLAPE = 0.5
_TIMESTAMP_CORRIDA = re.compile(r"[0-9]{8}-[0-9]{6}")  # `fullmatch`; solo dígitos ASCII
_MAX = 5
_MAX_SOLAPES = 3
# Modelos que `response_overlap` compara entre sí: las parejas crecen al cuadrado y una lista
# hostil con 10⁵ modelos colgaría el auditor. El motor usa un puñado; el resto se avisa.
_MAX_MODELOS_SOLAPE = 20
_LIMITE_VALOR = 50  # caracteres de un valor del manifiesto dentro de un detalle


def _mostrar(value: object) -> str:
    """Un valor no confiable para un detalle: acotado en coste y en longitud."""
    return "ausente" if value is None else short_text(value, limit=_LIMITE_VALOR)


def parse_utc(value: object) -> tuple[datetime | None, str | None]:
    """``(marca, None)`` o ``(None, motivo)``; una marca sin zona no vale.

    Acepta cualquier objeto y nunca lanza: un manifiesto editado a mano puede traer un
    entero, una lista, una bomba de alias o una cadena de megabytes donde se espera una
    marca. El motivo va acotado (``short_text``/``short_repr``).
    """
    if not isinstance(value, str):
        return None, f"no es una cadena ({short_repr(value, limit=_LIMITE_VALOR)})"
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:  # fail-closed: ni `ValueError` ni otra excepción de la lectura escapan
        return None, f"no es ISO-8601 (`{short_text(value, limit=_LIMITE_VALOR)}`)"
    if parsed.utcoffset() is None:
        return None, f"sin zona horaria (`{short_text(value, limit=_LIMITE_VALOR)}`)"
    return parsed, None


def _exenta(call: dict) -> bool:
    return call.get("provider") == "fake" and call.get("deterministic") is True


def _limite_inferior(ctx: AuditContext) -> tuple[datetime | None, str | None, str | None]:
    """``(inicio, aviso, fallo)`` de la corrida.

    El inicio es ``run.json.started_utc`` o, sin ``run.json``,
    ``manifest.timestamp`` si cumple ``%Y%m%d-%H%M%S`` (es UTC, ``cli.py``). Una
    marca con esa forma pero que no es una fecha real (``20261304-250000``) tampoco
    se puede verificar: es un aviso, no una excepción de ``strptime``.
    """
    if ctx.run_info is not None:
        parsed, error = parse_utc(ctx.run_info.started_utc)
        return parsed, None, (f"run.json.started_utc: {error}" if error else None)
    stamp = (ctx.manifest_dict or {}).get("timestamp")
    if isinstance(stamp, str) and _TIMESTAMP_CORRIDA.fullmatch(stamp):
        try:
            return datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC), None, None
        except ValueError:
            pass  # tiene la forma, no es una fecha: queda como no verificable
    loaded = ctx.art.run_info()
    origen = "run.json ilegible" if loaded.present and not loaded.ok else "sin run.json"
    return (
        None,
        f"límite inferior no verificable (timestamp `{_mostrar(stamp)}`, {origen})",
        None,
    )


def _limite_superior_sin_manifiesto(ctx: AuditContext) -> str:
    """Por qué no se puede comprobar el límite superior cuando no hay manifiesto utilizable.

    Un manifiesto que existe pero no se puede leer es «ilegible». Uno que no existe es
    «ausente»; y si la corrida no llegó al gate final es lo esperable, no un defecto: el
    motor lo escribe al evaluar ese gate (spec §4.2), así que una corrida en pausa todavía no
    lo tiene.
    """
    if ctx.manifest.present:
        return "límite superior no verificable (manifiesto ilegible)"
    if "reporte" in ctx.state.reached:
        return "límite superior no verificable: manifiesto ausente"
    return "límite superior no verificable: manifiesto ausente (corrida sin decisión final)"


def _limitar(items: list[str], maximo: int = _MAX) -> str:
    more = len(items) - maximo
    return "; ".join(items[:maximo]) + (f" (+{more} más)" if more > 0 else "")


def _antes(a: datetime, b: datetime) -> bool:
    """``a`` cae más de ``TOLERANCIA`` antes que ``b`` (se resta: ver la docstring del módulo)."""
    return b - a > TOLERANCIA


def check_timing(ctx: AuditContext) -> Verdict:
    """PRISMA 27 / trAIce M2: las marcas de tiempo son posibles."""
    fails: list[str] = []
    warns: list[str] = []
    marks: list[tuple[str, datetime]] = []

    calls = ctx.llm_calls
    call_marks: list[tuple[dict, datetime]] = []
    for i, call in enumerate(calls):
        parsed, error = parse_utc(call.get("timestamp_utc"))
        if parsed is None:
            fails.append(f"llm_calls[{i}]: {error}")
        else:
            call_marks.append((call, parsed))
            marks.append((f"llm_calls[{i}]", parsed))
        if call.get("deterministic") is True and call.get("provider") != "fake":
            fails.append(
                f"llm_calls[{i}]: `deterministic: true` con proveedor "
                f"`{_mostrar(call.get('provider'))}` (ningún proveedor real lo garantiza)"
            )

    ledger_marks: list[tuple[int, datetime]] = []
    for number, entry in ctx.ledger.entries:
        parsed, error = parse_utc(entry.timestamp_utc)
        if parsed is None:
            fails.append(f"ledger línea {number}: {error}")
        else:
            ledger_marks.append((number, parsed))
            marks.append((f"ledger línea {number}", parsed))

    if ctx.llm_calls_ilegible is not None:
        # Sin llamadas que leer no se cae a la copia del manifiesto: sus marcas no se comprobaron.
        warns.append(f"no se pueden comprobar las marcas de las llamadas: {LLM_CALLS_ILEGIBLE}")

    lower, lower_warn, lower_fail = _limite_inferior(ctx)
    warns += [lower_warn] if lower_warn else []
    fails += [lower_fail] if lower_fail else []
    upper = None
    if ctx.manifest_dict is None:
        warns.append(_limite_superior_sin_manifiesto(ctx))
    elif "created_utc" not in ctx.manifest_dict:
        warns.append("límite superior no verificable (manifest.created_utc ausente)")
    else:
        upper, error = parse_utc(ctx.manifest_dict.get("created_utc"))
        if error:
            fails.append(f"manifest.created_utc: {error}")

    for label, mark in marks:
        if lower is not None and _antes(mark, lower):
            fails.append(f"{label} anterior al inicio de la corrida ({mark.isoformat()})")
        if upper is not None and _antes(upper, mark):
            fails.append(f"{label} posterior al manifiesto ({mark.isoformat()})")

    latest: datetime | None = None
    for number, mark in ledger_marks:
        if latest is not None and _antes(mark, latest):
            back = (latest - mark).total_seconds()
            fails.append(f"ledger línea {number}: retrocede {back:.0f} s")
        latest = mark if latest is None else max(latest, mark)

    heuristic = sorted(mark for call, mark in call_marks if not _exenta(call))
    median_ms: float | None = None
    if len(heuristic) >= 2:
        gaps = [b - a for a, b in zip(heuristic, heuristic[1:], strict=False)]
        median = statistics.median(gaps)
        median_ms = median.total_seconds() * 1000
        if len(heuristic) >= MIN_LLAMADAS_HEURISTICA and median < MEDIANA_MINIMA:
            warns.append(
                f"{len(heuristic)} llamadas no fake con una mediana de {median_ms:.3f} ms entre "
                "marcas: una llamada real tarda ≥ 300 ms (≥ 1 s con `claude -p`); si usaste una "
                "API por lotes, decláralo"
            )
    if len(ledger_marks) >= MIN_MARCAS_LEDGER:
        redondas = sum(1 for _, mark in ledger_marks if mark.microsecond == 0)
        if redondas * 2 >= len(ledger_marks):
            warns.append(
                f"{redondas}/{len(ledger_marks)} marcas del ledger sin fracción de segundo: "
                "huelen a horas tecleadas"
            )

    if fails:
        return "FAIL", f"{len(fails)} marca(s) imposibles: {_limitar(fails)}."
    if warns:
        return "WARN", "; ".join(warns) + "."
    # Un límite no verificable es un WARN (arriba): con PASS los dos están comprobados.
    detail = f"{len(marks)} marcas dentro de [inicio, manifiesto] ±2 s"
    exentas = sum(1 for call in calls if _exenta(call))
    if median_ms is not None:
        detail += f"; mediana entre llamadas no fake {median_ms:.0f} ms"
        if exentas:
            detail += f" ({exentas} de {len(calls)} llamadas fake deterministas exentas)"
    elif exentas == len(calls) and calls:
        detail += "; llamadas fake deterministas, exentas de las heurísticas"
    elif calls:
        # Mezcla de fake y reales con < 2 reales: no hay intervalos que medir, pero tampoco
        # están exentas todas las llamadas.
        detail += "; "
        if exentas:
            detail += f"{exentas} de {len(calls)} llamadas fake deterministas exentas; "
        detail += f"{len(calls) - exentas} no fake: sin intervalos que medir"
    return "PASS", detail + "."


def _etiqueta(value: object) -> str:
    """Una cadena tal cual; cualquier otra cosa (lista, mapa, bomba de alias) acotada."""
    return value if isinstance(value, str) else short_repr(value)


def check_response_overlap(ctx: AuditContext) -> Verdict:
    """trAIce M2: dos modelos distintos no devuelven las mismas respuestas."""
    if ctx.manifest_dict is None:
        return "N/A", NA_MANIFIESTO
    if ctx.llm_calls_ilegible is not None:
        return "WARN", f"no se pueden comparar las respuestas: {LLM_CALLS_ILEGIBLE}."
    hashes: dict[str, list[str]] = {}
    for call in ctx.llm_calls:
        response = call.get("response_sha256")
        if call.get("provider") == "fake" or not response or not isinstance(response, str):
            continue
        key = f"{_etiqueta(call.get('provider'))}:{_etiqueta(call.get('model'))}"
        hashes.setdefault(key, []).append(response)
    eligible = {m: set(h) for m, h in hashes.items() if len(h) >= MIN_LLAMADAS_SOLAPE}
    names = sorted(eligible)
    compared = names[:_MAX_MODELOS_SOLAPE]
    findings: list[str] = []
    for a, b in combinations(compared, 2):
        common = eligible[a] & eligible[b]
        smaller = min(len(eligible[a]), len(eligible[b]))
        if smaller and len(common) / smaller >= UMBRAL_SOLAPE:
            findings.append(
                f"`{short_text(a, limit=_LIMITE_VALOR)}` y `{short_text(b, limit=_LIMITE_VALOR)}` "
                f"comparten {len(common)} de {smaller} respuestas"
            )
    skipped = len(names) - len(compared)
    notes: list[str] = []
    if findings:
        notes.append(
            _limitar(findings, _MAX_SOLAPES) + ": dos modelos distintos no dan las mismas "
            "respuestas (reconstrucción, C3, o un callback `agent` que no distingue modelos, A8)"
        )
    if skipped:
        notes.append(
            f"{len(names)} modelos no fake con ≥ {MIN_LLAMADAS_SOLAPE} llamadas: solo se "
            f"comparan los {_MAX_MODELOS_SOLAPE} primeros"
        )
    if notes:
        return "WARN", "; ".join(notes) + "."
    return "PASS", (
        f"sin respuestas compartidas entre modelos ({len(eligible)} modelo(s) no fake con "
        f"≥ {MIN_LLAMADAS_SOLAPE} llamadas)."
    )
