"""Reporte de verificación anti-alucinación (paso transversal del verificador).

Tras cada agente de razonamiento, el verificador comprueba que cada cita/
afirmación esté *grounded* en el corpus recuperado: que el id citado exista y
que la afirmación esté respaldada por la fuente. Si algo no se sostiene, marca
``hallucination_flagged`` y el flujo bloquea el avance antes del checkpoint
humano (reduce la carga humana a revisar solo lo señalado).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CitationCheck(BaseModel):
    """Verificación de una sola cita/afirmación.

    Attributes:
        claim: afirmación emitida por el agente.
        cited_id: id del estudio citado (si lo hay).
        exists_in_corpus: el id citado existe en el corpus recuperado.
        grounded: la afirmación está respaldada por la fuente citada.
        note: observación opcional del verificador.
    """

    claim: str
    cited_id: str | None = None
    exists_in_corpus: bool = False
    grounded: bool = False
    note: str | None = None


class VerificationReport(BaseModel):
    """Resultado de la verificación de la salida de una etapa.

    Attributes:
        stage: etapa verificada.
        checks: verificaciones individuales.
        hallucination_flagged: hay al menos una cita inexistente/no-grounded.
        notes: resumen opcional.
    """

    stage: str
    checks: list[CitationCheck] = Field(default_factory=list)
    hallucination_flagged: bool = False
    notes: str | None = None

    def recompute_flag(self) -> bool:
        """Recalcula ``hallucination_flagged`` a partir de los checks."""
        self.hallucination_flagged = any(
            (not c.exists_in_corpus) or (not c.grounded) for c in self.checks
        )
        return self.hallucination_flagged
