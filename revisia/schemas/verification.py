"""Reporte de verificación anti-alucinación (paso transversal del verificador).

Tras cada agente de razonamiento, el verificador comprueba que cada cita/
afirmación esté *grounded* en el corpus recuperado: que el id citado exista y
que la afirmación esté respaldada por la fuente. Si algo no se sostiene, marca
``hallucination_flagged`` y el flujo bloquea el avance antes del checkpoint
humano (reduce la carga humana a revisar solo lo señalado).

v2 (Ola 2, contratos de PR-0; todos los campos nuevos tienen default para que los
reportes v1 sigan validando):

- **Modo (D2).** ``mode`` registra con qué se comprobó el respaldo: ``existence`` (solo que
  el id exista), ``judge`` (un modelo juez, descrito en ``judge``) o ``embedder``. La v1 no
  lo guardaba, por eso es opcional. ``mode == "judge"`` exige ``judge``.
- **Afirmaciones y no solo citas (D15).** ``n_claims`` cuenta las afirmaciones de la síntesis y
  ``uncited_quantitative`` lista las que traen cifras sin ninguna cita, que antes pasaban sin
  que nadie las viera.
- **Fuente disponible y cifras (C2).** ``source_available`` distingue «la fuente no tiene texto
  que comparar» de «la fuente no respalda»; ``numbers_in_claim``/``numbers_missing`` dicen qué
  cifras de la afirmación no aparecen en la cita de respaldo.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from revisia.schemas.artifacts import ARTIFACT_SCHEMA_VERSION, GroundingMode, QuoteStatus


class JudgeInfo(BaseModel):
    """Modelo juez que comprobó el respaldo (modo ``judge``, D2)."""

    provider: str
    model: str


class UncitedClaim(BaseModel):
    """Afirmación con cifras y sin ninguna cita (D15).

    Attributes:
        claim_index: posición de la afirmación en la síntesis.
        sentence: la oración, recortada a 300 caracteres.
        numbers: cifras detectadas en la oración.
    """

    claim_index: int = Field(ge=0)
    sentence: str = Field(max_length=300)
    numbers: list[str]


class CitationCheck(BaseModel):
    """Verificación de una sola cita/afirmación.

    Attributes:
        index: posición de la comprobación en el reporte (v2).
        claim_index: afirmación de la síntesis a la que pertenece (v2).
        claim: afirmación emitida por el agente, con un contexto de hasta 600 caracteres.
        cited_id: id del estudio citado (si lo hay).
        exists_in_corpus: el id citado existe en el corpus recuperado.
        source_available: la fuente tiene texto contra el que comparar (C2).
        numbers_in_claim: cifras de la afirmación.
        numbers_missing: cifras de la afirmación que no aparecen en la cita de respaldo.
        grounded: la afirmación está respaldada por la fuente citada.
        support_quote: cita textual de la fuente que respalda la afirmación.
        quote_status: cómo se halló ``support_quote`` en la fuente.
        verdict_reason: motivo del veredicto, en una frase.
        note: observación opcional del verificador.
    """

    index: int | None = None
    claim_index: int | None = None
    claim: str = Field(max_length=600)
    cited_id: str | None = None
    exists_in_corpus: bool = False
    source_available: bool = True
    numbers_in_claim: list[str] = Field(default_factory=list)
    numbers_missing: list[str] = Field(default_factory=list)
    grounded: bool = False
    support_quote: str | None = None
    quote_status: QuoteStatus = "none"
    verdict_reason: str | None = None
    note: str | None = None


class VerificationReport(BaseModel):
    """Resultado de la verificación de la salida de una etapa.

    Attributes:
        schema_version: versión del contrato (2).
        stage: etapa verificada.
        mode: con qué se comprobó el respaldo (``None`` en reportes v1).
        judge: modelo juez; obligatorio si ``mode == "judge"``.
        n_claims: afirmaciones de la síntesis.
        n_uncited_quantitative: afirmaciones con cifras y sin cita; igual a la longitud de
            ``uncited_quantitative``.
        uncited_quantitative: esas afirmaciones.
        checks: verificaciones individuales.
        hallucination_flagged: hay al menos una cita inexistente/no-grounded.
        notes: resumen opcional.
    """

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    stage: str
    mode: GroundingMode | None = None
    judge: JudgeInfo | None = None
    n_claims: int = 0
    n_uncited_quantitative: int = 0
    uncited_quantitative: list[UncitedClaim] = Field(default_factory=list)
    checks: list[CitationCheck] = Field(default_factory=list)
    hallucination_flagged: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _coherencia(self) -> VerificationReport:
        """El contador debe coincidir con la lista y el modo juez exige juez (D2, D15)."""
        if self.n_uncited_quantitative != len(self.uncited_quantitative):
            raise ValueError("n_uncited_quantitative no coincide con uncited_quantitative.")
        if self.mode == "judge" and self.judge is None:
            raise ValueError("mode='judge' exige el campo judge.")
        return self

    def flagged_indices(self) -> list[int]:
        """Posiciones en ``checks`` de las citas marcadas (inexistentes o sin respaldo).

        Es la única regla de «cita marcada»: la usan ``recompute_flag``, la solicitud del gate
        final (``must_adjudicate``) y el auditor (``request_hash``, ``final_gate`` y ``grounding``).
        """
        return [
            i for i, c in enumerate(self.checks) if (not c.exists_in_corpus) or (not c.grounded)
        ]

    def recompute_flag(self) -> bool:
        """Recalcula ``hallucination_flagged`` a partir de los checks."""
        self.hallucination_flagged = bool(self.flagged_indices())
        return self.hallucination_flagged
