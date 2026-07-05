"""Ledger append-only de decisiones (humano + IA).

Registra cada decisión del pipeline en un JSONL inmutable: quién (humano o
agente), cuándo, en qué etapa, qué se decidió y con qué nivel de autonomía.
Es la columna vertebral de la auditabilidad PRISMA-trAIce y de la
reproducibilidad "a nivel decisión": dos ejecuciones con el mismo ledger
toman las mismas decisiones aunque el LLM no sea determinista a nivel token.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from revisia.provenance.runmeta import utc_now_iso


class DecisionEntry(BaseModel):
    """Una decisión registrada en el ledger.

    Attributes:
        stage: etapa del pipeline (ej. ``"screening_ta"``).
        actor: ``"human:<nombre>"`` o ``"agent:<nombre>"``.
        autonomy: nivel de autonomía aplicado (``A0``..``A3``).
        action: acción tomada (ej. ``"approve"``, ``"include"``, ``"edit"``).
        target: id del registro/campo afectado, si aplica.
        detail: payload estructurado adicional.
        timestamp_utc: instante de la decisión.
    """

    stage: str
    actor: str
    autonomy: str
    action: str
    target: str | None = None
    detail: dict = Field(default_factory=dict)
    timestamp_utc: str = Field(default_factory=utc_now_iso)


class DecisionLedger:
    """Escritura/lectura append-only de un ledger de decisiones en JSONL."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, entry: DecisionEntry) -> None:
        """Añade una decisión al final del ledger (crea el archivo si falta)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json() + "\n")

    def read_all(self) -> list[DecisionEntry]:
        """Lee todas las decisiones registradas, en orden de aparición."""
        if not self.path.exists():
            return []
        entries: list[DecisionEntry] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                entries.append(DecisionEntry.model_validate_json(stripped))
        return entries
