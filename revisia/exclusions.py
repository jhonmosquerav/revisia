"""Desglose de exclusiones por origen (humano vs IA) · requisito PRISMA-trAIce.

PRISMA-trAIce (§10 del documento canónico) exige reportar **cuántos estudios
excluyó el humano frente a cuántos la IA**. Este módulo lo computa de forma
determinista a partir de las decisiones de screening, distinguiendo además los
casos en que el humano sobrescribió a la IA (rescate o corte), que son la
evidencia de que la decisión final fue humana.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from revisia.schemas.screening import ScreeningDecision


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
