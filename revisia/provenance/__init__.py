"""Procedencia y auditabilidad: RunMeta por llamada + ledger de decisiones."""

from __future__ import annotations

from revisia.provenance.ledger import DecisionEntry, DecisionLedger
from revisia.provenance.runmeta import RunMeta, sha256_text, utc_now_iso
from revisia.provenance.sink import MetaSink, collecting, current_sink, emit, installed

__all__ = [
    "RunMeta",
    "sha256_text",
    "utc_now_iso",
    "DecisionEntry",
    "DecisionLedger",
    "MetaSink",
    "collecting",
    "current_sink",
    "emit",
    "installed",
]
