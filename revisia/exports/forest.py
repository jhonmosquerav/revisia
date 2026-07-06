"""Render del meta-análisis: forest plot Markdown + gráficos PNG opcionales.

El forest Markdown y el resumen numérico son **siempre** deterministas y sin
dependencias. Los gráficos PNG (forest y funnel) se generan solo si ``matplotlib``
está instalado (extra ``meta``); si no, se omiten silenciosamente y el entregable
Markdown sigue completo.

``display="proportion"`` re-transforma el efecto (logit) a **proporción** (0–1)
para mostrar — útil en metaanálisis de proporciones (p. ej. sensibilidad del
cribado), donde el eje en logit es correcto para agregar pero poco intuitivo de
leer. El cálculo (pooling, I², Egger) sigue en la escala del efecto; solo cambia
la presentación.
"""

from __future__ import annotations

import math
from pathlib import Path

from revisia.meta_analysis import MetaAnalysisResult


def _expit(x: float) -> float:
    """Inversa del logit: logit → proporción (0–1)."""
    return 1.0 / (1.0 + math.exp(-x))


def _fmt(value: float, *, log_scale: bool) -> str:
    """Formatea un efecto; si es escala log (logOR) muestra también el exp."""
    if log_scale:
        return f"{value:+.3f} (OR={math.exp(value):.2f})"
    return f"{value:+.3f}"


def render_forest_markdown(result: MetaAnalysisResult, *, display: str = "raw") -> str:
    """Renderiza el forest plot y el resumen del meta-análisis en Markdown.

    Args:
        display: ``"raw"`` (efecto en su escala nativa) o ``"proportion"``
            (re-transforma logit → proporción 0–1 para mostrar; el pooling y la
            heterogeneidad se calculan igual).
    """
    ls = result.log_scale
    prop = display == "proportion"

    def cell(v: float) -> str:
        return f"{_expit(v):.3f}" if prop else _fmt(v, log_scale=ls)

    def ci(lo: float, hi: float) -> str:
        if prop:
            return f"[{_expit(lo):.3f}, {_expit(hi):.3f}]"
        return f"[{lo:+.3f}, {hi:+.3f}]"

    effect_col = "Sensibilidad/Prop." if prop else "Efecto"
    lines = [
        "# Meta-análisis cuantitativo",
        "",
        f"- Medida: **{result.measure}**"
        + (" · presentada como **proporción**" if prop else (" (escala log)" if ls else "")),
        f"- Estudios (k): **{result.k}**",
        "",
        "## Forest plot",
        "",
        f"| Estudio | {effect_col} | IC95% | Peso (aleat.) |",
        "|---|---|---|---|",
    ]
    for s in result.studies:
        label = s.label or s.study_id
        lines.append(
            f"| {label} | {cell(s.yi)} | {ci(s.ci_low, s.ci_high)} | {s.weight_random:.1f}% |"
        )
    fx, rnd = result.fixed, result.random
    fx_c, fx_ci = cell(fx.estimate), ci(fx.ci_low, fx.ci_high)
    rnd_c, rnd_ci = cell(rnd.estimate), ci(rnd.ci_low, rnd.ci_high)
    lines += [
        f"| **Combinado (fijos)** | {fx_c} | {fx_ci} | — |",
        f"| **Combinado (aleatorios)** | {rnd_c} | {rnd_ci} | — |",
    ]
    het = result.heterogeneity
    q_p = "n/d" if het.p_value is None else f"{het.p_value:.4f}"
    lines += [
        "",
        "## Heterogeneidad",
        f"- Q = {het.q:.3f} (df={het.df}, p={q_p} · {het.p_method})",
        f"- I² = {het.i2:.1f}%  ·  τ² = {het.tau2:.4f}",
        "",
        "## Efecto combinado",
    ]
    if prop:
        lines += [
            f"- Fijos: **{_expit(fx.estimate):.3f}** "
            f"(IC95% [{_expit(fx.ci_low):.3f}, {_expit(fx.ci_high):.3f}])",
            f"- Aleatorios: **{_expit(rnd.estimate):.3f}** "
            f"(IC95% [{_expit(rnd.ci_low):.3f}, {_expit(rnd.ci_high):.3f}])"
            f" · logit {rnd.estimate:+.3f}, z={rnd.z:.2f}, p={rnd.p_value:.4f}",
        ]
    else:
        lines += [
            f"- Fijos: {_fmt(fx.estimate, log_scale=ls)} "
            f"(IC95% [{fx.ci_low:+.3f}, {fx.ci_high:+.3f}], z={fx.z:.2f}, p={fx.p_value:.4f})",
            f"- Aleatorios: {_fmt(rnd.estimate, log_scale=ls)} "
            f"(IC95% [{rnd.ci_low:+.3f}, {rnd.ci_high:+.3f}], z={rnd.z:.2f}, p={rnd.p_value:.4f})",
        ]
    if result.egger is not None:
        e = result.egger
        lines += [
            "",
            "## Sesgo de publicación (test de Egger)",
            f"- Intercepto = {e.intercept:.3f} (SE={e.se:.3f}, t={e.t:.2f}, "
            f"p={e.p_value:.4f} · {e.p_method})",
            "- Un intercepto significativamente ≠ 0 sugiere asimetría del funnel.",
        ]
    else:
        lines += [
            "",
            "## Sesgo de publicación",
            "- Test de Egger no calculado (requiere ≥3 estudios).",
        ]
    lines += [
        "",
        "_Síntesis cuantitativa orientativa: el juicio final (modelo, subgrupos, "
        "sensibilidad) es del revisor humano._",
    ]
    return "\n".join(lines)


def render_forest_png(result: MetaAnalysisResult, out_path: Path, *, display: str = "raw") -> bool:
    """Genera el forest plot PNG si matplotlib está disponible.

    Args:
        display: ``"raw"`` o ``"proportion"`` (eje re-transformado a 0–1).

    Returns:
        ``True`` si se escribió el PNG; ``False`` si matplotlib no está instalado.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    prop = display == "proportion"
    t = _expit if prop else (lambda v: v)
    studies = result.studies
    labels = [s.label or s.study_id for s in studies] + ["Aleatorios (combinado)"]
    estimates = [t(s.yi) for s in studies] + [t(result.random.estimate)]
    lows = [t(s.ci_low) for s in studies] + [t(result.random.ci_low)]
    highs = [t(s.ci_high) for s in studies] + [t(result.random.ci_high)]
    ys = list(range(len(labels)))[::-1]

    fig, ax = plt.subplots(figsize=(7.5, 0.42 * len(labels) + 1.6))
    for i, y in enumerate(ys):
        combined = i == len(labels) - 1
        ax.plot([lows[i], highs[i]], [y, y], color="#444", linewidth=1)
        ax.plot(
            estimates[i],
            y,
            "D" if combined else "s",
            color="#b5651d" if combined else "#1f4e79",
            markersize=7 if combined else 5,
        )
    ref = t(0.0)  # nulo (logit 0 → prop 0.5)
    ax.axvline(ref, color="#999", linestyle="--", linewidth=0.8)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=8)
    if prop:
        ax.set_xlabel("Sensibilidad (proporción, 0–1)")
        ax.set_xlim(0, 1)
    else:
        ax.set_xlabel(f"Efecto ({result.measure})")
    ax.set_title("Forest plot" + (" · sensibilidad del cribado" if prop else ""))
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def render_funnel_png(result: MetaAnalysisResult, out_path: Path) -> bool:
    """Genera el funnel plot PNG si matplotlib está disponible.

    El funnel se mantiene en la escala del efecto (logit para proporciones): es
    la convención — la asimetría se evalúa contra el error estándar del efecto.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    effects = [s.yi for s in result.studies]
    ses = [s.se for s in result.studies]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(effects, ses, color="#1f4e79")
    ax.axvline(result.random.estimate, color="#999", linestyle="--", linewidth=0.8)
    ax.invert_yaxis()
    ax.set_xlabel(f"Efecto ({result.measure}, escala logit)")
    ax.set_ylabel("Error estándar")
    ax.set_title("Funnel plot")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True
