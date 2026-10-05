"""Generador de ``metodologia.md`` · sección de métodos del entregable (§11).

Rinde la plantilla de métodos del documento canónico rellenándola con los datos
reales de la corrida (pregunta, bases, ventana, screening + kappa, extracción +
acuerdo, RoB, síntesis, uso de IA y exclusiones humano/IA). Las limitaciones y
sesgos quedan como andamiaje para que el revisor humano los complete. Determinista.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from revisia.exports.checklist import (
    describe_gate,
    engine_search_date,
    human_validation_summary,
    label_databases,
)
from revisia.metrics import fmt_metric
from revisia.orchestration.hitl import effective_autonomy

if TYPE_CHECKING:
    from revisia.config import ReviewProtocol
    from revisia.exclusions import ExclusionBreakdown
    from revisia.exports.prisma_flow import PrismaCounts
    from revisia.extraction_agreement import ExtractionAgreement
    from revisia.metrics import ScreeningMetrics
    from revisia.schemas.artifacts import GateSummary, SearchLog


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
    search_log: SearchLog | None = None,
    gates: Mapping[str, GateSummary] | None = None,
    autonomy_effective: Mapping[str, str] | None = None,
    forced_human: bool = False,
) -> str:
    """Renderiza la sección de métodos (``metodologia.md``) de la revisión.

    Con ``search_log`` (Ola 1) la fecha de búsqueda es la registrada por el
    motor, se dice en qué bases se usó la pregunta como cadena (PRISMA-S 8) y las
    bases cuya búsqueda falló se marcan en «Bases consultadas».
    Quién decidió cada fase sale de ``gates`` (``summarize_gates`` del ledger) y
    de la autonomía efectiva, no de un texto fijo: si un gate de juicio no lo
    resolvió un humano, el método lo dice (M13). Sin ``gates`` no se afirma
    ninguna decisión: cada fase figura pendiente. Es la sección que se pega en un
    manuscrito: cada frase tiene que ser cierta, sin imperativos ni paréntesis
    dobles, y no atribuye a la IA lo que no hizo (revisión de la Tarea 27).
    """
    gates = gates or {}
    autonomy = dict(autonomy_effective or {})

    def decision(stage: str) -> str:
        level = autonomy.get(stage) or protocol.autonomy_for(stage)
        if stage == "reporte":
            # Sin `autonomy_effective` (o con una inconsistente), el gate final forzado por
            # citas marcadas no se aplica en la declarada (A2 «exige decisión humana» se
            # contradice): la regla es la misma que aplica el gate (`effective_autonomy`).
            level = effective_autonomy(level, forced_human=forced_human)
        return describe_gate(stage, gates.get(stage), autonomy=level, inline_autonomy=True)

    q = protocol.question
    components = "; ".join(f"{k}={v}" for k, v in q.components.items()) or "(no detallados)"
    # Con log, una base que falló se marca: «consultada» sería falso (revisión de la pista C).
    bases = ", ".join(label_databases(protocol.databases or ["OpenAlex"], search_log))
    # Se mide la propuesta del ensemble, no la decisión final con las correcciones humanas
    # (D6; revisión de la Tarea 23): «humano-IA» daba a entender lo segundo.
    kappa = (
        f"Cohen's kappa de la propuesta de la IA frente al gold humano = "
        f"{fmt_metric(metrics.cohen_kappa)} (se mide la propuesta del ensemble, no la decisión "
        "final con las correcciones humanas)"
        if metrics is not None
        else "no calculado (sin gold standard)"
    )
    sintesis = (
        "cuantitativa (meta-análisis) + narrativa (SWiM)"
        if quantitative
        else "narrativa siguiendo SWiM (Synthesis Without Meta-analysis)"
    )
    ia_models = ", ".join(models or []) or "(ninguno registrado)"
    # El ensemble es solo de título/abstract y solo si el protocolo lo declara: el cribado a
    # texto completo pasa un único miembro (`_fulltext`).
    n_ta = protocol.n_screeners_for("screening_ta")
    cribado_ta = (
        f"ensemble multi-modelo sesgado a recall ({n_ta} modelos)"
        if n_ta > 1
        else "un solo modelo (sin ensemble)"
    )

    lines = [
        "## Método",
        "",
        f"Tipo: revisión sistemática {protocol.prisma_extension} + PRISMA-trAIce (uso de IA).",
        f"Registro: {_registration_line(protocol.registration)}",
        f"Pregunta ({q.framework}): {q.text}",
        f"Componentes: {components}",
        f"Bases consultadas: {bases}",
        f"Ventana de búsqueda: {_window_line(protocol.search_window)}",
    ]
    # Sin log no se sabe qué se usó y se conserva la cita; con log solo si alguna base
    # leyó su cadena de search_strings/ (una búsqueda inyectada no usa cadenas por base).
    if search_log is None or any(e.query_origin == "file" for e in search_log.entries):
        lines.append(
            "Cadenas de búsqueda: 00_protocol/search_strings/ de la corrida (copia congelada "
            "del protocolo; PRISMA-S)."
        )
    lines.append("Criterios: ver inclusion_exclusion.yml (declarados antes de ver resultados).")
    if search_log is not None:
        lines.append(
            f"Búsqueda ejecutada (fecha registrada por el motor): {engine_search_date(search_log)}."
        )
        fallback = [e.database for e in search_log.entries if e.query_origin == "question_fallback"]
        if fallback:
            lines.append(
                f"Sin cadena propia en {', '.join(fallback)}: se usó la pregunta como cadena."
            )
    lines += [
        "",
        "### Selección (screening)",
        f"Dos fases (título/abstract y texto completo): {cribado_ta} en título/abstract y un "
        f"solo modelo en texto completo. Título/abstract: {decision('screening_ta')}. Texto "
        f"completo: {decision('screening_ft')}. Acuerdo: {kappa}.",
        f"Flujo PRISMA: identificados={counts.identified} · duplicados={counts.duplicates_removed} "
        f"· cribados={counts.screened} · buscados a texto completo={counts.fulltext_sought} "
        f"· no recuperados={counts.fulltext_not_retrieved} "
        f"· evaluados para elegibilidad={counts.fulltext_assessed} "
        f"· incluidos={counts.included}. Un informe sin texto completo no se evalúa "
        "(PRISMA 2020: cuenta como no recuperado).",
    ]
    if counts.fulltext_rescued:
        # Revisión de la Tarea 24: un rescate cuenta como evaluado, pero la IA no vio ese texto.
        # Solo se nombran RoB y verificación, que sí usan el texto completo cuando existe: la
        # extracción usa título y abstract para todos y se declara en «### Extracción».
        lines.append(
            f"Informes rescatados por el revisor: {counts.fulltext_rescued} que el motor no "
            "recuperó y un humano evaluó con el texto completo obtenido fuera de él (cuentan "
            "como evaluados, no como no recuperados). Limitación: la IA no tuvo ese texto, así "
            "que el riesgo de sesgo y la verificación de las citas de los que se incluyeron se "
            "hicieron solo con título/abstract."
        )

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
        "Formulario configurable (extraction_form.yml). La IA extrae a partir del título y el "
        "abstract; el texto completo no entra en la extracción (limitación conocida). Se "
        "solicita al modelo una cita textual de origen por campo y se registra junto al "
        "valor; no se verifica automáticamente contra el texto. La tabla de extracción se "
        f"aprueba por etapa: {decision('extraccion')}.",
    ]
    if extraction_agreement is not None and extraction_agreement.n_studies:
        ea = extraction_agreement
        agr = "n/d" if ea.value_agreement is None else f"{ea.value_agreement:.2%}"
        lines.append(
            f"Doble extracción independiente en {ea.n_studies} estudios "
            f"({ea.n_field_pairs} pares de campo): acuerdo de valor={agr}, "
            f"kappa de presencia={fmt_metric(ea.presence_kappa)}."
        )

    lines += [
        "",
        "### Evaluación de calidad",
        f"Herramienta: {protocol.rob_tool}. No excluye estudios automáticamente; "
        f"pondera su peso en la síntesis. Decisión: {decision('rob')}.",
        "",
        "### Síntesis",
        f"Tipo: {sintesis}.",
        "",
        "### Uso de IA (PRISMA-trAIce)",
        f"Modelos: {ia_models}. Parámetros (temperatura/top_p/seed) y hash de prompt "
        "registrados por llamada en manifest.yml. Validación humana: "
        f"{human_validation_summary(gates)} Reporte final: {decision('reporte')}"
        + (" — exige decisión humana: el verificador marcó citas." if forced_human else "."),
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
