"""Desglose de exclusiones por origen (humano vs IA) · requisito PRISMA-trAIce.

PRISMA-trAIce (§10 del documento canónico) exige reportar **cuántos estudios
excluyó el humano frente a cuántos la IA**. Este módulo lo computa de forma
determinista a partir de las decisiones de screening, distinguiendo además los
casos en que el humano sobrescribió a la IA (rescate o corte), que son la
evidencia de que la decisión final fue humana.

También construye la lista 16b de informes excluidos a texto completo con su
razón y su origen (``compute_ft_excluded``, PRISMA 2020), de la que se deriva
el desglose de razones del diagrama de flujo.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from revisia.schemas.artifacts import ExcludedReport
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision

# Razón cuando ni el humano ni la IA nombraron un criterio.
RAZON_NO_ESPECIFICADA = "criterio no especificado"


class ExclusionBreakdown(BaseModel):
    """Conteo de exclusiones por origen de la decisión.

    Attributes:
        total_excluded: total de registros con ``final_label == "exclude"``.
        excluded_ai: la IA propuso excluir y el humano no lo rescató.
        excluded_human: el humano excluyó explícitamente (``human_label``).
        overridden_to_include: la IA excluyó pero el humano rescató (incluyó).
        overridden_to_exclude: la IA no excluyó pero el humano cortó (excluyó).
    """

    total_excluded: int = 0
    excluded_ai: int = 0
    excluded_human: int = 0
    overridden_to_include: int = 0
    overridden_to_exclude: int = 0


def compute_exclusion_breakdown(
    decisions: Iterable[ScreeningDecision],
) -> ExclusionBreakdown:
    """Desglosa las exclusiones de un conjunto de decisiones de screening."""
    breakdown = ExclusionBreakdown()
    for decision in decisions:
        ai = decision.ensemble_label
        human = decision.human_label
        final = decision.final_label or human or ai

        # Rescates / cortes del humano (el humano cambió la propuesta de la IA).
        if ai == "exclude" and human == "include":
            breakdown.overridden_to_include += 1
        if ai in {"include", "unclear"} and human == "exclude":
            breakdown.overridden_to_exclude += 1

        if final != "exclude":
            continue
        breakdown.total_excluded += 1
        # Atribución del origen de la exclusión efectiva.
        if human == "exclude":
            breakdown.excluded_human += 1
        else:  # la IA propuso excluir y el humano no lo rescató
            breakdown.excluded_ai += 1
    return breakdown


def compute_ft_excluded(
    decisions: Iterable[ScreeningDecision], records: Iterable[SearchRecord]
) -> list[ExcludedReport]:
    """Informes excluidos en elegibilidad con su razón y su origen (PRISMA 2020, 16b).

    La razón es la humana si el humano excluyó (``human_label == "exclude"``,
    con su ``human_reason``); si no, el primer ``criteria_violated`` no vacío de
    la IA (recortado: un LLM puede devolver ``""`` o ``"  "``, que no es razón)
    o "criterio no especificado". ``reason_source`` lo dice explícitamente
    (PRISMA-trAIce R1): ``ft_exclusion_reasons`` se deriva de esta lista para
    que el diagrama, la tabla 16b y el auditor cuenten lo mismo.
    """
    by_id = {r.record_id: r for r in records}
    reports: list[ExcludedReport] = []
    for decision in decisions:
        final = decision.final_label or decision.human_label or decision.ensemble_label
        if final != "exclude":
            continue
        if decision.human_label == "exclude":
            reason = (decision.human_reason or "").strip() or RAZON_NO_ESPECIFICADA
            source = "human"
        else:
            violated = [
                c.strip() for v in decision.votes for c in v.criteria_violated if c and c.strip()
            ]
            reason = violated[0] if violated else RAZON_NO_ESPECIFICADA
            source = "ai"
        record = by_id.get(decision.record_id)
        reports.append(
            ExcludedReport(
                record_id=decision.record_id,
                title=record.title if record is not None else decision.record_id,
                year=record.year if record is not None else None,
                doi=record.doi if record is not None else None,
                reason=reason,
                reason_source=source,
            )
        )
    return reports
