"""Agente de extracción de datos (🤖 razonamiento).

Llena el formulario de extracción (definido en ``extraction_form.yml``) a partir
del abstract, guardando la **cita textual de origen** por campo. Sin cita
verificable, el campo queda ``not_found``/``needs_review`` y va al checkpoint
humano (autonomía A0). En H3 se ampliará a full-text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from revisia.llm.base import LLMProvider, LLMRequest
from revisia.prompts import load_prompt
from revisia.provenance.runmeta import RunMeta
from revisia.schemas.extraction import ExtractionField, ExtractionRecord
from revisia.schemas.records import SearchRecord

_SYSTEM = "Eres un extractor de datos meticuloso que solo reporta lo que el texto dice."


class _ExtractedField(BaseModel):
    key: str
    value: str | None = None
    source_quote: str | None = None
    found: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class _ExtractionOut(BaseModel):
    fields: list[_ExtractedField] = Field(default_factory=list)


def extract_record(
    provider: LLMProvider,
    *,
    record: SearchRecord,
    form_fields: list[dict],
    temperature: float = 0.0,
    seed: int | None = None,
) -> tuple[ExtractionRecord, RunMeta]:
    """Extrae los campos del formulario para un estudio.

    Args:
        form_fields: lista de campos del formulario (``{key, descripcion, ...}``).
    """
    fields_desc = "\n".join(f"- {f.get('key')}: {f.get('descripcion', '')}" for f in form_fields)
    prompt = load_prompt("extraccion").format(
        title=record.title,
        abstract=record.abstract or "(sin abstract disponible)",
        fields=fields_desc,
    )
    req = LLMRequest(prompt=prompt, system=_SYSTEM, temperature=temperature, seed=seed)
    out, meta = provider.structured(req, _ExtractionOut)

    fields: dict[str, ExtractionField] = {}
    for ef in out.fields:
        status = "needs_review" if ef.found and ef.value else "not_found"
        fields[ef.key] = ExtractionField(
            value=ef.value,
            source_quote=ef.source_quote,
            confidence=ef.confidence,
            status=status,
        )
    extraction = ExtractionRecord(study_id=record.record_id, fields=fields)
    return extraction, meta
