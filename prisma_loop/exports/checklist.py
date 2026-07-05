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
