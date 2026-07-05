"""Meta-análisis cuantitativo (§8.1) · inverse-variance + DerSimonian-Laird.

Implementa lo esencial de una síntesis cuantitativa, en Python puro (sin numpy):
efecto combinado por efectos fijos y aleatorios, heterogeneidad (Q, I², τ²),
intervalos de confianza y test de Egger de asimetría del funnel.

Los *p-valores* usan la normal estándar (``statistics.NormalDist``) como
aproximación; si ``scipy`` está instalado se usan las distribuciones exactas
(χ² para Q, t de Student para Egger). El resultado declara qué método usó.
"""

from __future__ import annotations

import math
from statistics import NormalDist

from pydantic import BaseModel

from revisia.schemas.effects import EffectInput, Measure

_Z = NormalDist()


def _two_sided_p_normal(stat: float) -> float:
    """p-valor bilateral de un estadístico bajo la normal estándar."""
    return 2 * (1 - _Z.cdf(abs(stat)))


def _chi2_sf(x: float, df: int) -> tuple[float | None, str]:
    """Cola superior de χ²; usa scipy si está, si no devuelve ``None``."""
    try:
        from scipy.stats import chi2  # type: ignore

        return float(chi2.sf(x, df)), "scipy"
    except Exception:
        return None, "n/d (instala scipy para el p-valor de Q)"


def _t_sf_two_sided(t: float, df: int) -> tuple[float, str]:
    """p-valor bilateral de una t de Student; cae a la normal si no hay scipy."""
    try:
        from scipy.stats import t as student_t  # type: ignore

        return float(2 * student_t.sf(abs(t), df)), "scipy-t"
    except Exception:
        return _two_sided_p_normal(t), "aprox-normal"


class StudyEffect(BaseModel):
    """Efecto de un estudio con su peso en cada modelo."""

    study_id: str
    label: str | None = None
    yi: float
    vi: float
    se: float
    ci_low: float
    ci_high: float
    weight_fixed: float
    weight_random: float


class PooledEstimate(BaseModel):
    """Estimación combinada (efectos fijos o aleatorios)."""

    model: str
    estimate: float
    se: float
    ci_low: float
    ci_high: float
    z: float
    p_value: float


class Heterogeneity(BaseModel):
    """Estadísticos de heterogeneidad entre estudios."""

    q: float
    df: int
    i2: float
    tau2: float
    p_value: float | None = None
    p_method: str = ""


class EggerTest(BaseModel):
    """Test de Egger de asimetría del funnel (sesgo de publicación)."""

    intercept: float
    se: float
    t: float
    p_value: float
    p_method: str


class MetaAnalysisResult(BaseModel):
    """Resultado completo del meta-análisis."""

    k: int
    measure: str
    log_scale: bool
    studies: list[StudyEffect]
    fixed: PooledEstimate
    random: PooledEstimate
    heterogeneity: Heterogeneity
    egger: EggerTest | None = None


def _pool(yi: list[float], wi: list[float], model: str) -> PooledEstimate:
    sw = sum(wi)
    est = sum(w * y for w, y in zip(wi, yi, strict=True)) / sw
    se = math.sqrt(1 / sw)
    z = est / se if se else 0.0
    return PooledEstimate(
        model=model,
        estimate=est,
        se=se,
        ci_low=est - 1.96 * se,
        ci_high=est + 1.96 * se,
        z=z,
        p_value=_two_sided_p_normal(z),
    )


def _egger(yi: list[float], vi: list[float]) -> EggerTest | None:
    """Regresión de Egger: SND = a + b·precisión; el intercepto ``a`` mide sesgo."""
    k = len(yi)
    if k < 3:  # el test no es interpretable con <3 estudios
        return None
    se_i = [math.sqrt(v) for v in vi]
    x = [1 / s for s in se_i]  # precisión
    y = [yi[i] / se_i[i] for i in range(k)]  # standard normal deviate
    mx = sum(x) / k
    my = sum(y) / k
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx == 0:
        return None
    slope = sum((x[i] - mx) * (y[i] - my) for i in range(k)) / sxx
    intercept = my - slope * mx
    # Error residual y SE del intercepto (regresión OLS simple).
    resid = [y[i] - (intercept + slope * x[i]) for i in range(k)]
    s2 = sum(r**2 for r in resid) / (k - 2)
    se_intercept = math.sqrt(s2 * (1 / k + mx**2 / sxx))
    t = intercept / se_intercept if se_intercept else 0.0
    p, method = _t_sf_two_sided(t, k - 2)
    return EggerTest(intercept=intercept, se=se_intercept, t=t, p_value=p, p_method=method)


def meta_analyze(effects: list[EffectInput], measure: Measure) -> MetaAnalysisResult:
    """Ejecuta el meta-análisis sobre una lista de efectos.

    Args:
        effects: efectos por estudio (crudos o precomputados).
        measure: ``precomputed`` | ``logOR`` | ``MD`` | ``SMD``.

    Raises:
        ValueError: si hay menos de 2 estudios o faltan datos.
    """
    if len(effects) < 2:
        raise ValueError("El meta-análisis requiere al menos 2 estudios.")
    yi: list[float] = []
    vi: list[float] = []
    labels: list[tuple[str, str | None]] = []
    for eff in effects:
        y, v = eff.to_yi_vi(measure)
        if v <= 0:
            raise ValueError(f"{eff.study_id}: varianza no positiva ({v}).")
        yi.append(y)
        vi.append(v)
        labels.append((eff.study_id, eff.label))

    k = len(yi)
    w_fixed = [1 / v for v in vi]

    # Heterogeneidad (Q, τ² por DerSimonian-Laird, I²).
    sw = sum(w_fixed)
    mean_fixed = sum(w * y for w, y in zip(w_fixed, yi, strict=True)) / sw
    q = sum(w * (y - mean_fixed) ** 2 for w, y in zip(w_fixed, yi, strict=True))
    df = k - 1
    c = sw - sum(w**2 for w in w_fixed) / sw
    tau2 = max(0.0, (q - df) / c) if c > 0 else 0.0
    i2 = max(0.0, (q - df) / q) * 100 if q > 0 else 0.0
    q_p, q_method = _chi2_sf(q, df)

    w_random = [1 / (v + tau2) for v in vi]

    fixed = _pool(yi, w_fixed, "fixed")
    random = _pool(yi, w_random, "random")

    studies = [
        StudyEffect(
            study_id=labels[i][0],
            label=labels[i][1],
            yi=yi[i],
            vi=vi[i],
            se=math.sqrt(vi[i]),
            ci_low=yi[i] - 1.96 * math.sqrt(vi[i]),
            ci_high=yi[i] + 1.96 * math.sqrt(vi[i]),
            weight_fixed=w_fixed[i] / sw * 100,
            weight_random=w_random[i] / sum(w_random) * 100,
        )
        for i in range(k)
    ]

    return MetaAnalysisResult(
        k=k,
        measure=measure,
        log_scale=(measure == "logOR"),
        studies=studies,
        fixed=fixed,
        random=random,
        heterogeneity=Heterogeneity(q=q, df=df, i2=i2, tau2=tau2, p_value=q_p, p_method=q_method),
        egger=_egger(yi, vi),
    )
