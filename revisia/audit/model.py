"""Modelo del informe de auditoría (``AuditCheck``, ``AuditReport``)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditCheck:
    """Resultado de una verificación puntual de la auditoría."""

    check_id: str
    item_ref: str  # ítem PRISMA / trAIce que respalda la verificación
    status: str  # PASS | WARN | FAIL
    detail: str


@dataclass(frozen=True)
class AuditReport:
    """Informe completo de auditoría de una corrida."""

    run_dir: Path
    checks: list[AuditCheck]

    @property
    def n_fail(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def publishable(self) -> bool:
        return self.n_fail == 0
