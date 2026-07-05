"""Pre-chequeo de adherencia de un manuscrito a PRISMA 2020 (comando ``check``).

Dado un manuscrito (markdown/texto plano), un modelo evalúa **ítem por ítem**
si el reporte cubre cada uno de los 27 ítems del checklist PRISMA 2020, citando
la evidencia textual que encontró. Va en la línea de *PRISMA-Check* (la
herramienta de adherencia que el sitio oficial anuncia en desarrollo), con la
misma honestidad que el resto del sistema:

- Es un **pre-chequeo de escritorio**, no un juicio editorial ni una validación
  metodológica: un "cubierto" significa "el texto dice algo pertinente", no
  "lo que dice es correcto".
- La llamada queda registrada con ``RunMeta`` (modelo, hash del prompt) para
  poder declararla bajo PRISMA-trAIce si el chequeo se menciona en el flujo
  de trabajo del manuscrito.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from revisia.exports.checklist import _PRISMA_2020_ITEMS
from revisia.llm.base import LLMRequest
from revisia.llm.registry import ProviderConfig, build_provider
from revisia.provenance.runmeta import RunMeta

_MAX_CHARS = 150_000  # límite defensivo del manuscrito enviado al modelo

_STATUS_ICON = {"cubierto": "✅", "parcial": "🟡", "ausente": "❌", "sin_evaluar": "⬜"}

_SYSTEM = (
    "Eres un editor metodológico experto en la declaración PRISMA 2020 "
    "(Page et al., BMJ 2021;372:n71). Evalúas si un manuscrito de revisión "
    "sistemática REPORTA cada ítem del checklist: juzgas presencia y "
    "completitud del reporte, no la calidad científica. Si un ítem no aplica "
    "al diseño (p. ej. meta-análisis cuando la síntesis es narrativa), "
    "márcalo 'parcial' y explícalo en la evidencia. Sé estricto: 'cubierto' "
    "exige que el texto lo diga de forma explícita y localizable."
)


class ItemAdherence(BaseModel):
    """Juicio de adherencia de un ítem PRISMA 2020."""

    item: int = Field(ge=1, le=27)
    status: Literal["cubierto", "parcial", "ausente"]
    evidence: str = ""  # cita textual breve del manuscrito o razón del juicio


class AdherenceReport(BaseModel):
    """Evaluación completa de un manuscrito contra los 27 ítems."""

    items: list[ItemAdherence] = Field(default_factory=list)


def check_manuscript(text: str, provider_cfg: ProviderConfig) -> tuple[AdherenceReport, RunMeta]:
    """Evalúa la adherencia del manuscrito con el proveedor configurado."""
    provider = build_provider(provider_cfg)
    items_desc = "\n".join(
        f"{num}. [{section}] {title}" for section, num, title in _PRISMA_2020_ITEMS
    )
    manuscript = text[:_MAX_CHARS]
    prompt = (
        "Evalúa el manuscrito contra los 27 ítems del checklist PRISMA 2020.\n"
        "Para CADA ítem (1..27) devuelve: item, status "
        "('cubierto' | 'parcial' | 'ausente') y evidence (cita textual breve "
        "del manuscrito que lo respalda, o la razón del juicio; máx. 30 palabras).\n\n"
        f"Checklist:\n{items_desc}\n\n"
        f"Manuscrito:\n---\n{manuscript}\n---"
    )
    report, meta = provider.structured(
        LLMRequest(
            prompt=prompt,
            system=_SYSTEM,
            temperature=provider_cfg.temperature,
            seed=provider_cfg.seed,
            max_tokens=8192,
        ),
        AdherenceReport,
    )
    return report, meta


def render_adherence_md(report: AdherenceReport, *, source_name: str, model: str) -> str:
    """Renderiza el informe de adherencia como Markdown (27 filas siempre)."""
    by_item = {i.item: i for i in report.items}
    counts = {"cubierto": 0, "parcial": 0, "ausente": 0, "sin_evaluar": 0}
    lines = [
        "# Pre-chequeo de adherencia PRISMA 2020",
        "",
        f"- Manuscrito: `{source_name}`",
        f"- Evaluador: `{model}` (pre-chequeo asistido por IA; no sustituye la "
        "revisión editorial humana)",
        "",
        "| Ítem | Sección | Qué reporta | Estado | Evidencia / razón |",
        "|---|---|---|---|---|",
    ]
    for section, number, title in _PRISMA_2020_ITEMS:
        judged = by_item.get(number)
        status = judged.status if judged else "sin_evaluar"
        counts[status] += 1
        icon = _STATUS_ICON[status]
        evidence = (judged.evidence if judged else "").replace("|", "/").strip()
        lines.append(f"| {number} | {section} | {title} | {icon} {status} | {evidence} |")
    lines += [
        "",
        f"**Resumen:** ✅ cubiertos {counts['cubierto']} · 🟡 parciales "
        f"{counts['parcial']} · ❌ ausentes {counts['ausente']}"
        + (f" · ⬜ sin evaluar {counts['sin_evaluar']}" if counts["sin_evaluar"] else ""),
        "",
        "> Un 'cubierto' significa que el manuscrito lo reporta, no que sea "
        "metodológicamente correcto. Contraste final: humano.",
    ]
    return "\n".join(lines)
