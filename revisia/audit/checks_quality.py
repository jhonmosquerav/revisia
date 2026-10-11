"""Checks de calidad del cribado y de la síntesis: ``gold``, ``thresholds``, ``grounding``.

``thresholds`` aplica D7: los umbrales del protocolo según lo que mide cada
métrica. Un recall bajo ``recall_target`` significa estudios relevantes
perdidos y es FAIL mientras quede alguna exclusión IA de T/A sin etiqueta
humana; si un humano las etiquetó todas (en ``screening_ta/decision.yml``,
reanudando, D14), ningún estudio quedó fuera sin que alguien lo mirara y baja a
WARN ("decláralo"). Que esas etiquetas de ``decisions.json`` sean de verdad del
ledger lo verifica ``hitl`` por registro. Un κ bajo ``kappa_min`` (acuerdo
humano-IA) es una desviación a declarar (WARN). El caso de la auditoría
2026-09-03 (A11: κ=0.0 con PASS) deja de pasar en limpio.
``grounding`` aplica D8: una cita marcada por el verificador sin adjudicar por
un humano es FAIL.

Los artefactos son entrada no confiable (revisiones de la Tarea 4): un número
leído de ellos (recall, κ, la matriz, un umbral del protocolo) puede ser
``nan``, ``inf``, negativo o un entero de miles de cifras. Ninguno puede lanzar
(``ZeroDivisionError``, ``ValueError``, ``OverflowError``) ni entrar sin acotar en
un detalle: lo que no se puede medir es un umbral «no medible» (WARN), no una
excepción, y todo valor interpolado pasa por ``short_text``/``short_repr``.
"""

from __future__ import annotations

import math
from typing import Any

from revisia.audit.artifacts import NA_PROTOCOLO, AuditContext, short_repr, short_text
from revisia.audit.checks_flow import TA, included_ids

# La adjudicación de una cita (`flag_review`) y la etiqueta de un registro (`label`) pertenecen
# a la decisión efectiva con el mismo criterio (`decision_sha256` + `request_sha256`), y una sola
# regla, la de `hitl`, evita que se contradigan. El índice de una `flag_review` también se lee
# igual aquí y en la relación 17 de `final_gate`.
from revisia.audit.checks_hitl import de_la_decision_efectiva, indice_de_bandera
from revisia.audit.model import Verdict
from revisia.config import KNOWN_THRESHOLDS
from revisia.metrics import ScreeningMetrics, wilson_interval
from revisia.provenance.ledger import is_human_actor

METRICS = "03_screening/metrics.json"
VERIFICATION = "06_synthesis/verification.json"

_MAX_CLAVES = 5  # claves de `thresholds` desconocidas que se listan
_MAX_FANTASMAS = 3  # citas con id fuera de los incluidos que se listan
_MAX_INDICES = 5  # índices de citas que se listan
_MAX_ACTORES = 5  # actores que se listan
_LIMITE_NUMERO = 40  # caracteres de un número (un entero puede tener 4 000 cifras)
_LIMITE_DECIMAL = 1e15  # un float de módulo mayor deja la notación decimal (`_num`)
_TOLERANCIA_RANGO = 1e-9  # holgura del redondeo de coma flotante en los límites de κ y MCC
_LIMITE_ID = 60  # caracteres de un id de cita, una clave o un actor
# Sufijo de `thresholds` cuando el protocolo no valida y los umbrales salen del mapa crudo.
_NOTA_CRUDOS = " (leídos del protocolo en crudo: no valida, ver `protocol_snapshot` y `schemas`)"


def _num(value: object, spec: str = ".3f") -> str:
    """Un número leído de un artefacto, para un detalle: acotado y sin lanzar.

    Un ``int`` de más de 4 300 cifras (el JSON lo carga, ``str`` ya no lo convierte) no
    revienta el check: se muestra como valor fuera de rango. Un ``float`` finito enorme
    (``1e308`` con ``.3f`` ocupa 313 caracteres) o no finito se muestra en notación
    científica: ``1.000e+308``, ``nan``, ``inf``.
    """
    try:
        if isinstance(value, float):
            text = format(value, spec if abs(value) < _LIMITE_DECIMAL else ".3e")
        else:
            text = str(value)
    except ValueError:
        return "(valor fuera de rango)"
    return short_text(text, limit=_LIMITE_NUMERO)


def _metrica(value: float | None, spec: str = ".3f") -> str:
    """Una métrica leída de ``metrics.json``: ``no calculable`` si falta; si no, :func:`_num`."""
    return "no calculable" if value is None else _num(value, spec)


def _es_correlacion(value: float) -> bool:
    """``value`` cabe en [-1, 1] (κ y MCC), con la holgura del redondeo de coma flotante."""
    return -1 - _TOLERANCIA_RANGO <= value <= 1 + _TOLERANCIA_RANGO


def _finito(value: float | None) -> float | None:
    """``value`` si es un número finito; ``None`` si falta o es ``nan``/``inf``."""
    return value if value is not None and math.isfinite(value) else None


def _con_resto(items: list[str], maximo: int) -> str:
    """Los primeros ``maximo`` elementos, unidos por comas, y cuántos más hay."""
    shown = ", ".join(items[:maximo])
    more = len(items) - maximo
    return shown + (f" (+{more} más)" if more > 0 else "")


def _matrix_note(ctx: AuditContext) -> str:
    """Por qué ``metrics.json`` no valida (el FAIL lo da ``schemas``)."""
    raw = ctx.art.json(METRICS)
    if not raw.ok or not isinstance(raw.value, dict):
        return "metrics.json ilegible (ver `schemas`)."
    keys = ("tp", "fp", "fn", "tn")
    if all(k in raw.value for k in keys):
        return (
            f"Métricas vs gold humano: recall={short_repr(raw.value.get('recall'))} · "
            "metrics.json con matriz de confusión ilegible (tp/fp/fn/tn con algún valor no "
            "numérico; ver `schemas`)."
        )
    return "metrics.json sin matriz de confusión: métricas no verificables (ver `schemas`)."


def check_gold(ctx: AuditContext) -> Verdict:
    """trAIce M9/R2: métricas del cribado IA contra un gold humano, informativas."""
    loaded = ctx.art.artifact(METRICS)
    if not loaded.present:
        return "WARN", (
            "Sin gold standard: no hay recall/kappa del cribado IA vs humano. "
            "Crea gold.yml (revisia gold-template) antes de publicar."
        )
    if not loaded.ok:
        return "WARN", _matrix_note(ctx)
    m: ScreeningMetrics = loaded.value
    gold_una_clase = m.tp + m.fn == 0 or m.tn + m.fp == 0
    ia_una_clase = m.tp + m.fp == 0 or m.fn + m.tn == 0
    # Un `nan`/`inf` no es una métrica informativa: se trata como indefinida.
    kappa, matthews = _finito(m.cohen_kappa), _finito(m.mcc)
    # κ y MCC son coeficientes de correlación: fuera de [-1, 1] es un dato corrupto, no una métrica.
    fuera = [
        nombre
        for nombre, valor in (("kappa", kappa), ("MCC", matthews))
        if valor is not None and not _es_correlacion(valor)
    ]
    if fuera:
        return "WARN", (
            f"Métricas vs gold humano: recall={_metrica(m.recall)} · {' y '.join(fuera)} fuera "
            "de [-1, 1]: no verificable (ver `arithmetic`)."
        )
    if kappa is None or matthews is None or gold_una_clase or ia_una_clase:
        return "WARN", (
            f"Métricas vs gold humano: recall={_metrica(m.recall)} · kappa/mcc no calculable: "
            "métricas indefinidas o no informativas (el gold o la IA asignaron una sola clase). "
            "Amplía el gold con registros relevantes e irrelevantes."
        )
    return "PASS", (
        f"Métricas vs gold humano (n={_num(m.n)}): recall={_metrica(m.recall)} · "
        f"kappa={_metrica(kappa)} · MCC={_metrica(matthews)} (accuracy omitida a propósito)."
    )


def potencia_minima(target: float) -> int | None:
    """Positivos mínimos del gold para que un solo fallo no baje del umbral.

    ⌈1/(1−umbral)⌉: 20 para 0,95; 10 para 0,90. ``None`` si ningún gold tiene potencia
    (umbral ≥ 1) o el umbral no es un número en (0, 1): ``nan``, ``inf`` y los umbrales
    ≤ 0 o > 1 no son medibles y no pueden dividir por cero. El redondeo evita que el
    error de coma flotante convierta 5,000000000000001 en 6.
    """
    if not math.isfinite(target) or target <= 0 or target >= 1:
        return None
    return math.ceil(round(1 / (1 - target), 9))


def ai_exclusions_without_label(ctx: AuditContext) -> int | None:
    """Exclusiones IA de T/A sin etiqueta humana (``None`` si no se leen las decisiones)."""
    loaded = ctx.art.artifact(TA)
    if not loaded.ok:
        return None
    return sum(1 for d in loaded.value if d.ensemble_label == "exclude" and d.human_label is None)


def _ic(k: int, n: int) -> str:
    """Intervalo de Wilson al 95 % de ``k/n``, o «no calculable» (matriz absurda)."""
    try:
        interval = wilson_interval(k, n)
    except (ArithmeticError, ValueError):  # enteros enormes: `z²/n` no cabe en un float
        interval = None
    if interval is None:
        return "[IC95 no calculable]"
    return f"[IC95 {interval[0]:.2f}–{interval[1]:.2f}]"


def _como_umbral(value: object) -> float | None:
    """Un umbral del protocolo como número finito; ``None`` si no lo es.

    Leído en crudo (:func:`_umbrales`), un umbral puede ser ``nan``, ``inf``,
    texto, un booleano o un entero que no cabe en un float: ninguno se puede medir y ninguno
    puede lanzar (``math.isfinite`` de un entero enorme es un ``OverflowError``).
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _recall(
    ctx: AuditContext, m: ScreeningMetrics | None, why: str, declarado: object
) -> tuple[str, str]:
    """``(estado, texto)`` de ``recall_target`` frente a las métricas validadas (D7)."""
    target = _como_umbral(declarado)
    if target is None or not 0 < target <= 1:
        return "WARN", (
            f"recall_target {short_repr(declarado, limit=_LIMITE_NUMERO)} no medible (debe ser "
            "un número en (0, 1])"
        )
    objetivo = f"{target:.2f}"
    if m is None:
        return "WARN", f"recall_target {objetivo} no medible ({why})"
    if m.tp < 0 or m.fn < 0:
        return "WARN", (
            f"recall_target {objetivo} no medible (matriz de confusión fuera de rango; "
            "ver `arithmetic`)"
        )
    positives = m.tp + m.fn
    if positives == 0:
        return "WARN", (
            f"recall_target {objetivo} no medible (recall indefinido: la matriz de confusión no "
            "tiene positivos)"
        )
    # El recall se recalcula de la matriz, la misma de la que salen el IC de Wilson y los
    # positivos del detalle: decidir con el `recall` que guarda `metrics.json` (que `arithmetic`
    # contrasta con la matriz) y mostrar el resto de la matriz era incoherente (revisión de la
    # fase 1 de PR-E). `ScreeningMetrics` exige la matriz: sin ella `m` es `None` (arriba).
    valor = m.tp / positives
    recall = f"recall {valor:.2f} {_ic(m.tp, positives)}"
    if valor < target:
        pending = ai_exclusions_without_label(ctx)
        if pending == 0:
            # D7: un humano revisó cada exclusión de la IA; ningún estudio relevante quedó
            # fuera sin que alguien lo mirara. La desviación del protocolo se declara.
            return "WARN", (
                f"{recall} < {objetivo} con {_num(positives)} positivos, pero todas las "
                "exclusiones IA de T/A tienen etiqueta humana: decláralo (D7)"
            )
        quedan = "un número no verificable de" if pending is None else str(pending)
        return "FAIL", (
            f"{recall} < {objetivo} con {_num(positives)} positivos y {quedan} exclusiones IA de "
            "T/A sin etiqueta humana: etiquétalas en `screening_ta/decision.yml` y reanuda "
            "(D7, D14)"
        )
    minimo = potencia_minima(target)
    if minimo is None:
        return "WARN", (
            f"{recall} ≥ {objetivo} con solo {_num(positives)} positivos en el gold: con un "
            "umbral de 1 un solo fallo ya baja del umbral (gold sin potencia)"
        )
    if positives < minimo:
        return "WARN", (
            f"{recall} ≥ {objetivo} con solo {_num(positives)} positivos en el gold: con menos "
            f"de {minimo} un solo fallo ya baja del umbral (gold sin potencia)"
        )
    return "PASS", f"{recall} ≥ {objetivo} con {_num(positives)} positivos"


def _kappa(m: ScreeningMetrics | None, why: str, declarado: object) -> tuple[str, str]:
    """``(estado, texto)`` de ``kappa_min``: un κ bajo es una desviación a declarar (WARN)."""
    minimo = _como_umbral(declarado)
    if minimo is None or not 0 <= minimo <= 1:
        return "WARN", (
            f"kappa_min {short_repr(declarado, limit=_LIMITE_NUMERO)} no medible (debe ser un "
            "número en [0, 1])"
        )
    objetivo = f"{minimo:.2f}"
    if m is None:
        return "WARN", f"kappa_min {objetivo} no medible ({why})"
    kappa = _finito(m.cohen_kappa)
    if kappa is None:
        return "WARN", f"kappa_min {objetivo} no medible (κ indefinido)"
    if not _es_correlacion(kappa):
        return "WARN", (
            f"kappa_min {objetivo} no medible (κ {_num(kappa)} fuera de [-1, 1]: no verificable; "
            "ver `arithmetic`)"
        )
    if kappa < minimo:
        return "WARN", (
            f"κ {kappa:.2f} < {objetivo}: desviación del protocolo, decláralo (PRISMA 24c)"
        )
    return "PASS", f"κ {kappa:.2f} ≥ {objetivo}"


def _umbrales(ctx: AuditContext) -> tuple[dict[Any, Any], bool] | None:
    """``thresholds`` del protocolo de la corrida y si se leyeron en crudo.

    Con el protocolo válido, los validados. Desde PR-D ``ReviewProtocol`` rechaza al cargar
    un umbral no finito o fuera de rango, así que un protocolo con ``recall_target: .nan``
    queda inválido entero (el FAIL lo dan ``protocol_snapshot`` y ``schemas``) y el umbral
    pasaba a N/A: entonces se lee el mapa ``thresholds`` crudo, para que cada umbral siga
    recibiendo su WARN «no medible» (D7). El crudo es el de la instantánea ``00_protocol/``
    (``AuditContext.protocol_raw``; el del manifiesto en corridas anteriores a la Ola 1 o con
    la instantánea ilegible). ``None`` si tampoco hay eso: sin protocolo legible en ninguna
    fuente o sin un mapa ``thresholds`` en él (la causa la da otra fila).
    """
    if ctx.protocol is not None:
        return dict(ctx.protocol.thresholds), False
    protocolo = ctx.protocol_raw
    crudos = protocolo.get("thresholds") if isinstance(protocolo, dict) else None
    return (crudos, True) if isinstance(crudos, dict) else None


def check_thresholds(ctx: AuditContext) -> Verdict:
    """trAIce M9/R2 / PRISMA 8, 24c: umbrales del protocolo según lo que miden (D7)."""
    umbrales = _umbrales(ctx)
    if umbrales is None:
        # Sin protocolo no hay umbrales que contrastar: es un N/A como en `search_window` y
        # `registration`, y el FAIL lo da la fila que explica por qué (`manifest` o `schemas`).
        return "N/A", NA_PROTOCOLO
    thresholds, crudos = umbrales
    resultados: dict[str, list[str]] = {"FAIL": [], "WARN": [], "PASS": []}

    # Las claves del mapa crudo pueden no ser texto (YAML `5:`): se ordenan ya acotadas.
    unknown = sorted(
        f"`{short_text(k, limit=_LIMITE_ID)}`" for k in thresholds if k not in KNOWN_THRESHOLDS
    )
    if unknown:
        resultados["WARN"].append(
            f"clave(s) desconocida(s) en thresholds: {_con_resto(unknown, _MAX_CLAVES)} "
            f"(¿errata? se entienden {', '.join(sorted(KNOWN_THRESHOLDS))})"
        )
    # Por presencia y no por valor: un `recall_target: null` crudo está declarado y no se mide.
    if "recall_target" not in thresholds and "kappa_min" not in thresholds:
        resultados["WARN"].append(
            "ningún umbral declarado: declara al menos `recall_target` en el protocolo"
        )

    loaded = ctx.art.artifact(METRICS)
    m: ScreeningMetrics | None = loaded.value if loaded.ok else None
    why = "sin gold" if not loaded.present else "metrics.json no válido"

    if "recall_target" in thresholds:
        estado, texto = _recall(ctx, m, why, thresholds["recall_target"])
        resultados[estado].append(texto)
    if "kappa_min" in thresholds:
        estado, texto = _kappa(m, why, thresholds["kappa_min"])
        resultados[estado].append(texto)

    fails, warns, passes = resultados["FAIL"], resultados["WARN"], resultados["PASS"]
    nota = _NOTA_CRUDOS if crudos else ""
    if fails:
        return "FAIL", "; ".join(fails + warns + passes) + nota + "."
    if warns:
        return "WARN", "; ".join(warns + passes) + nota + "."
    return "PASS", "; ".join(passes) + nota + "."


def _adjudications(ctx: AuditContext) -> dict[int, list[str]]:
    """Citas adjudicadas como falso positivo en la decisión efectiva de ``reporte``.

    ``{índice: actores}`` de las entradas ``flag_review`` de la decisión efectiva
    (el mismo ``decision_sha256`` y ``request_sha256`` que el ``approve``), con
    ``verdict: false_positive`` y razón no vacía (spec §4.3). Las de una decisión
    sustituida (un rechazo o una reanudación posteriores, D14) no cuentan: son
    huérfanas. Sin ``decision_sha256`` (ledger anterior a la Ola 1) no hay
    adjudicación posible.
    """
    gate = ctx.gates.get("reporte")
    if gate is None or gate.action != "approve" or gate.decision_sha256 is None:
        return {}
    result: dict[int, list[str]] = {}
    for entry in ctx.ledger.decisions:
        if entry.stage != "reporte" or entry.action != "flag_review":
            continue
        if not de_la_decision_efectiva(ctx, entry):
            continue
        reason = entry.detail.get("reason")
        if entry.detail.get("verdict") != "false_positive":
            continue
        if not isinstance(reason, str) or not reason.strip():
            continue
        indice = indice_de_bandera(entry.target)
        if indice is not None:
            result.setdefault(indice, []).append(entry.actor)
    return result


def _indices(items: list[int]) -> str:
    """``[0, 2, 5]`` con los primeros ``_MAX_INDICES`` y cuántos más hay."""
    return "[" + _con_resto([str(i) for i in items], _MAX_INDICES) + "]"


def check_grounding(ctx: AuditContext) -> Verdict:
    """trAIce M8/M9: citas de la síntesis verificadas; las marcadas, adjudicadas (D8)."""
    loaded = ctx.art.artifact(VERIFICATION)
    if not loaded.ok:
        estado = "ausente" if not loaded.present else "inválido"
        return "N/A", f"no aplica: {VERIFICATION} {estado} (ver `stage_artifacts` y `schemas`)."
    report = loaded.value
    checks = report.checks
    ids = included_ids(ctx)
    included = set(ids) if ids is not None else None
    fails: list[str] = []

    # `recompute_flag` muta el modelo, que el contexto comparte con otros checks: se aplica
    # a una copia.
    recomputed = report.model_copy(deep=True).recompute_flag()
    if report.hallucination_flagged != recomputed:
        fails.append(
            f"bandera inconsistente: hallucination_flagged={report.hallucination_flagged} y "
            f"los checks dan {recomputed} (recompute_flag)"
        )
    if included is not None:
        phantom = [
            f"{i} (`{short_text(c.cited_id, limit=_LIMITE_ID)}`)"
            for i, c in enumerate(checks)
            if c.exists_in_corpus and c.cited_id not in included
        ]
        if phantom:
            fails.append(
                "exists_in_corpus: true para ids que no están entre los incluidos: "
                + _con_resto(phantom, _MAX_FANTASMAS)
            )

    flagged = [i for i, c in enumerate(checks) if not c.exists_in_corpus or not c.grounded]
    adjudicated = _adjudications(ctx)
    missing = [i for i in flagged if i not in adjudicated]
    actors = sorted({actor for i in flagged for actor in adjudicated.get(i, [])})
    non_human = [a for a in actors if not is_human_actor(a)]
    if missing:
        fails.append(
            f"{len(missing)} cita(s) marcada(s) sin adjudicar por un humano (D8): índices "
            f"{_indices(missing)}; adjudícalas en `reporte/decision.yml` (`flags`) o rechaza el "
            "reporte"
        )
    if non_human:
        listados = _con_resto([short_text(a, limit=_LIMITE_ID) for a in non_human], _MAX_ACTORES)
        fails.append(f"adjudicación de un actor no humano: {listados}")

    if fails:
        return "FAIL", "; ".join(fails) + "."
    if ids is None:
        # Las decisiones a texto completo no se leen: ni «ninguna marcada» ni «0 incluidos» son
        # verdad comprobada (la causa está en `stage_artifacts` y `schemas`).
        return "WARN", (
            f"{len(checks)} citas, {len(flagged)} marcada(s): no se pueden contrastar con los "
            "incluidos (04_fulltext/decisions.json no se lee; ver `stage_artifacts`)."
        )
    if flagged:
        quienes = _con_resto([short_text(a, limit=_LIMITE_ID) for a in actors], _MAX_ACTORES)
        return "WARN", (
            f"{len(flagged)} citas marcadas, adjudicadas como falsos positivos por "
            f"{quienes}: decláralo."
        )
    if not checks:
        if ids:
            return "WARN", (
                f"la síntesis no cita ningún estudio ({len(ids)} incluidos): no hay citas que "
                "verificar."
            )
        return "PASS", "sin incluidos ni citas que verificar."
    cited = len({c.cited_id for c in checks if c.cited_id in included})
    return "PASS", f"{len(checks)} citas, ninguna marcada; {cited}/{len(ids)} incluidos citados."
