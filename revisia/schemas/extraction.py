"""Extracción de datos · formulario tipado con cita de origen por campo.

Espeja la §6 del documento canónico. Cada campo extraído guarda la **cita/span de
origen** que el modelo reporta y un estado. La cita se pide y se guarda junto al valor;
nada la contrasta con el texto, así que sirve de ayuda al revisor, no de verificación.
Todo campo encontrado queda en ``needs_review`` y va al checkpoint humano. La extracción
nunca supera autonomía A0: el humano aprueba la tabla por estudio y corrige campo a campo
(D3); la concordancia IA-IA del 20 % es una señal, no una verificación (D4).

v2 (Ola 2): la cita se contrasta con el texto (``quote_status``/``quote_offset``) y la
corrección humana queda junto al valor del modelo, sin pisarlo (``final_value``, D22).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from revisia.schemas.artifacts import ARTIFACT_SCHEMA_VERSION, QuoteStatus, RecordStatus, SourceText

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
        quote_status: resultado de contrastar la cita con el texto (``none`` si no se contrastó).
        quote_offset: posición de la cita en el texto, si se encontró.
        human_value: valor corregido por el humano (el del modelo se conserva en ``value``).
        human_reason: porqué de la corrección (obligatorio si ``human_edited``).
        human_actor: quién corrigió (obligatorio si ``human_edited``).
        human_edited: ``True`` si el humano sustituyó el valor del modelo.
    """

    value: str | None = None
    source_quote: str | None = None
    source_locator: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: ExtractionStatus = "needs_review"
    quote_status: QuoteStatus = "none"
    quote_offset: int | None = Field(default=None, ge=0)
    human_value: str | int | float | None = None
    human_reason: str | None = None
    human_actor: str | None = None
    human_edited: bool = False

    @property
    def final_value(self) -> str | int | float | None:
        """Valor vigente: el humano si editó, si no el del modelo."""
        return self.human_value if self.human_edited else self.value

    @model_validator(mode="after")
    def _coherencia_humana(self) -> ExtractionField:
        """Una edición humana exige razón y actor; sin edición no hay rastro humano."""
        humanos = (self.human_value, self.human_reason, self.human_actor)
        if self.human_edited:
            if self.human_reason is None or self.human_actor is None:
                raise ValueError("human_edited exige human_reason y human_actor")
        elif any(h is not None for h in humanos):
            raise ValueError("human_value/reason/actor solo con human_edited=True")
        return self


class ExtractionRecord(BaseModel):
    """Formulario de extracción completo de un estudio.

    Las claves de ``fields`` se definen en ``extraction_form.yml`` del
    protocolo, de modo que el formulario es configurable por revisión. El default de
    ``source_text`` reproduce la v1: la 0.8 solo leía el resumen.
    """

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    study_id: str
    fields: dict[str, ExtractionField] = Field(default_factory=dict)
    extractor: str = "agent:extraccion"
    source_text: SourceText = "abstract"
    text_sha256: str | None = None
    truncated: bool = False
    status: RecordStatus = "ok"
