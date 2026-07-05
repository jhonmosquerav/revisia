"""Cerebro de investigador en archivos (markdown + JSONL · sin vectores).

``ResearchBrain`` sedimenta cada revisión sistemática en una estructura de
archivos portátil e inspirada en el patrón `cerebro`:

    <root>/
      genome/events.jsonl          # log append-only (una línea por revisión)
      wiki/semantic/<slug>.md      # síntesis vigente del tema (se sobrescribe)
      wiki/episodic/<slug>-<ts>.md # episodio: una corrida concreta
      raw/<slug>-<ts>/incluidos.md # estudios incluidos + extracción (inmutable)
      index.md                     # índice navegable de todas las revisiones

No usa embeddings ni Docker: la recuperación es "leer el archivo". Más adelante
se puede añadir un índice vectorial local opcional (ver
:class:`prisma_loop.rag.embed.FastEmbedEmbedder`) sin cambiar este formato.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ResearchBrain:
    """Memoria persistente de investigador respaldada por archivos markdown."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # ── escritura de alto nivel ─────────────────────────────────────────
    def record_review(
        self,
        *,
        slug: str,
        timestamp: str,
        question: str,
        counts: Mapping[str, Any],
        included_ids: list[str],
        narrative: str,
        models: list[str] | None = None,
        extractions: Mapping[str, Mapping[str, Any]] | None = None,
        titles: Mapping[str, str] | None = None,
    ) -> Path:
        """Sedimenta una revisión en el cerebro y devuelve la carpeta del episodio.

        Args:
            slug: identificador de la revisión.
            timestamp: marca de la corrida (``runs/<slug>-<timestamp>``).
            question: pregunta de investigación.
            counts: conteos PRISMA (dict-like).
            included_ids: ids de los estudios incluidos.
            narrative: síntesis narrativa (texto).
            models: modelos/proveedores usados (procedencia).
            extractions: ``{id: {campo: valor}}`` para la tabla del raw.
            titles: ``{id: título}`` si se conocen (para legibilidad).
        """
        models = models or []
        titles = titles or {}
        self._append_event(slug, timestamp, question, counts, included_ids, models)
        self._write_semantic(slug, question, narrative, included_ids, titles)
        episode = self._write_episodic(
            slug, timestamp, question, counts, included_ids, narrative, models, titles
        )
        self._write_raw(slug, timestamp, included_ids, extractions or {}, titles)
        self._rebuild_index()
        return episode

    def record_from_run(self, run_dir: str | Path) -> Path:
        """Lee los artefactos de un ``runs/<slug>-<ts>/`` y lo sedimenta.

        Trabaja sobre archivos ya escritos (manifiesto, extracción, deliverable),
        de modo que sirve también para corridas pasadas: archivos in → archivos out.
        """
        import yaml

        run = Path(run_dir)
        manifest = yaml.safe_load((run / "manifest.yml").read_text(encoding="utf-8")) or {}
        proto = manifest.get("protocol", {})
        slug = manifest.get("slug") or run.name
        timestamp = manifest.get("timestamp") or run.name.split("-")[-1]
        question = (proto.get("question") or {}).get("text", "")
        counts = manifest.get("counts", {})
        models = manifest.get("models_used", [])

        extractions = self._read_extractions(run)
        included_ids = sorted(extractions.keys())
        narrative = self._read_narrative(run)
        titles = self._read_titles(run)
        return self.record_review(
            slug=slug,
            timestamp=timestamp,
            question=question,
            counts=counts,
            included_ids=included_ids,
            narrative=narrative,
            models=models,
            extractions=extractions,
            titles=titles,
        )

    # ── escritura por capa ──────────────────────────────────────────────
    def _append_event(self, slug, timestamp, question, counts, included_ids, models) -> None:
        path = self.root / "genome" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "created_utc": datetime.now(UTC).isoformat(),
            "slug": slug,
            "timestamp": timestamp,
            "question": question,
            "counts": dict(counts),
            "n_included": len(included_ids),
            "included_ids": included_ids,
            "models": models,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _write_semantic(self, slug, question, narrative, included_ids, titles) -> None:
        path = self.root / "wiki" / "semantic" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        refs = "\n".join(f"- [{i}] {titles.get(i, '')}".rstrip() for i in included_ids)
        path.write_text(
            f"# {slug}\n\n"
            f"**Pregunta:** {question}\n\n"
            "## Síntesis vigente\n\n"
            f"{narrative}\n\n"
            f"## Estudios incluidos ({len(included_ids)})\n\n{refs}\n",
            encoding="utf-8",
        )

    def _write_episodic(
        self, slug, timestamp, question, counts, included_ids, narrative, models, titles
    ) -> Path:
        path = self.root / "wiki" / "episodic" / f"{slug}-{timestamp}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        counts_md = "\n".join(f"- {k}: {v}" for k, v in dict(counts).items())
        path.write_text(
            f"# Episodio · {slug} · {timestamp}\n\n"
            f"**Pregunta:** {question}\n\n"
            f"**Modelos:** {', '.join(models) or '(n/d)'}\n\n"
            f"## Conteos PRISMA\n{counts_md}\n\n"
            f"## Síntesis\n\n{narrative}\n\n"
            f"## Incluidos\n\n"
            + "\n".join(f"- [{i}] {titles.get(i, '')}".rstrip() for i in included_ids)
            + "\n",
            encoding="utf-8",
        )
        return path

    def _write_raw(self, slug, timestamp, included_ids, extractions, titles) -> None:
        path = self.root / "raw" / f"{slug}-{timestamp}" / "incluidos.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Estudios incluidos (raw) · {slug} · {timestamp}", ""]
        for i in included_ids:
            lines.append(f"## [{i}] {titles.get(i, '')}".rstrip())
            fields = extractions.get(i, {})
            for k, v in fields.items():
                val = v.get("value") if isinstance(v, Mapping) else v
                if val:
                    lines.append(f"- **{k}:** {val}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    def _rebuild_index(self) -> None:
        events_path = self.root / "genome" / "events.jsonl"
        if not events_path.exists():
            return
        rows = []
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        lines = [
            "# Índice del cerebro de investigador",
            "",
            "| Revisión | Fecha | Incluidos | Pregunta |",
            "|---|---|---|---|",
        ]
        for r in rows:
            q = (r.get("question") or "").replace("|", "/")[:80]
            lines.append(
                f"| [{r['slug']}](wiki/semantic/{r['slug']}.md) | {r.get('timestamp', '')} "
                f"| {r.get('n_included', 0)} | {q} |"
            )
        (self.root / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── lectura de artefactos de una corrida ────────────────────────────
    @staticmethod
    def _read_extractions(run: Path) -> dict[str, dict]:
        path = run / "05_extraction" / "extractions.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        out: dict[str, dict] = {}
        for rid, rec in data.items():
            fields = rec.get("fields", {}) if isinstance(rec, dict) else {}
            out[rid] = fields
        return out

    @staticmethod
    def _read_narrative(run: Path) -> str:
        doc = run / "deliverable" / "documento.md"
        if doc.exists():
            return doc.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def _read_titles(run: Path) -> dict[str, str]:
        """Extrae ``{doi: título}`` de la bibliografía BibTeX del deliverable."""
        bib = run / "deliverable" / "referencias.bib"
        if not bib.exists():
            return {}
        import re

        titles: dict[str, str] = {}
        for block in bib.read_text(encoding="utf-8").split("@article"):
            title_m = re.search(r"title\s*=\s*\{(.+?)\}", block, re.DOTALL)
            doi_m = re.search(r"doi\s*=\s*\{(.+?)\}", block)
            if title_m and doi_m:
                titles[doi_m.group(1).strip()] = title_m.group(1).strip()
        return titles
