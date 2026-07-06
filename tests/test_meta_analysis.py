"""Tests del meta-análisis cuantitativo (valores contra cálculo a mano)."""

from __future__ import annotations

import math

import pytest

from revisia.exports.forest import render_forest_markdown
from revisia.meta_analysis import meta_analyze
from revisia.schemas.effects import EffectInput


def test_forest_markdown_display_proportion() -> None:
    # logit 0 → proporción 0.5; logit 2.197 → ≈0.900.
    effects = [
        EffectInput(study_id="a", yi=0.0, vi=0.1),
        EffectInput(study_id="b", yi=2.197, vi=0.1),
    ]
    res = meta_analyze(effects, "precomputed")
    md = render_forest_markdown(res, display="proportion")
    assert "Sensibilidad/Prop." in md
    assert "0.500" in md  # expit(0)
    assert "0.900" in md  # expit(2.197)
    # Modo raw sigue mostrando el logit (efecto), no la proporción.
    raw = render_forest_markdown(res, display="raw")
    assert "Efecto" in raw
    assert "+2.197" in raw


def test_fixed_effect_pooled_estimate() -> None:
    # Dos estudios con se=0.2 → vi=0.04, wi=25; pooled=(0.2+0.4)/2=0.3.
    effects = [
        EffectInput(study_id="a", yi=0.2, vi=0.04),
        EffectInput(study_id="b", yi=0.4, vi=0.04),
    ]
    res = meta_analyze(effects, "precomputed")
    assert res.k == 2
    assert res.fixed.estimate == pytest.approx(0.3, abs=1e-9)
    assert res.fixed.se == pytest.approx(math.sqrt(1 / 50), abs=1e-9)
    # Homogéneos → sin heterogeneidad y random == fixed.
    assert res.heterogeneity.i2 == pytest.approx(0.0, abs=1e-9)
    assert res.heterogeneity.tau2 == pytest.approx(0.0, abs=1e-9)
    assert res.random.estimate == pytest.approx(res.fixed.estimate, abs=1e-9)


def test_weights_suman_100() -> None:
    effects = [
        EffectInput(study_id="a", yi=0.2, vi=0.04),
        EffectInput(study_id="b", yi=0.4, vi=0.01),
    ]
    res = meta_analyze(effects, "precomputed")
    assert sum(s.weight_fixed for s in res.studies) == pytest.approx(100.0, abs=1e-6)
    assert sum(s.weight_random for s in res.studies) == pytest.approx(100.0, abs=1e-6)


def test_log_or_desde_2x2() -> None:
    # e1=10/n1=100, e0=20/n0=100 con corrección 0.5.
    eff = EffectInput(study_id="x", e1=10, n1=100, e0=20, n0=100)
    yi, vi = eff.to_yi_vi("logOR")
    assert yi == pytest.approx(-0.786, abs=1e-2)
    assert vi == pytest.approx(0.1675, abs=1e-3)


def test_mean_difference() -> None:
    eff = EffectInput(study_id="x", m1=10, sd1=2, cn1=50, m0=8, sd0=2, cn0=50)
    yi, vi = eff.to_yi_vi("MD")
    assert yi == pytest.approx(2.0, abs=1e-9)
    assert vi == pytest.approx(0.16, abs=1e-9)


def test_smd_hedges_g_aplica_correccion() -> None:
    eff = EffectInput(study_id="x", m1=10, sd1=2, cn1=50, m0=8, sd0=2, cn0=50)
    yi, _ = eff.to_yi_vi("SMD")
    # d = 2/2 = 1; J<1 reduce un poco → g algo menor que 1.
    assert 0.9 < yi < 1.0


def test_egger_requiere_tres_estudios() -> None:
    dos = meta_analyze(
        [EffectInput(study_id="a", yi=0.2, vi=0.04), EffectInput(study_id="b", yi=0.4, vi=0.04)],
        "precomputed",
    )
    assert dos.egger is None
    tres = meta_analyze(
        [
            EffectInput(study_id="a", yi=0.2, vi=0.04),
            EffectInput(study_id="b", yi=0.4, vi=0.02),
            EffectInput(study_id="c", yi=0.6, vi=0.01),
        ],
        "precomputed",
    )
    assert tres.egger is not None
    assert math.isfinite(tres.egger.intercept)
    assert math.isfinite(tres.egger.p_value)


def test_menos_de_dos_estudios_falla() -> None:
    with pytest.raises(ValueError, match="al menos 2"):
        meta_analyze([EffectInput(study_id="a", yi=0.2, vi=0.04)], "precomputed")


def test_varianza_no_positiva_falla() -> None:
    with pytest.raises(ValueError, match="varianza"):
        meta_analyze(
            [EffectInput(study_id="a", yi=0.2, vi=0.0), EffectInput(study_id="b", yi=0.4, vi=0.04)],
            "precomputed",
        )
