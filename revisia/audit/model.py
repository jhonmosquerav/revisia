"""Modelo del informe de auditoría (``AuditCheck``, ``AuditReport``, ``Status``)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from revisia.audit.state import RunState

# ``N/A`` = la etapa del check no se alcanzó (corrida en pausa, interrumpida o
# rechazada) o su raíz ya dio FAIL en otra fila. Invariante del auditor: si hay
# algún N/A, hay al menos un FAIL (spec 2026-10-04 §9.2).
Status = Literal["PASS", "WARN", "FAIL", "N/A"]

STATUS_ICON: dict[str, str] = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "N/A": "➖"}

# Lo que devuelve cada check: estado y evidencia. El registro (``CheckSpec``)
# pone el id y el ítem de reporte.
Verdict = tuple[Status, str]


@dataclass(frozen=True)
class AuditCheck:
    """Resultado de una verificación puntual de la auditoría."""

    check_id: str
    item_ref: str  # ítem PRISMA / trAIce que respalda la verificación
    status: Status
    detail: str


@dataclass(frozen=True)
class AuditReport:
    """Informe completo de auditoría de una corrida.

    ``checks`` tiene siempre una fila por check registrado, en el mismo orden:
    la forma del informe es estable y comparable entre corridas. ``state`` es
    el estado que el auditor dedujo de la corrida (``None`` solo en informes
    construidos a mano).
    """

    run_dir: Path
    checks: list[AuditCheck]
    state: RunState | None = None

    @property
    def n_fail(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def n_na(self) -> int:
        return sum(1 for c in self.checks if c.status == "N/A")

    @property
    def publishable(self) -> bool:
        return self.n_fail == 0
