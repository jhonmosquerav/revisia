"""Render del meta-análisis: forest plot Markdown + gráficos PNG opcionales.

El forest Markdown y el resumen numérico son **siempre** deterministas y sin
dependencias. Los gráficos PNG (forest y funnel) se generan solo si ``matplotlib``
está instalado (extra ``meta``); si no, se omiten silenciosamente y el entregable
Markdown sigue completo.
"""

from __future__ import annotations

import math
from pathlib import Path

from prisma_loop.meta_analysis import MetaAnalysisResult


def _fmt(value: float, *, log_scale: bool) -> str:
    """Formatea un efecto; si es escala log (logOR) muestra también el exp."""
    if log_scale:
        return f"{value:+.3f} (OR={math.exp(value):.2f})"
    return f"{value:+.3f}"


def render_forest_markdown(result: MetaAnalysisResult) -> str:
    """Renderiza el forest plot y el resumen del meta-análisis en Markdown."""
    ls = result.log_scale
    lines = [
        "# Meta-análisis cuantitativo",
        "",
        f"- Medida: **{result.measure}**" + (" (escala log)" if ls else ""),
        f"- Estudios (k): **{result.k}**",
        "",
        "## Forest plot",
        "",
        "| Estudio | Efecto | IC95% | Peso (aleat.) |",
        "|---|---|---|---|",
    ]
    for s in result.studies:
        label = s.label or s.study_id
        lines.append(
            f"| {label} | {_fmt(s.yi, log_scale=ls)} | "
            f"[{s.ci_low:+.3f}, {s.ci_high:+.3f}] | {s.weight_random:.1f}% |"
        )
    fx, rnd = result.fixed, result.random
    lines += [
        f"| **Combinado (fijos)** | {_fmt(fx.estimate, log_scale=ls)} | "
        f"[{fx.ci_low:+.3f}, {fx.ci_high:+.3f}] | — |",
        f"| **Combinado (aleatorios)** | {_fmt(rnd.estimate, log_scale=ls)} | "
        f"[{rnd.ci_low:+.3f}, {rnd.ci_high:+.3f}] | — |",
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


def render_forest_png(result: MetaAnalysisResult, out_path: Path) -> bool:
    """Genera el forest plot PNG si matplotlib está disponible.

    Returns:
        ``True`` si se escribió el PNG; ``False`` si matplotlib no está instalado.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    studies = result.studies
    labels = [s.label or s.study_id for s in studies] + ["Aleatorios (combinado)"]
    estimates = [s.yi for s in studies] + [result.random.estimate]
    lows = [s.ci_low for s in studies] + [result.random.ci_low]
    highs = [s.ci_high for s in studies] + [result.random.ci_high]
    ys = list(range(len(labels)))[::-1]

    fig, ax = plt.subplots(figsize=(7, 0.5 * len(labels) + 1.5))
    for i, y in enumerate(ys):
        ax.plot([lows[i], highs[i]], [y, y], color="#444", linewidth=1)
        marker = "D" if i == len(labels) - 1 else "s"
        ax.plot(estimates[i], y, marker, color="#1f4e79")
    ax.axvline(0, color="#999", linestyle="--", linewidth=0.8)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels)
    ax.set_xlabel(f"Efecto ({result.measure})")
    ax.set_title("Forest plot")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def render_funnel_png(result: MetaAnalysisResult, out_path: Path) -> bool:
    """Genera el funnel plot PNG si matplotlib está disponible."""
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
    ax.set_xlabel(f"Efecto ({result.measure})")
    ax.set_ylabel("Error estándar")
    ax.set_title("Funnel plot")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True
