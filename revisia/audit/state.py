"""Estado de una corrida deducido de sus artefactos (spec 2026-10-04 §9.2).

El auditor no audita igual una corrida terminada que una en pausa: en una
pausa, lo que está después del gate pendiente todavía no existe y exigirlo
daría FAIL falsos. ``derive_state`` deduce el estado de ``run.json`` (si
existe), del ledger validado y de qué gates tienen ``review_request.yml``.
Las filas de checks cuya etapa no se alcanzó salen ``N/A``; como una pausa
siempre deja ``final_gate`` en FAIL, un ``N/A`` no puede ocultar nada en una
corrida publicable.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from typing import Literal

from revisia.config import STAGES
from revisia.schemas.artifacts import GATED_STAGES, GateSummary, RunInfo

RunStateStatus = Literal["completed", "paused", "rejected", "interrupted", "unknown"]

# Acciones con las que un gate deja pasar la corrida a la etapa siguiente.
_PASSED = frozenset({"approve", "auto-proceed"})

_DESCRIPCION = {
    "paused": "en pausa en",
    "rejected": "rechazada en",
    "interrupted": "interrumpida en",
}


@dataclass(frozen=True)
class RunState:
    """Estado deducido de una corrida.

    Attributes:
        status: ``completed`` | ``paused`` | ``rejected`` | ``interrupted`` |
            ``unknown`` (ledger ilegible o vacío y sin ``run.json``: se exige
            todo).
        reached: etapas de ``config.STAGES`` cuyos artefactos deben existir.
        pending_stage: gate en el que está detenida la corrida (``None`` si
            terminó o si el estado es desconocido).
    """

    status: RunStateStatus
    reached: frozenset[str]
    pending_stage: str | None = None

    def describe(self) -> str:
        """Descripción legible: ``completada``, ``en pausa en `screening_ft```…"""
        if self.status == "completed":
            return "completada"
        if self.status == "unknown":
            return "desconocido (ledger ilegible o vacío y sin run.json): se exige todo"
        return f"{_DESCRIPCION[self.status]} `{self.pending_stage}`"

    def na_detail(self) -> str:
        """Detalle de una fila ``N/A`` por etapa no alcanzada."""
        return f"no aplica: corrida {self.describe()}; se verificará al reanudar."


def _reached_until(pending: str) -> frozenset[str]:
    """Etapas anteriores al gate pendiente (más ``reporte`` si es ese gate).

    El manifiesto y el entregable se escriben al evaluar el gate final, con
    cualquier resultado (spec §4.2): una corrida en pausa o rechazada en
    ``reporte`` se audita entera.
    """
    idx = STAGES.index(pending)
    reached = set(STAGES[:idx])
    if pending == "reporte":
        reached.add("reporte")
    return frozenset(reached)


def derive_state(
    *,
    run_info: RunInfo | None,
    gates: Mapping[str, GateSummary],
    requests: Set[str],
    ledger_ok: bool,
) -> RunState:
    """Deduce el estado de la corrida.

    Args:
        run_info: ``run.json`` validado, o ``None`` (corrida anterior a la Ola
            1 o fichero ausente).
        gates: decisión efectiva por etapa (``summarize_gates`` del ledger).
        requests: gates con ``<gate>/review_request.yml`` en disco.
        ledger_ok: el ledger existe, se lee entero y tiene entradas.

    Reglas (en este orden): ``unknown`` si el ledger no sirve y no hay
    ``run.json``; ``rejected`` si la decisión efectiva de algún gate es
    ``reject``; ``completed`` si ``reporte`` pasó (``approve`` o
    ``auto-proceed``: quién decidió lo juzga ``final_gate``);
    ``interrupted`` si ``run.json`` lo dice; si no, el primer gate sin
    decisión: ``paused`` con solicitud, ``interrupted`` sin ella.

    ``completed`` lo decide el ledger, para que se audite todo, pero el ``approve`` del reporte
    puede ser de una vuelta anterior: si ``run.json`` dice ``paused``, ``interrupted`` o
    ``running`` (o ``rejected``), la corrida no terminó y ``final_gate`` da el FAIL.
    """
    everything = frozenset(STAGES)
    if not ledger_ok and run_info is None:
        return RunState("unknown", everything)

    for gate in GATED_STAGES:
        summary = gates.get(gate)
        if summary is not None and summary.action == "reject":
            return RunState("rejected", _reached_until(gate), gate)

    reporte = gates.get("reporte")
    if reporte is not None and reporte.action in _PASSED:
        return RunState("completed", everything)

    pending = next((g for g in GATED_STAGES if g not in gates), None)
    if run_info is not None and run_info.status == "interrupted":
        stage = run_info.stage if run_info.stage in STAGES else pending
        if stage is None:
            return RunState("unknown", everything)
        return RunState("interrupted", _reached_until(stage), stage)
    if pending is None:
        return RunState("unknown", everything)
    if pending in requests:
        return RunState("paused", _reached_until(pending), pending)
    return RunState("interrupted", _reached_until(pending), pending)
