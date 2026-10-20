"""Contrato de la capa de abstracción LLM.

Define el ``Protocol`` que todo proveedor implementa, de modo que el mismo
agente corra con Gemini, OpenAI, Anthropic o un modelo local sin cambiar
código del núcleo. Cada llamada devuelve, junto al resultado, un ``RunMeta``
de procedencia (ver :mod:`revisia.provenance.runmeta`).

El núcleo programa contra este Protocol, nunca contra un proveedor concreto:
esa es la garantía de que el repo corre end-to-end sin Claude Code ni ningún
SDK específico salvo el que la config pida.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from revisia.provenance.runmeta import RunMeta

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class TransientCallError(RuntimeError):
    """El intento falló por algo que reanudar puede arreglar (429, 5xx, red, timeout).

    Regla de D9 (spec 2026-10-18): lo transitorio se reanuda sin molestar al humano.
    Los 401 y 403 son globales (credencial, permiso) y se tratan como transitorios
    (§19 fila 14 del spec). Subclase de ``RuntimeError`` para que el código de la Ola 1
    que atrapa ``RuntimeError`` (rc 3) siga funcionando.

    """


class DeterministicCallError(RuntimeError):
    """El intento falló por algo que repetir no arregla (D9; §19 fila 14).

    Cubre el 4xx distinto de 401/403/408/429, el bloqueo de contenido, el límite de
    presupuesto o de turnos y la salida que no valida tras los reintentos. Regla de
    D9: lo determinista pasa al humano; reintentarlo solo gastaría presupuesto.

    Attributes:
        attempts: intentos consumidos antes de rendirse (1 si falló a la primera). Al
            menos 1: rendirse sin haber intentado es un bug del llamador (``ValueError``).
    """

    def __init__(self, message: str, *, attempts: int = 1) -> None:
        if attempts < 1:
            raise ValueError(f"attempts debe ser >= 1 (llegó {attempts})")
        super().__init__(message)

        self.attempts = attempts


@dataclass(slots=True, frozen=True)
class LLMRequest:
    """Una petición a un proveedor LLM, agnóstica del backend.

    Los parámetros de muestreo viajan en la petición (no en el proveedor)
    para que una misma instancia de proveedor sirva distintas etapas con
    distinta temperatura/seed.

    ``prompt_template`` es el nombre con versión de la plantilla renderizada
    (``"extraccion/v2.md"``); es el que viaja a ``RunMeta.prompt_template``
    (auditoría 2026-09-03, A7). Lo rellenan los agentes en PR-A.
    """

    prompt: str
    system: str | None = None
    temperature: float = 0.0
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int = 4096
    prompt_template: str | None = None


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
