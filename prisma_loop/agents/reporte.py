"""Agente de síntesis narrativa / reporte (🤖 razonamiento).

Redacta el borrador de síntesis (SWiM) de los estudios incluidos, exigiendo que
cada afirmación cite el id del estudio (lo verifica el verificador). Los conteos
del diagrama de flujo PRISMA y los checklists son deterministas y viven en
``prisma_loop.exports``. Autonomía A1: el borrador lo aprueba/edita un humano.
"""

from __future__ import annotations

from prisma_loop.llm.base import LLMProvider, LLMRequest
from prisma_loop.prompts import load_prompt
from prisma_loop.provenance.runmeta import RunMeta
from prisma_loop.schemas.extraction import ExtractionRecord
from prisma_loop.schemas.records import SearchRecord

_SYSTEM = "Eres un redactor académico riguroso que nunca afirma lo que no está respaldado."


def _studies_block(included: list[SearchRecord], extractions: dict[str, ExtractionRecord]) -> str:
    lines: list[str] = []
    for record in included:
        lines.append(f"- [{record.record_id}] {record.title}")
        extraction = extractions.get(record.record_id)
        if extraction:
            for key, field in extraction.fields.items():
                if field.value:
                    lines.append(f"    · {key}: {field.value}")
    return "\n".join(lines)


def synthesize_narrative(
    provider: LLMProvider,
    *,
    question: str,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
    temperature: float = 0.2,
    seed: int | None = None,
) -> tuple[str, RunMeta]:
    """Genera el borrador de síntesis narrativa y su procedencia."""
    example_id = included[0].record_id if included else "rec-1"
    prompt = load_prompt("reporte").format(
        question=question,
        studies=_studies_block(included, extractions) or "(sin estudios incluidos)",
        example_id=example_id,
    )
    req = LLMRequest(prompt=prompt, system=_SYSTEM, temperature=temperature, seed=seed)
    resp = provider.complete(req)
    return resp.text, resp.meta
