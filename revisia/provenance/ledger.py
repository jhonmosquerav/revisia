"""Ledger append-only de decisiones (humano + IA).

Registra cada decisión del pipeline en un JSONL inmutable: quién (humano o
agente), cuándo, en qué etapa, qué se decidió y con qué nivel de autonomía.
Es la columna vertebral de la auditabilidad PRISMA-trAIce y de la
reproducibilidad "a nivel decisión": dos ejecuciones con el mismo ledger
toman las mismas decisiones aunque el LLM no sea determinista a nivel token.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from revisia.provenance.runmeta import utc_now_iso

# Import diferido: `schemas.artifacts` importa `provenance.runmeta`, y el paquete
# `provenance` importa este módulo; un import real aquí cerraría el ciclo.
if TYPE_CHECKING:
    from revisia.schemas.artifacts import GateSummary

# Acciones que el motor escribe en el ledger (spec 2026-10-04 §4.3). El auditor
# rechaza cualquier otra: la reconstrucción de la auditoría 2026-09-03 (C3)
# traía `propose`, `exclude` y `verify`, que ningún código del motor emite.
LEDGER_ACTIONS: frozenset[str] = frozenset(
    {"approve", "reject", "auto-proceed", "label", "flag_review"}
)
# Subconjunto que cierra un gate: la última de una etapa es su decisión efectiva.
GATE_DECISION_ACTIONS: frozenset[str] = frozenset({"approve", "reject", "auto-proceed"})
# Prefijo de los actores humanos (`human:<nombre>`, el de `decision.yml`).
HUMAN_ACTOR_PREFIX = "human:"
# Actor sintético de `--auto-approve`: no es humano (D8, D9).
AUTO_APPROVE_ACTOR = "auto-approve (demo)"


def plain_text(text: str) -> str:
    """El texto en una sola línea, sin saltos, controles ni marcas de formato (D4).

    PyYAML y libyaml cierran un comentario con cualquier salto de línea de YAML 1.1
    (LF, CR, U+0085, U+2028, U+2029): lo que viniera detrás, p. ej. un
    ``approved: true`` dentro de un ``rationale``, sería una clave de verdad. Todo
    espacio (esos saltos incluidos) y todo carácter no imprimible (controles C0 y C1,
    sustitutos sueltos) pasa a un espacio, y los espacios se pliegan. Las marcas de
    formato (categoría Cf: U+00AD, ZWNJ, ZWJ, U+200B, U+FEFF, las de dirección…) no
    separan palabras, así que se borran: sustituirlas por un espacio partiría "intervención"
    en dos.
    """
    visible = (
        "" if unicodedata.category(ch) == "Cf" else ch if ch.isprintable() else " " for ch in text
    )
    return " ".join("".join(visible).split())


def is_human_actor(actor: str) -> bool:
    """¿``actor`` es un humano identificado? ``human:<nombre>``, con un nombre visible.

    Es la única definición de «humano» del motor: la usan el gate (que exige una decisión
    humana al reutilizar o aplicar), el pipeline y los entregables. El prefijo solo no
    basta: ``human:`` (o ``human:`` y espacios) no dice quién decidió. Tampoco un nombre
    que no se ve (``human:`` + U+200B, una marca de formato Cf, o un NUL): se juzga el
    texto que queda con ``plain_text``. El default de la plantilla, ``human:desconocido``,
    sí cuenta (tiene nombre; el auditor le da WARN).
    """
    return actor.startswith(HUMAN_ACTOR_PREFIX) and bool(
        plain_text(actor.removeprefix(HUMAN_ACTOR_PREFIX))
    )


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
        # Se parte por el salto de línea y no con `splitlines()`: `model_dump_json` escribe
        # U+2028/U+2029/U+0085 crudos dentro de las cadenas y `splitlines()` partiría la
        # entrada por la mitad. `read_text` ya pliega el CRLF; `strip()` quita el resto.
        for line in self.path.read_text(encoding="utf-8").split("\n"):
            stripped = line.strip()
            if stripped:
                entries.append(DecisionEntry.model_validate_json(stripped))
        return entries


def summarize_gates(entries: Iterable[DecisionEntry]) -> dict[str, GateSummary]:
    """Reduce el ledger a la decisión efectiva de cada etapa (D12, D14).

    La decisión efectiva de una etapa es su **última** entrada ``approve``,
    ``reject`` o ``auto-proceed`` en el orden del fichero (se puede reanudar
    tras un rechazo; todas quedan registradas). ``n_labels`` y
    ``n_flag_reviews`` cuentan las entradas ``label``/``flag_review`` de esa
    etapa que llevan el mismo ``decision_sha256`` que la decisión efectiva; si
    esta no lo tiene (``auto-proceed`` o ledger anterior a la Ola 1), valen 0.

    Es el único reductor del ledger: lo usan el pipeline (checklist trAIce y
    métodos, M13) y el auditor, para que no se contradigan (auditoría
    2026-09-03, C3/M13). Las etapas sin decisión no aparecen en el resultado.
    """
    # Import diferido: ver el comentario de `TYPE_CHECKING` arriba (evita el ciclo).
    from revisia.schemas.artifacts import GateSummary

    entries = list(entries)
    effective: dict[str, DecisionEntry] = {}
    for entry in entries:
        if entry.action in GATE_DECISION_ACTIONS:
            effective[entry.stage] = entry

    summaries: dict[str, GateSummary] = {}
    for stage, decision in effective.items():
        decision_sha = decision.detail.get("decision_sha256")
        n_labels = n_flags = 0
        if decision_sha is not None:
            for entry in entries:
                if entry.stage != stage or entry.detail.get("decision_sha256") != decision_sha:
                    continue
                if entry.action == "label":
                    n_labels += 1
                elif entry.action == "flag_review":
                    n_flags += 1
        summaries[stage] = GateSummary(
            stage=stage,
            action=decision.action,
            actor=decision.actor,
            autonomy=decision.autonomy,
            request_sha256=decision.detail.get("request_sha256"),
            decision_sha256=decision_sha,
            n_labels=n_labels,
            n_flag_reviews=n_flags,
            forced_human=bool(decision.detail.get("forced_human", False)),
            timestamp_utc=decision.timestamp_utc,
        )
    return summaries
