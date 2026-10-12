"""Extracción de datos · formulario tipado con cita de origen por campo.

Espeja la §6 del documento canónico. Cada campo extraído guarda la **cita/span de
origen** que el modelo reporta y un estado. La cita se pide y se guarda junto al valor;
nada la contrasta con el texto, así que sirve de ayuda al revisor, no de verificación.
Todo campo encontrado queda en ``needs_review`` y va al checkpoint humano. La extracción
nunca supera autonomía A0 (revisión humana campo a campo del 20% mínimo).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ExtractionStatus = Literal["verified", "needs_review", "not_found"]


class ExtractionField(BaseModel):
    """Un campo extraído con su procedencia textual.

    Attributes:
        value: valor extraído (``None`` si no se encontró).
        source_quote: cita textual que el modelo da como respaldo del valor (se guarda, no
            se verifica contra el texto).
        source_locator: ubicación legible (ej. ``"p.4, Tabla 2"``).
        confidence: confianza en [0, 1].
        status: estado de verificación del campo.
    """

    value: str | None = None
    source_quote: str | None = None
    source_locator: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: ExtractionStatus = "needs_review"


class ExtractionRecord(BaseModel):
    """Formulario de extracción completo de un estudio.

    Las claves de ``fields`` se definen en ``extraction_form.yml`` del
    protocolo, de modo que el formulario es configurable por revisión.
    """

    study_id: str
    fields: dict[str, ExtractionField] = Field(default_factory=dict)
    extractor: str = "agent:extraccion"
