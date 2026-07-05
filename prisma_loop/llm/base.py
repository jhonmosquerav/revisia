"""Contrato de la capa de abstracción LLM.

Define el ``Protocol`` que todo proveedor implementa, de modo que el mismo
agente corra con Gemini, OpenAI, Anthropic o un modelo local sin cambiar
código del núcleo. Cada llamada devuelve, junto al resultado, un ``RunMeta``
de procedencia (ver :mod:`prisma_loop.provenance.runmeta`).

El núcleo programa contra este Protocol, nunca contra un proveedor concreto:
esa es la garantía de que el repo corre end-to-end sin Claude Code ni ningún
SDK específico salvo el que la config pida.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from prisma_loop.provenance.runmeta import RunMeta

SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(slots=True, frozen=True)
class LLMRequest:
    """Una petición a un proveedor LLM, agnóstica del backend.

    Los parámetros de muestreo viajan en la petición (no en el proveedor)
    para que una misma instancia de proveedor sirva distintas etapas con
    distinta temperatura/seed.
    """

    prompt: str
    system: str | None = None
    temperature: float = 0.0
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int = 4096


@dataclass(slots=True, frozen=True)
class LLMResponse:
    """Respuesta de texto libre de un proveedor, con su procedencia."""

    text: str
    meta: RunMeta


@runtime_checkable
class LLMProvider(Protocol):
    """Contrato que implementa cada proveedor LLM.

    Attributes:
        name: identificador estable usado en config (ej. ``"gemini"``).
    """

    name: str

    def complete(self, req: LLMRequest) -> LLMResponse:
        """Genera texto libre a partir de la petición."""
        ...

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        """Genera salida estructurada validada contra un schema Pydantic.

        Returns:
            Tupla ``(objeto_validado, run_meta)``. La validación contra el
            schema ocurre dentro del proveedor; el agente recibe ya un objeto
            tipado, no texto a parsear.
        """
        ...
