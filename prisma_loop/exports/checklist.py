"""Checklists PRISMA 2020 (27 ítems) y PRISMA-trAIce (uso de IA).

El checklist 2020 se emite como andamiaje: el sistema pre-rellena la evidencia
de los ítems que el pipeline cubre (búsqueda, selección, flujo, registro,
disponibilidad de datos) y deja el resto para que el humano lo complete. El
checklist trAIce se rellena automáticamente desde los ``RunMeta`` de la corrida
(modelos, determinismo) y la autonomía por etapa.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from prisma_loop.provenance.runmeta import RunMeta

if TYPE_CHECKING:
    from prisma_loop.exclusions import ExclusionBreakdown
    from prisma_loop.metrics import ScreeningMetrics

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
    16: "Diagrama de flujo PRISMA en deliverable/prisma_flow.md.",
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


def render_prisma_s_checklist(
    *,
    databases: list[str] | None = None,
    search_window: dict[str, str] | None = None,
    counts=None,
) -> str:
    """Renderiza el checklist PRISMA-S (16 ítems) pre-rellenando lo que el motor sabe.

    La búsqueda es la etapa más automatizada del pipeline, así que la mayor
    parte de la evidencia sale sola: bases, cadenas versionadas, ventana,
    fechas, totales por base y método de deduplicación.
    """
    auto: dict[int, str] = {}
    if databases:
        auto[1] = f"Bases: {', '.join(databases)} (APIs abiertas; ver docs/integraciones.md)."
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
    lines = [
        "# Checklist PRISMA-S · reporte de la búsqueda (16 ítems)",
        "",
        "> Rethlefsen ML, et al. PRISMA-S. _Syst Rev_ 2021;10:39. "
        "doi:10.1186/s13643-020-01542-z",
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
) -> str:
    """Renderiza el checklist PRISMA 2020 para resúmenes (12 ítems).

    Como el checklist principal, se emite de andamiaje: pre-rellena la
    evidencia que el pipeline conoce (fuentes, ventana, conteos, registro) y
    deja el juicio editorial al humano.
    """
    auto: dict[int, str] = {}
    if databases:
        executed = (search_window or {}).get("executed") or "(sin fecha ejecutada)"
        auto[4] = f"Bases: {', '.join(databases)} · última búsqueda: {executed}."
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


def render_traice_checklist(
    run_metas: Iterable[RunMeta],
    autonomy: dict[str, str],
    *,
    metrics: ScreeningMetrics | None = None,
    exclusions: ExclusionBreakdown | None = None,
    search_window: dict[str, str] | None = None,
) -> str:
    """Renderiza el checklist PRISMA-trAIce a partir de la procedencia real.

    Args:
        run_metas: todos los ``RunMeta`` registrados en la corrida.
        autonomy: nivel de autonomía aplicado por etapa.
        metrics: métricas de cribado frente al gold standard, si se calcularon.
        exclusions: desglose de exclusiones humano vs IA, si se calculó.
        search_window: ventana temporal de la búsqueda declarada en el protocolo.
    """
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
        "- Prompts: versionados en prisma_loop/prompts/ y hash-eados por llamada (RunMeta).",
        "- Validación humana: checkpoints HITL registrados en decisions_ledger.jsonl.",
        "",
        "## Autonomía por etapa",
    ]
    for stage, level in autonomy.items():
        lines.append(f"- {stage}: {level}")
    if metrics is not None:
        lines += [
            "",
            "## Métricas de cribado (vs gold standard humano)",
            f"- Recall (evidencia recuperada): {_fmt(metrics.recall)}",
            f"- Lost-Evidence (evidencia perdida): {_fmt(metrics.lost_evidence)}",
            f"- MCC: {metrics.mcc:.3f} · WMCC (w={metrics.wmcc_fn_weight:g}): {metrics.wmcc:.3f}",
            f"- Cohen's kappa humano-IA: {metrics.cohen_kappa:.3f}",
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
