"""Funciones de métricas públicas para el auditor (spec 2026-10-04 §9.1, D7)."""

from __future__ import annotations

import math

import pytest

from revisia.metrics import cohen_kappa, confusion, kappa_from_matrix, mcc, wilson_interval


@pytest.mark.parametrize(
    ("pred", "gold"),
    [
        ([True, True, False, False], [True, False, True, False]),
        ([True, True, True, False, False], [True, True, False, False, False]),
        ([True, True, True], [True, False, True]),
    ],
)
def test_kappa_from_matrix_coincide_con_cohen_kappa(pred, gold) -> None:
    assert kappa_from_matrix(*confusion(pred, gold)) == cohen_kappa(pred, gold)


def test_kappa_from_matrix_indefinido_y_no_informativo() -> None:
    assert kappa_from_matrix(0, 0, 0, 0) is None
    assert kappa_from_matrix(5, 0, 0, 0) is None  # pe = 1
    # IA de una sola clase con gold mixto: número (0.0), no None (A11).
    assert kappa_from_matrix(3, 2, 0, 0) == 0.0


def test_kappa_c3_imposible_con_fn_cero() -> None:
    # Auditoría 2026-09-03, C3: con n=47 y FN=0 ninguna matriz da κ=0.75 y MCC=0.71.
    pares = set()
    for tp in range(1, 47):
        for fp in range(0, 47 - tp):
            tn = 47 - tp - fp
            kappa, phi = kappa_from_matrix(tp, fp, 0, tn), mcc(tp, fp, 0, tn)
            if kappa is not None and phi is not None:
                pares.add((round(kappa, 2), round(phi, 2)))
    assert pares and (0.75, 0.71) not in pares


def test_wilson_interval_valores_conocidos() -> None:
    bajo, alto = wilson_interval(33, 34)
    assert math.isclose(bajo, 0.8508, abs_tol=1e-4)
    assert math.isclose(alto, 0.9948, abs_tol=1e-4)
    bajo, alto = wilson_interval(5, 5)
    assert alto == 1.0
    assert math.isclose(bajo, 0.5655, abs_tol=1e-4)
    bajo, alto = wilson_interval(0, 10)
    assert bajo == 0.0 and math.isclose(alto, 0.2775, abs_tol=1e-4)


def test_wilson_interval_sin_datos_y_z_configurable() -> None:
    assert wilson_interval(0, 0) is None
    ancho_95 = wilson_interval(8, 10)
    ancho_99 = wilson_interval(8, 10, z=2.576)
    assert ancho_99[0] < ancho_95[0] and ancho_99[1] > ancho_95[1]
