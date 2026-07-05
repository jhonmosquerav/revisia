"""Métricas de screening · correctas para datos desbalanceados.

Lección dura del estado del arte: con datos desbalanceados (la inmensa mayoría
de registros son irrelevantes) la *accuracy* es engañosa — el modelo "mejor en
accuracy" puede perder >60% de la evidencia relevante. Por eso este módulo
**no expone accuracy** y prioriza:

- **Recall / Lost-Evidence**: ¿qué fracción de la evidencia relevante recupera
  (o pierde) el cribado? Es la métrica que importa en una revisión sistemática.
- **MCC**: coeficiente de correlación de Matthews, robusto al desbalance.
- **WMCC**: MCC con el falso negativo ponderado (coste FN ≫ FP, w=10 por
  defecto). Variante pragmática que penaliza perder evidencia.
- **Cohen's kappa**: acuerdo humano-IA (umbral ≥0.60 del documento canónico).

Todas se calculan contra un *gold standard* humano (subconjunto etiquetado).
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from revisia.schemas.screening import ScreeningDecision


class ScreeningMetrics(BaseModel):
    """Métricas del cribado frente a un gold standard humano."""

    n: int
    tp: int
    fp: int
    fn: int
    tn: int
    recall: float | None = None
    lost_evidence: float | None = None
    precision: float | None = None
    mcc: float = 0.0
    wmcc: float = 0.0
    wmcc_fn_weight: float = 10.0
    cohen_kappa: float = 0.0


def confusion(pred: list[bool], gold: list[bool]) -> tuple[int, int, int, int]:
    """Matriz de confusión (tp, fp, fn, tn) tratando ``True`` como "relevante"."""
    if len(pred) != len(gold):
        raise ValueError("pred y gold deben tener la misma longitud.")
    tp = sum(1 for p, g in zip(pred, gold, strict=True) if p and g)
    fp = sum(1 for p, g in zip(pred, gold, strict=True) if p and not g)
    fn = sum(1 for p, g in zip(pred, gold, strict=True) if not p and g)
    tn = sum(1 for p, g in zip(pred, gold, strict=True) if not p and not g)
    return tp, fp, fn, tn


def _safe_ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def mcc(tp: int, fp: int, fn: int, tn: int) -> float:
    """Coeficiente de correlación de Matthews (0.0 si el denominador es 0)."""
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return ((tp * tn) - (fp * fn)) / denom if denom else 0.0


def wmcc(tp: int, fp: int, fn: int, tn: int, *, fn_weight: float = 10.0) -> float:
    """MCC con el falso negativo ponderado por ``fn_weight`` (coste FN ≫ FP).

    Variante pragmática (no estandarizada): se reemplaza ``fn`` por
    ``fn_weight * fn`` para penalizar perder evidencia relevante.
    """
    fnw = fn_weight * fn
    denom = math.sqrt((tp + fp) * (tp + fnw) * (tn + fp) * (tn + fnw))
    return ((tp * tn) - (fp * fnw)) / denom if denom else 0.0


def cohen_kappa(pred: list[bool], gold: list[bool]) -> float:
    """Cohen's kappa entre dos clasificaciones binarias (0.0 si indefinido)."""
    tp, fp, fn, tn = confusion(pred, gold)
    n = tp + fp + fn + tn
    if n == 0:
        return 0.0
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    return (po - pe) / (1 - pe) if (1 - pe) else 0.0


def compute_screening_metrics(
    decisions: list[ScreeningDecision],
    gold: dict[str, bool],
    *,
    fn_weight: float = 10.0,
) -> ScreeningMetrics:
    """Calcula las métricas del cribado sobre los registros con etiqueta humana.

    Args:
        decisions: decisiones del cribado (se usa ``final_label``/``ensemble_label``).
        gold: ``{record_id: es_relevante}`` (gold standard humano).
        fn_weight: peso del falso negativo para WMCC.

    Un registro se considera "pasado" (predicho relevante) si su etiqueta NO es
    "exclude" (include o unclear pasan a la siguiente fase: sesgo a recall).
    """
    by_id = {d.record_id: d for d in decisions}
    pred: list[bool] = []
    gold_bools: list[bool] = []
    for record_id, is_relevant in gold.items():
        decision = by_id.get(record_id)
        if decision is None:
            continue
        label = decision.final_label or decision.ensemble_label
        pred.append(label != "exclude")
        gold_bools.append(bool(is_relevant))

    tp, fp, fn, tn = confusion(pred, gold_bools)
    return ScreeningMetrics(
        n=len(pred),
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        recall=_safe_ratio(tp, tp + fn),
        lost_evidence=_safe_ratio(fn, tp + fn),
        precision=_safe_ratio(tp, tp + fp),
        mcc=mcc(tp, fp, fn, tn),
        wmcc=wmcc(tp, fp, fn, tn, fn_weight=fn_weight),
        wmcc_fn_weight=fn_weight,
        cohen_kappa=cohen_kappa(pred, gold_bools),
    )
