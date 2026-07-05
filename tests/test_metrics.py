"""Tests de las métricas de screening (valores conocidos)."""

from __future__ import annotations

import math

from prisma_loop.metrics import (
    cohen_kappa,
    compute_screening_metrics,
    confusion,
    mcc,
    wmcc,
)
from prisma_loop.schemas.screening import ScreeningDecision


def test_confusion_y_recall() -> None:
    pred = [True, True, False, False]
    gold = [True, False, True, False]
    tp, fp, fn, tn = confusion(pred, gold)
    assert (tp, fp, fn, tn) == (1, 1, 1, 1)
    assert tp / (tp + fn) == 0.5  # recall


def test_recall_perfecto() -> None:
    pred = [True, True, True, False]
    gold = [True, True, False, False]
    tp, fp, fn, tn = confusion(pred, gold)
    assert fn == 0  # ninguna evidencia perdida
    assert tp / (tp + fn) == 1.0


def test_mcc_cero_cuando_no_hay_correlacion() -> None:
    assert mcc(1, 1, 1, 1) == 0.0


def test_wmcc_penaliza_falsos_negativos() -> None:
    # Con FN presente, el WMCC (w=10) es más severo (más negativo) que el MCC.
    base = mcc(1, 1, 1, 1)
    weighted = wmcc(1, 1, 1, 1, fn_weight=10)
    assert weighted < base
    assert math.isclose(weighted, -9 / 22, rel_tol=1e-6)


def test_cohen_kappa_acuerdo_perfecto() -> None:
    pred = [True, False, True, False]
    gold = [True, False, True, False]
    assert cohen_kappa(pred, gold) == 1.0


def test_compute_screening_metrics_usa_ensemble_label() -> None:
    decisions = [
        ScreeningDecision(record_id="a", ensemble_label="include"),
        ScreeningDecision(record_id="b", ensemble_label="exclude"),
        ScreeningDecision(record_id="c", ensemble_label="include"),
        ScreeningDecision(record_id="d", ensemble_label="unclear"),
    ]
    gold = {"a": True, "b": True, "c": False, "d": True}
    m = compute_screening_metrics(decisions, gold)
    # pred: a=T(incluir), b=F(excluir), c=T, d=T(unclear pasa) → sesgo a recall
    # gold: a=T, b=T, c=F, d=T
    assert (m.tp, m.fp, m.fn, m.tn) == (2, 1, 1, 0)
    assert m.recall == 2 / 3
    assert m.lost_evidence == 1 / 3
    assert m.n == 4
