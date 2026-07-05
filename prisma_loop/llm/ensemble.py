"""Agregación de votos de un ensemble multi-modelo para screening.

Regla de voto **sesgada a recall**: en una revisión sistemática el error caro
es el falso negativo (perder un estudio relevante), no el falso positivo. Por
eso un registro pasa si *cualquier* modelo lo incluye; solo se excluye cuando
hay consenso de exclusión. Es la estrategia que el estado del arte asocia a
recall ~100% en ensembles de LLM. La decisión final sigue siendo humana.
"""

from __future__ import annotations

from collections.abc import Iterable

from prisma_loop.schemas.screening import ScreeningLabel


def recall_biased_label(labels: Iterable[ScreeningLabel]) -> ScreeningLabel:
    """Combina etiquetas de varios modelos priorizando el recall.

    - "include" si algún modelo incluye.
    - si no, "unclear" si algún modelo duda.
    - "exclude" solo si todos excluyen.
    - sin votos → "unclear" (conservador).
    """
    labels = list(labels)
    if not labels:
        return "unclear"
    if any(label == "include" for label in labels):
        return "include"
    if any(label == "unclear" for label in labels):
        return "unclear"
    return "exclude"
