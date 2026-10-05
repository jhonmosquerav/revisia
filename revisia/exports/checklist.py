"""Checklists PRISMA 2020 (27 ítems) y PRISMA-trAIce (uso de IA).

El checklist 2020 se emite como andamiaje: el sistema pre-rellena la evidencia
de los ítems que el pipeline cubre (búsqueda, selección, flujo, registro,
disponibilidad de datos) y deja el resto para que el humano lo complete. El
checklist trAIce se rellena automáticamente desde los ``RunMeta`` de la corrida
(modelos, determinismo) y desde el ledger: la autonomía efectiva y quién decidió de
verdad cada gate (``describe_gate``), sin afirmar una validación humana que no ocurrió.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from revisia.config import JUDGMENT_STAGES
from revisia.metrics import fmt_metric
from revisia.provenance.ledger import AUTO_APPROVE_ACTOR, HUMAN_ACTOR_PREFIX
from revisia.provenance.runmeta import RunMeta
from revisia.schemas.artifacts import GATED_STAGES

if TYPE_CHECKING:
    from revisia.exclusions import ExclusionBreakdown
    from revisia.metrics import ScreeningMetrics
    from revisia.schemas.artifacts import GateSummary, SearchLog, SearchLogEntry

# (sección, número, título corto). Numeración principal PRISMA 2020 (1–27).
_PRISMA_2020_ITEMS: list[tuple[str, int, str]] = [
    ("Título", 1, "Título"),
    ("Resumen", 2, "Resumen estructurado"),
    ("Introducción", 3, "Justificación"),
    ("Introducción", 4, "Objetivos"),
    ("Métodos", 5, "Criterios de elegibilidad"),
    ("Métodos", 6, "Fuentes de información"),
    ("Métodos", 7, "Estrategia de búsqueda"),
    ("Métodos", 8, "Proceso de selección"),
    ("Métodos", 9, "Proceso de recolección de datos"),
    ("Métodos", 10, "Ítems de datos"),
    ("Métodos", 11, "Evaluación del riesgo de sesgo"),
    ("Métodos", 12, "Medidas del efecto"),
    ("Métodos", 13, "Métodos de síntesis"),
    ("Métodos", 14, "Evaluación de sesgos de reporte"),
    ("Métodos", 15, "Evaluación de la certeza"),
    ("Resultados", 16, "Selección de estudios"),
    ("Resultados", 17, "Características de los estudios"),
    ("Resultados", 18, "Riesgo de sesgo en los estudios"),
    ("Resultados", 19, "Resultados de estudios individuales"),
    ("Resultados", 20, "Resultados de las síntesis"),
    ("Resultados", 21, "Sesgos de reporte"),
    ("Resultados", 22, "Certeza de la evidencia"),
    ("Discusión", 23, "Discusión"),
    ("Otra información", 24, "Registro y protocolo"),
    ("Otra información", 25, "Apoyo/financiación"),
    ("Otra información", 26, "Conflictos de interés"),
    ("Otra información", 27, "Disponibilidad de datos, código y materiales"),
]

# Evidencia que el pipeline aporta automáticamente para ciertos ítems.
_AUTO_EVIDENCE: dict[int, str] = {
    7: "Cadenas en protocols/<slug>/search_strings/ (PRISMA-S).",
    8: "Decisiones de screening en runs/.../decisions_ledger.jsonl.",
    16: (
        "Diagrama de flujo PRISMA en deliverable/prisma_flow.md (16a); informes "
        "excluidos con su razón en deliverable/excluidos_texto_completo.md (16b)."
    ),
    24: "Registro declarado en protocol.yml (registration).",
    27: "Datos y manifiesto reproducibles en runs/<slug>-<fecha>/.",
}


def _fmt(value: float | None) -> str:
    """Formatea un ratio (o ``n/d`` si es indefinido)."""
    return "n/d" if value is None else f"{value:.3f}"


def render_prisma_2020_checklist() -> str:
    """Renderiza el checklist PRISMA 2020 como andamiaje Markdown."""
    lines = ["# Checklist PRISMA 2020", ""]
    current_section = ""
    for section, number, title in _PRISMA_2020_ITEMS:
        if section != current_section:
            lines.append(f"\n## {section}")
            current_section = section
        evidence = _AUTO_EVIDENCE.get(number)
        suffix = f" — _auto: {evidence}_" if evidence else " — _(completar)_"
        lines.append(f"- [ ] {number}. {title}{suffix}")
    return "\n".join(lines)


# (número, sección, título corto) · PRISMA-S (16 ítems) — extensión para reportar
# búsquedas bibliográficas. Rethlefsen ML, et al. Syst Rev 2021;10:39.
# doi:10.1186/s13643-020-01542-z (CC BY 4.0).
_PRISMA_S_ITEMS: list[tuple[int, str, str]] = [
    (1, "Fuentes y métodos", "Nombre de cada base de datos consultada (con plataforma)"),
    (2, "Fuentes y métodos", "Búsqueda multi-base: si se lanzó en varias a la vez, listarlas"),
    (3, "Fuentes y métodos", "Registros de estudios consultados (ensayos, protocolos)"),
    (4, "Fuentes y métodos", "Recursos en línea y navegación (webs, motores, repositorios)"),
    (5, "Fuentes y métodos", "Búsqueda por citas (hacia atrás/adelante), con herramienta"),
    (6, "Fuentes y métodos", "Contactos: autores, expertos, fabricantes consultados"),
    (7, "Fuentes y métodos", "Otros métodos adicionales de identificación"),
    (8, "Estrategias de búsqueda", "Estrategia COMPLETA de cada base, tal que sea repetible"),
    (9, "Estrategias de búsqueda", "Límites y restricciones (idioma, fecha, tipo) y justificación"),
    (10, "Estrategias de búsqueda", "Filtros de búsqueda publicados usados (con cita)"),
    (11, "Estrategias de búsqueda", "Estrategias adaptadas de trabajos previos (con cita)"),
    (12, "Estrategias de búsqueda", "Actualizaciones de la búsqueda: métodos y fechas"),
    (13, "Estrategias de búsqueda", "Fecha de ejecución de cada búsqueda"),
    (14, "Revisión por pares", "Revisión por pares de la estrategia (PRESS), si se hizo"),
    (15, "Gestión de registros", "Total de registros identificados (por base y en total)"),
    (16, "Gestión de registros", "Método y herramienta de deduplicación"),
]


def _ran_in_engine(entry: SearchLogEntry) -> bool:
    """Si el motor ejecutó esa búsqueda (base con backend o búsqueda inyectada).

    Una importación (``manual_import``) lleva la hora de lectura del fichero, no la de
    la búsqueda externa que lo originó; una base ``manual_only`` o desconocida no se
    ejecutó.
    """
    return entry.kind == "injected" or (entry.kind == "database" and entry.backend is not None)


def engine_search_date(search_log: SearchLog) -> str:
    """Fecha (UTC, ``AAAA-MM-DD``) en que el motor ejecutó la búsqueda.

    La más temprana de las búsquedas que ejecutó el motor (bases con backend o
    búsqueda inyectada; no las importaciones); si ninguna tiene hora, la de inicio
    del log. Es la fecha que se reporta, no la tecleada en ``search_window.executed``
    (PRISMA-S 13).
    """
    starts = [e.started_utc for e in search_log.entries if _ran_in_engine(e) and e.started_utc]
    return min(starts or [search_log.started_utc])[:10]


_FAILED_DATABASE = " (falló: no devolvió registros)"


def label_databases(databases: Iterable[str], search_log: SearchLog | None) -> list[str]:
    """Nombres de las bases para un texto que las da por consultadas, marcando las fallidas.

    Con ``search_log``, una base cuya búsqueda falló no devolvió registros y no se
    puede decir que se consultó sin más (``PubMed (falló: no devolvió registros)``); el
    error concreto queda en ``01_search/log.json`` y en los ítems 8 y 13 de PRISMA-S.
    Sin log no se sabe y la lista sale como está.
    """
    if search_log is None:
        return list(databases)
    failed = {
        e.database.casefold()
        for e in search_log.entries
        if e.kind == "database" and e.status == "failed"
    }
    return [f"{db}{_FAILED_DATABASE}" if db.casefold() in failed else db for db in databases]


def _engine_source(entry: SearchLogEntry) -> str:
    """Fuente que ejecutó el motor, para listarla cuando el protocolo no declara bases."""
    if entry.kind == "injected":
        return "búsqueda inyectada (search_fn)"
    return f"{entry.database}{_FAILED_DATABASE}" if entry.status == "failed" else entry.database


def _flat(text: str) -> str:
    """Colapsa el espacio en blanco (saltos de línea incluidos) a un solo espacio.

    Una cadena de búsqueda multilínea partiría el ítem del checklist y, al pasar a
    HTML (Anexo E), una línea que empiece por ``#`` o ``- `` se volvería un encabezado
    o una lista. ``log.json`` conserva la cadena exacta; solo se aplana al renderizar.
    """
    return " ".join(text.split())


_MAX_ERROR_CHARS = 120


def _failure_note(entry: SearchLogEntry) -> str:
    """``(falló: <error>)`` de una entrada fallida (error ya redactado, recortado)."""
    if entry.status != "failed":
        return ""
    error = _flat(entry.error or "sin detalle")
    if len(error) > _MAX_ERROR_CHARS:
        error = error[: _MAX_ERROR_CHARS - 1] + "…"
    return f" (falló: {error})"


def _strings_evidence(search_log: SearchLog) -> str:
    """PRISMA-S 8: la cadena efectiva de cada base, tal como se ejecutó."""
    parts: list[str] = []
    for entry in search_log.entries:
        if entry.kind == "injected":
            parts.append("búsqueda inyectada (search_fn): sin cadena por base")
            continue
        if entry.kind != "database":
            continue
        where = f" ({entry.query_file})" if entry.query_file else ""
        query = _flat(entry.query or "")
        if entry.status == "unknown":
            parts.append(f"{entry.database}: base desconocida, sin búsqueda")
        elif entry.status == "manual_only" and entry.query_origin == "file":
            # No la ejecutó el motor: es la cadena declarada de una búsqueda externa
            # cuyos resultados entran por imported/.
            parts.append(
                f"{entry.database}: cadena declarada para una búsqueda externa "
                f"(importada vía imported/): «{query}»{where}"
            )
        elif entry.query_origin == "file":
            parts.append(f"{entry.database}: «{query}»{where}{_failure_note(entry)}")
        elif entry.query_origin == "question_fallback":
            parts.append(
                f"{entry.database}: ⚠ sin cadena propia, se usó la pregunta «{query}»"
                f"{_failure_note(entry)}"
            )
        else:
            parts.append(f"{entry.database}: importación manual (imported/)")
    return "Cadenas ejecutadas (01_search/log.json) — " + " · ".join(parts) + "."


def _date_note(entry: SearchLogEntry) -> str:
    """``<fuente> <fecha>`` de una entrada con hora; las importaciones, «importado el»."""
    day = (entry.started_utc or "")[:10]
    if entry.kind == "manual_import":
        verb = "importación intentada el" if entry.status == "failed" else "importado el"
        return f"{entry.database} {verb} {day}{_failure_note(entry)}"
    return f"{entry.database} {day}{_failure_note(entry)}"


def _dates_evidence(search_log: SearchLog, search_window: dict[str, str] | None) -> str:
    """PRISMA-S 13: fecha de ejecución registrada por el motor, por base."""
    dated = [_date_note(e) for e in search_log.entries if e.started_utc]
    text = f"Búsqueda ejecutada (fecha del motor): {engine_search_date(search_log)}"
    if dated:
        text += f" ({' · '.join(dated)})"
    declared = (search_window or {}).get("executed")
    if declared and declared != engine_search_date(search_log):
        text += (
            f". ⚠ Difiere de search_window.executed ({declared}): reporta la fecha del "
            "motor o explica la diferencia"
        )
    return text + "."


def render_prisma_s_checklist(
    *,
    databases: list[str] | None = None,
    search_window: dict[str, str] | None = None,
    counts=None,
    search_log: SearchLog | None = None,
) -> str:
    """Renderiza el checklist PRISMA-S (16 ítems) pre-rellenando lo que el motor sabe.

    La búsqueda es la etapa más automatizada del pipeline, así que la mayor
    parte de la evidencia sale sola: bases, cadenas versionadas, ventana,
    fechas, totales por base y método de deduplicación. Con ``search_log``
    (``01_search/log.json``, Ola 1) los ítems 8 y 13 salen de lo que el motor
    ejecutó de verdad: la cadena de cada base (señalando dónde se usó la
    pregunta) y la fecha registrada, no la tecleada (auditoría 2026-09-03, M12).
    """
    auto: dict[int, str] = {}
    if databases:
        listed = ", ".join(label_databases(databases, search_log))
        auto[1] = f"Bases: {listed} (APIs abiertas; ver docs/integraciones.md)."
        auto[2] = "Cada base se consulta por separado con su propia cadena."
        auto[7] = "Import RIS/BibTeX en protocols/<slug>/imported/ (Scopus/WoS/gestores)."
        auto[8] = "Cadenas completas versionadas en protocols/<slug>/search_strings/<base>.txt."
    if search_window:
        limits = " · ".join(f"{k}: {v}" for k, v in search_window.items() if v)
        if limits:
            auto[9] = f"Ventana temporal declarada en protocol.yml — {limits}."
        if search_window.get("executed"):
            auto[13] = f"Búsqueda ejecutada: {search_window['executed']}."
    if counts is not None:
        per_db = " · ".join(f"{db}: {n}" for db, n in sorted(counts.identified_by_source.items()))
        auto[15] = f"Total identificados: {counts.identified}" + (
            f" ({per_db})." if per_db else "."
        )
        auto[16] = (
            f"Deduplicación determinista del motor (DOI/título normalizado): "
            f"{counts.duplicates_removed} duplicados eliminados."
        )
    if search_log is not None:
        auto[8] = _strings_evidence(search_log)
        auto[13] = _dates_evidence(search_log, search_window)
    lines = [
        "# Checklist PRISMA-S · reporte de la búsqueda (16 ítems)",
        "",
        "> Rethlefsen ML, et al. PRISMA-S. _Syst Rev_ 2021;10:39. doi:10.1186/s13643-020-01542-z",
        "",
    ]
    current_section = ""
    for number, section, title in _PRISMA_S_ITEMS:
        if section != current_section:
            lines.append(f"\n## {section}")
            current_section = section
        evidence = auto.get(number)
        suffix = f" — _auto: {evidence}_" if evidence else " — _(completar)_"
        lines.append(f"- [ ] {number}. {title}{suffix}")
    return "\n".join(lines)


# (número, título corto) · checklist PRISMA 2020 para resúmenes (12 ítems,
# tabla 2 de la declaración; hereda PRISMA-A 2013 con redacción armonizada).
_PRISMA_ABSTRACTS_ITEMS: list[tuple[int, str]] = [
    (1, "Título: identificar como revisión sistemática"),
    (2, "Objetivos: pregunta(s) que aborda la revisión"),
    (3, "Criterios de elegibilidad"),
    (4, "Fuentes de información y fecha de la última búsqueda"),
    (5, "Riesgo de sesgo: métodos de evaluación"),
    (6, "Síntesis de resultados: métodos de presentación/síntesis"),
    (7, "Estudios incluidos: número de estudios y participantes"),
    (8, "Síntesis de resultados: resultados principales (efecto y precisión)"),
    (9, "Limitaciones de la evidencia"),
    (10, "Interpretación: implicaciones principales"),
    (11, "Financiación de la revisión"),
    (12, "Registro: nombre del registro y número"),
]


def render_prisma_abstracts_checklist(
    *,
    counts=None,
    databases: list[str] | None = None,
    search_window: dict[str, str] | None = None,
    registration: dict[str, str] | None = None,
    search_log: SearchLog | None = None,
) -> str:
    """Renderiza el checklist PRISMA 2020 para resúmenes (12 ítems).

    Como el checklist principal, se emite de andamiaje: pre-rellena la
    evidencia que el pipeline conoce (fuentes, ventana, conteos, registro) y
    deja el juicio editorial al humano. Con ``search_log``, la fecha de la
    búsqueda (ítem 4) es la que registró el motor, y sale aunque el protocolo no
    declare bases: el motor buscó en OpenAlex por defecto y lo dejó en el log.
    """
    auto: dict[int, str] = {}
    if databases or search_log is not None:
        executed = (search_window or {}).get("executed") or "(sin fecha ejecutada)"
        sources = list(databases or [])
        if search_log is not None:
            executed = f"{engine_search_date(search_log)} (registrada por el motor)"
            if sources:
                sources = label_databases(sources, search_log)
            else:
                sources = [_engine_source(e) for e in search_log.entries if _ran_in_engine(e)]
        listed = ", ".join(sources) or "(ninguna registrada)"
        auto[4] = f"Bases: {listed} · última búsqueda: {executed}."
    if counts is not None:
        auto[7] = f"{counts.included} estudios incluidos (ver prisma_flow.md)."
    if registration and any(registration.values()):
        auto[12] = ", ".join(f"{k}={v}" for k, v in registration.items() if v) + "."
    lines = ["# Checklist PRISMA 2020 · resúmenes (12 ítems)", ""]
    for number, title in _PRISMA_ABSTRACTS_ITEMS:
        evidence = auto.get(number)
        suffix = f" — _auto: {evidence}_" if evidence else " — _(completar)_"
        lines.append(f"- [ ] {number}. {title}{suffix}")
    return "\n".join(lines)


def describe_gate(stage: str, summary: GateSummary | None) -> str:
    """Quién decidió de verdad un gate, en una frase (M13).

    Sale del ledger reducido por ``summarize_gates`` (el mismo reductor que usa
    el auditor, D12): nunca se afirma una validación humana que no ocurrió.
    """
    if summary is None:
        if stage == "reporte":
            return "pendiente de la decisión final"
        return "pendiente (sin decisión registrada)"
    if summary.action == "auto-proceed":
        return f"auto-proceed ({summary.actor}, autonomía {summary.autonomy}): sin revisión humana"
    if summary.actor == AUTO_APPROVE_ACTOR:
        return "aprobado por auto-approve (demo): NO es una validación humana"
    verb = "aprobado" if summary.action == "approve" else "rechazado"
    if not summary.actor.startswith(HUMAN_ACTOR_PREFIX):
        return f"{verb} por {summary.actor} (no humano)"
    extras = []
    if summary.n_labels:
        extras.append(f"{summary.n_labels} etiqueta(s) por registro")
    if summary.n_flag_reviews:
        extras.append(f"{summary.n_flag_reviews} cita(s) marcada(s) adjudicada(s)")
    if summary.forced_human:
        extras.append("forzado a humano por citas marcadas")
    return f"{verb} por humano ({summary.actor})" + "".join(f" · {e}" for e in extras)


def human_validation_summary(gates: Mapping[str, GateSummary]) -> str:
    """¿Resolvió un humano cada gate de juicio con decisión? (M13)."""
    reached = [s for s in JUDGMENT_STAGES if s in gates]
    if not reached:
        return "ningún gate de juicio tiene todavía una decisión registrada."
    without_human = [s for s in reached if not gates[s].actor.startswith(HUMAN_ACTOR_PREFIX)]
    if without_human:
        detail = ", ".join(f"{s} ({gates[s].actor})" for s in without_human)
        return (
            f"⚠ gates de juicio sin decisión humana: {detail}. Sin revisión humana la "
            "corrida no es evidencia publicable; decláralo."
        )
    return f"un humano resolvió todos los gates de juicio con decisión ({', '.join(reached)})."


def render_traice_checklist(
    run_metas: Iterable[RunMeta],
    autonomy_effective: Mapping[str, str],
    *,
    gates: Mapping[str, GateSummary] | None = None,
    forced_human: bool = False,
    metrics: ScreeningMetrics | None = None,
    exclusions: ExclusionBreakdown | None = None,
    search_window: dict[str, str] | None = None,
) -> str:
    """Renderiza el checklist PRISMA-trAIce a partir de la procedencia real.

    Args:
        run_metas: todos los ``RunMeta`` registrados en la corrida.
        autonomy_effective: autonomía con la que se aplica cada gate (la
            declarada, o A1 en ``reporte`` si el gate quedó forzado a humano).
        gates: decisión efectiva por gate (``summarize_gates`` del ledger). El
            checklist se escribe antes del gate final, que figura "pendiente".
        forced_human: el gate final exige humano por citas marcadas (M5).
        metrics: métricas de cribado frente al gold standard, si se calcularon.
        exclusions: desglose de exclusiones humano vs IA, si se calculó.
        search_window: ventana temporal de la búsqueda declarada en el protocolo.
    """
    gates = gates or {}
    metas = list(run_metas)
    models = sorted({f"{m.provider}:{m.model}" for m in metas})
    any_nondeterministic = any(not m.deterministic for m in metas)
    lines = [
        "# Checklist PRISMA-trAIce (uso de IA)",
        "",
        f"- Modelos usados: {', '.join(models) or '(ninguno)'}",
        f"- Total de llamadas a IA registradas: {len(metas)}",
        f"- Determinismo a nivel token: {'NO garantizado' if any_nondeterministic else 'sí'}"
        " (la reproducibilidad a nivel decisión se asegura vía el ledger).",
        "- Prompts: versionados en revisia/prompts/ y hash-eados por llamada (RunMeta).",
        f"- Validación humana: {human_validation_summary(gates)}",
        "",
        "## Autonomía efectiva y decisión por gate",
    ]
    for stage in GATED_STAGES:
        if stage not in autonomy_effective:
            continue
        line = f"- {stage} ({autonomy_effective[stage]}): {describe_gate(stage, gates.get(stage))}"
        if stage == "reporte" and forced_human and stage not in gates:
            line += " · exige decisión humana: el verificador marcó citas"
        lines.append(line)
    if metrics is not None:
        lines += [
            "",
            "## Métricas de cribado (propuesta de la IA vs gold standard humano)",
            "- Se mide la propuesta de la IA (`ensemble_label`) frente al gold humano, no la "
            "decisión final con las correcciones humanas (D6): evalúa al sistema, no al "
            "revisor que lo corrige.",
            f"- Recall (evidencia recuperada): {_fmt(metrics.recall)}",
            f"- Lost-Evidence (evidencia perdida): {_fmt(metrics.lost_evidence)}",
            f"- MCC: {fmt_metric(metrics.mcc)} · "
            f"WMCC (w={metrics.wmcc_fn_weight:g}): {fmt_metric(metrics.wmcc)}",
            "- Cohen's kappa (propuesta de la IA vs gold humano): "
            f"{fmt_metric(metrics.cohen_kappa)}",
            f"- Confusión (n={metrics.n}): TP={metrics.tp} FP={metrics.fp} "
            f"FN={metrics.fn} TN={metrics.tn}",
            "- _accuracy se omite a propósito (engañosa con datos desbalanceados)._",
        ]
    if search_window:
        win = " · ".join(f"{k}: {v}" for k, v in search_window.items() if v)
        lines += ["", "## Ventana temporal de la búsqueda", f"- {win or '(no declarada)'}"]

    lines += ["", "## Exclusiones separadas humano vs IA"]
    if exclusions is not None:
        lines += [
            f"- Excluidos por IA (sin rescate humano): {exclusions.excluded_ai}",
            f"- Excluidos por humano (explícito): {exclusions.excluded_human}",
            f"- Rescatados por humano (IA excluía, humano incluyó): "
            f"{exclusions.overridden_to_include}",
            f"- Cortados por humano (IA no excluía, humano excluyó): "
            f"{exclusions.overridden_to_exclude}",
        ]
    else:
        lines.append("- [ ] (sin datos de screening para desglosar)")

    lines += [
        "",
        "## Pendientes de declaración humana",
        "- [ ] Gobernanza de datos sensibles (qué se envió a APIs externas).",
        "- [ ] Depósito de prompts/outputs en repositorio abierto (OSF/Zenodo).",
    ]
    return "\n".join(lines)
