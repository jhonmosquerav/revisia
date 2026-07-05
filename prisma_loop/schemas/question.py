"""Marco de la pregunta de investigación (PICO/PICo/PEO/SPICE/SPIDER).

Espeja la §2 del documento metodológico canónico. El marco se declara en el
protocolo y condiciona criterios de inclusión y estrategia de búsqueda.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class QuestionFramework(StrEnum):
    """Marcos de formulación de pregunta soportados."""

    PICO = "PICO"  # Population · Intervention · Comparator · Outcome
    PICo = "PICo"  # Population · Interest · Context (cualitativo)
    PEO = "PEO"  # Population · Exposure · Outcome
    SPICE = "SPICE"  # Setting · Perspective · Intervention · Comparison · Evaluation
    SPIDER = "SPIDER"  # Sample · Phenomenon · Design · Evaluation · Research type


class ResearchQuestion(BaseModel):
    """Pregunta de investigación estructurada.

    Attributes:
        text: la pregunta en lenguaje natural.
        framework: marco elegido.
        components: componentes del marco (ej. ``{"Population": "...", ...}``).
    """

    text: str
    framework: QuestionFramework
    components: dict[str, str] = Field(default_factory=dict)
