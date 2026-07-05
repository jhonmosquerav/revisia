"""Contexto de una corrida · carpeta ``runs/<slug>-<fecha>/`` reproducible.

Centraliza dónde se escriben los artefactos de una ejecución, acumula los
``RunMeta`` de todas las llamadas a IA y escribe el ``manifest.yml`` que permite
a otro investigador reproducir (o entender la no-reproducibilidad de) la corrida.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from prisma_loop.provenance.ledger import DecisionLedger
from prisma_loop.provenance.runmeta import RunMeta, utc_now_iso


class RunContext:
    """Estado y rutas de una ejecución concreta del pipeline."""

    def __init__(self, slug: str, runs_root: str | Path, timestamp: str) -> None:
        self.slug = slug
        self.timestamp = timestamp
        self.run_dir = Path(runs_root) / f"{slug}-{timestamp}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = DecisionLedger(self.run_dir / "decisions_ledger.jsonl")
        self.metas: list[RunMeta] = []

    def stage_dir(self, name: str) -> Path:
        path = self.run_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def deliverable_dir(self) -> Path:
        path = self.run_dir / "deliverable"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def record_meta(self, meta: RunMeta) -> None:
        self.metas.append(meta)

    def write_text(self, relpath: str, content: str) -> Path:
        path = self.run_dir / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(self, relpath: str, data: object) -> Path:
        return self.write_text(relpath, json.dumps(data, ensure_ascii=False, indent=2))

    def write_manifest(
        self, *, protocol_snapshot: dict, counts: dict, extra: dict | None = None
    ) -> Path:
        """Escribe ``manifest.yml`` con todo lo necesario para reproducir."""
        manifest = {
            "slug": self.slug,
            "created_utc": utc_now_iso(),
            "timestamp": self.timestamp,
            "protocol": protocol_snapshot,
            "counts": counts,
            "llm_calls": [m.model_dump() for m in self.metas],
            "models_used": sorted({f"{m.provider}:{m.model}" for m in self.metas}),
            "deterministic_token_level": (
                all(m.deterministic for m in self.metas) if self.metas else True
            ),
            **(extra or {}),
        }
        path = self.run_dir / "manifest.yml"
        path.write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        return path
