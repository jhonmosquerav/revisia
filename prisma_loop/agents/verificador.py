"""Agente verificador / grounding (transversal · anti-alucinación).

Corre tras cada agente de razonamiento, ANTES del checkpoint humano. Comprueba
que cada estudio citado exista en el corpus y, si se le da un embedder + las
fuentes, que la afirmación esté **semánticamente respaldada** por el texto de la
fuente citada (no solo que el id exista). Si algo no se sostiene, marca
alucinación y el orquestador bloquea el avance.

Niveles de grounding:
- **Existencia** (siempre): el id citado pertenece al corpus recuperado.
- **Semántico** (si hay embedder + sources): la similitud entre la afirmación y
  el texto de la fuente supera un umbral. Con el embedder portátil por defecto
  (hashing) el grounding es léxico; con Gemini es semántico real.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from prisma_loop.rag.store import semantic_similarity
from prisma_loop.schemas.verification import CitationCheck, VerificationReport

if TYPE_CHECKING:
    from prisma_loop.rag.embed import Embedder
    from prisma_loop.rag.grounding import GroundingJudge

# Citas con formato [id], donde id es un identificador de registro.
_CITATION_RE = re.compile(r"\[([A-Za-z0-9][\w.:/\-]*)\]")


def extract_citations(text: str) -> list[str]:
    """Extrae los identificadores citados (``[id]``) de un texto, sin duplicados."""
    seen: list[str] = []
    for match in _CITATION_RE.findall(text):
        if match not in seen:
            seen.append(match)
    return seen


def verify_narrative(
    stage: str,
    text: str,
    corpus_ids: Iterable[str],
    *,
    sources: Mapping[str, str] | None = None,
    embedder: Embedder | None = None,
    judge: GroundingJudge | None = None,
    threshold: float = 0.12,
) -> VerificationReport:
    """Verifica las citas de un texto: existencia + (opcional) grounding.

    El grounding semántico puede resolverse de dos formas (si hay ``sources``):
    por **juez** (un modelo que decide si la fuente respalda la afirmación;
    cruza idiomas) o por **embedder** (similitud coseno; léxico con el embedder
    portátil). Si se pasan ambos, el juez tiene prioridad. Sin ninguno, solo se
    verifica la existencia del id en el corpus.

    Args:
        stage: etapa cuya salida se verifica (ej. ``"reporte"``).
        text: texto generado que contiene citas ``[id]``.
        corpus_ids: ids válidos (estudios realmente recuperados/incluidos).
        sources: ``{id: texto_fuente}`` para grounding (opcional).
        embedder: embedder para similitud afirmación↔fuente (opcional).
        judge: juez de grounding (modelo) afirmación↔fuente (opcional, prioritario).
        threshold: similitud mínima para considerar "grounded" (modo embedder).
    """
    valid = set(corpus_ids)
    checks: list[CitationCheck] = []
    for cited in extract_citations(text):
        exists = cited in valid
        claim = _claim_context(text, cited)
        grounded = exists
        note = None if exists else "id citado no está en el corpus"
        if exists and sources and cited in sources and judge is not None:
            verdict = judge(claim, sources[cited])
            grounded = verdict.grounded
            note = (
                f"respaldado: «{verdict.support_quote}»"
                if grounded and verdict.support_quote
                else (
                    (verdict.reason or "la fuente no respalda la afirmación")
                    if not grounded
                    else None
                )
            )
        elif exists and embedder is not None and sources and cited in sources:
            sim = semantic_similarity(embedder, claim, sources[cited])
            grounded = sim >= threshold
            if not grounded:
                note = f"cita existe pero baja similitud con la fuente (sim={sim:.2f})"
        checks.append(
            CitationCheck(
                claim=claim,
                cited_id=cited,
                exists_in_corpus=exists,
                grounded=grounded,
                note=note,
            )
        )
    report = VerificationReport(stage=stage, checks=checks)
    report.recompute_flag()
    return report


def _claim_context(text: str, cited: str, window: int = 120) -> str:
    """Devuelve un fragmento del texto alrededor de la cita, para trazabilidad."""
    idx = text.find(f"[{cited}]")
    if idx == -1:
        return f"[{cited}]"
    start = max(0, idx - window)
    end = min(len(text), idx + len(cited) + 2 + window)
    return text[start:end].strip()
