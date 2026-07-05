"""Grounding por juicio de un modelo (anti-alucinación SIN vectores).

Alternativa de costo cero al grounding por embeddings: en vez de medir similitud
coseno entre la afirmación y la fuente —que no cruza idiomas (una síntesis en
español contra abstracts en inglés da similitud baja aunque la afirmación sea
correcta)—, se le pide a un proveedor LLM que **juzgue** si la fuente respalda la
afirmación y devuelva la cita textual de soporte.

Es provider-agnóstico: con ``provider: agent`` lo resuelve el agente de la sesión
(sin API key ni descarga); con gemini/openai/anthropic/claude_code, ese proveedor.
No requiere ``fastembed`` ni embeddings: encaja con la filosofía de un cerebro de
archivos (markdown), sin vectores ni servidores.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from prisma_loop.llm.base import LLMProvider, LLMRequest

_SYSTEM = (
    "Eres un verificador anti-alucinación para revisiones sistemáticas. Juzgas si "
    "una afirmación está respaldada por el texto fuente citado. La afirmación y la "
    "fuente pueden estar en idiomas distintos; juzga por el SIGNIFICADO, no por el "
    "solape de palabras. Sé estricto: si la fuente no respalda la afirmación, dilo."
)


class GroundingVerdict(BaseModel):
    """Veredicto de grounding de una afirmación contra su fuente."""

    grounded: bool = Field(description="¿La fuente respalda la afirmación?")
    support_quote: str | None = Field(
        default=None, description="Cita textual de la fuente que respalda, si existe."
    )
    reason: str = Field(default="", description="Justificación breve del veredicto.")


# Un juez recibe (afirmación, texto_fuente) y devuelve un veredicto.
GroundingJudge = Callable[[str, str], GroundingVerdict]


def make_provider_judge(
    provider: LLMProvider, model_name: str = "", *, temperature: float = 0.0
) -> GroundingJudge:
    """Construye un juez de grounding respaldado por un proveedor LLM.

    Args:
        provider: cualquier ``LLMProvider`` (``agent`` para costo cero en sesión).
        model_name: etiqueta del modelo (informativa).
        temperature: temperatura del juicio (0.0 = determinista en lo posible).

    Returns:
        Un ``GroundingJudge`` que devuelve un :class:`GroundingVerdict` por llamada.
    """

    def judge(claim: str, source: str) -> GroundingVerdict:
        prompt = (
            "AFIRMACIÓN:\n"
            f"{claim}\n\n"
            "TEXTO FUENTE CITADO:\n"
            f"{source}\n\n"
            "¿El texto fuente respalda la afirmación? Devuelve grounded (bool), "
            "support_quote (cita textual de la fuente, o null) y reason (breve)."
        )
        req = LLMRequest(prompt=prompt, system=_SYSTEM, temperature=temperature)
        verdict, _meta = provider.structured(req, GroundingVerdict)
        return verdict

    return judge
