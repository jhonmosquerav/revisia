"""Generador de ``metodologia.md`` · sección de métodos del entregable (§11).

Rinde la plantilla de métodos del documento canónico rellenándola con los datos
reales de la corrida (pregunta, bases, ventana, screening + kappa, extracción +
acuerdo, RoB, síntesis, uso de IA y exclusiones humano/IA). Las limitaciones y
sesgos quedan como andamiaje para que el revisor humano los complete. Determinista.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prisma_loop.config import ReviewProtocol
    from prisma_loop.exclusions import ExclusionBreakdown
    from prisma_loop.exports.prisma_flow import PrismaCounts
    from prisma_loop.extraction_agreement import ExtractionAgreement
    from prisma_loop.metrics import ScreeningMetrics


def _registration_line(registration: dict[str, str]) -> str:
    if not registration:
        return "No preregistrado (declarar PROSPERO/OSF si aplica)."
    return ", ".join(f"{k.upper()}: {v}" for k, v in registration.items() if v) or "(declarado)"


def _window_line(window: dict[str, str]) -> str:
    if not window:
        return "(no declarada)"
    parts = [f"{k}: {v}" for k, v in window.items() if v]
    return " · ".join(parts) or "(no declarada)"


def render_methods(
    *,
    protocol: ReviewProtocol,
    counts: PrismaCounts,
    metrics: ScreeningMetrics | None = None,
    models: list[str] | None = None,
    quantitative: bool = False,
    exclusions: ExclusionBreakdown | None = None,
    extraction_agreement: ExtractionAgreement | None = None,
) -> str:
    """Renderiza la sección de métodos (``metodologia.md``) de la revisión."""
    q = protocol.question
    components = "; ".join(f"{k}={v}" for k, v in q.components.items()) or "(no detallados)"
    bases = ", ".join(protocol.databases) or "OpenAlex"
    kappa = (
        f"Cohen's kappa humano-IA = {metrics.cohen_kappa:.3f}"
        if metrics is not None
        else "no calculado (sin gold standard)"
    )
    sintesis = (
        "cuantitativa (meta-análisis) + narrativa (SWiM)"
        if quantitative
        else "narrativa siguiendo SWiM (Synthesis Without Meta-analysis)"
    )
    ia_models = ", ".join(models or []) or "(ninguno registrado)"

    lines = [
        "## Método",
        "",
        f"Tipo: revisión sistemática {protocol.prisma_extension} + PRISMA-trAIce (uso de IA).",
        f"Registro: {_registration_line(protocol.registration)}",
        f"Pregunta ({q.framework}): {q.text}",
        f"Componentes: {components}",
        f"Bases consultadas: {bases}",
        f"Ventana de búsqueda: {_window_line(protocol.search_window)}",
        "Cadenas de búsqueda: ver protocols/<slug>/search_strings/ (PRISMA-S).",
        "Criterios: ver inclusion_exclusion.yml (declarados antes de ver resultados).",
        "",
        "### Selección (screening)",
        f"Dos fases (título/abstract y texto completo) con ensemble multi-modelo "
        f"sesgado a recall y checkpoint humano (HITL). Acuerdo: {kappa}.",
        f"Flujo PRISMA: identificados={counts.identified} · duplicados={counts.duplicates_removed} "
        f"· cribados={counts.screened} · texto completo={counts.fulltext_assessed} "
        f"· incluidos={counts.included}.",
    ]

    if exclusions is not None:
        lines.append(
            f"Exclusiones por origen: IA={exclusions.excluded_ai} · "
            f"humano={exclusions.excluded_human} "
            f"· rescatados por humano={exclusions.overridden_to_include} "
            f"· cortados por humano={exclusions.overridden_to_exclude}."
        )

    lines += [
        "",
        "### Extracción",
        "Formulario configurable (extraction_form.yml) con cita textual de origen por "
        "campo (anti-alucinación); autonomía A0 (revisión humana campo a campo).",
    ]
    if extraction_agreement is not None and extraction_agreement.n_studies:
        ea = extraction_agreement
        agr = "n/d" if ea.value_agreement is None else f"{ea.value_agreement:.2%}"
        lines.append(
            f"Doble extracción independiente en {ea.n_studies} estudios "
            f"({ea.n_field_pairs} pares de campo): acuerdo de valor={agr}, "
            f"kappa de presencia={ea.presence_kappa:.3f}."
        )

    lines += [
        "",
        "### Evaluación de calidad",
        f"Herramienta: {protocol.rob_tool}. No excluye estudios automáticamente; "
        "pondera su peso en la síntesis. Juicio final humano (A0).",
        "",
        "### Síntesis",
        f"Tipo: {sintesis}.",
        "",
        "### Uso de IA (PRISMA-trAIce)",
        f"Modelos: {ia_models}. Parámetros (temperatura/top_p/seed) y hash de prompt "
        "registrados por llamada en manifest.yml. Validación humana: checkpoints HITL "
        "en cada etapa; la decisión final es siempre humana.",
        "",
        "## Limitaciones",
        "- [ ] (completar: cobertura de bases, idioma, ventana temporal)",
        "- [ ] (completar: dependencia de disponibilidad de texto completo OA)",
        "",
        "## Sesgos potenciales",
        "- Sesgo de publicación: [evaluado con funnel/Egger si hubo meta-análisis]",
        "- Sesgo de idioma: [declarar idiomas incluidos]",
        "- Sesgo geográfico: [declarar concentración regional]",
    ]
    return "\n".join(lines)
