"""Cerebro de investigador en archivos (markdown + JSONL · sin vectores).

``ResearchBrain`` sedimenta cada revisión sistemática en una estructura de
archivos portátil que sigue el patrón de memoria del proyecto **cerebro**
(https://github.com/jhonmosquerav/cerebro, licencia MIT): capas de memoria
en markdown + un log de eventos append-only. Sin RAG, sin vectores, sin
servidores.

    <root>/
      genome/events.jsonl          # log append-only (una línea por revisión)
      wiki/semantic/<slug>.md      # síntesis vigente del tema (se sobrescribe)
      wiki/episodic/<slug>-<ts>.md # episodio: una corrida concreta
      raw/<slug>-<ts>/incluidos.md # estudios incluidos + extracción (inmutable)
      index.md                     # índice navegable de todas las revisiones

La memoria se LEE con :meth:`ResearchBrain.recall` (y el subcomando
``revisia brain``): si un slug ya tiene corridas previas, la nueva corrida
se registra como **actualización** (living review) con el delta de estudios
incluidos (nuevos / retirados) respecto a la corrida anterior.

Anti-sesgo (regla de diseño): la memoria NUNCA se inyecta en las etapas de
juicio (screening / extracción / riesgo de sesgo). Informa al investigador
humano y al reporte; no contamina las decisiones de elegibilidad. Ver
``docs/memoria-cerebro.md``.

No usa embeddings ni Docker: la recuperación es "leer el archivo". Más adelante
se puede añadir un índice vectorial local opcional (ver
:class:`revisia.rag.embed.FastEmbedEmbedder`) sin cambiar este formato.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BrainRecall:
    """Memoria recuperada de un slug: lo que ya se sabe antes de volver a correr."""

    slug: str
    n_runs: int
    last_timestamp: str
    last_counts: dict[str, Any] = field(default_factory=dict)
    last_included_ids: list[str] = field(default_factory=list)
    semantic_summary: str = ""


class ResearchBrain:
    """Memoria persistente de investigador respaldada por archivos markdown."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # ── lectura (recall) ─────────────────────────────────────────────────
    def recall(self, slug: str) -> BrainRecall | None:
        """Recupera la memoria vigente de un slug. ``None`` si no hay corridas."""
        events = self._events_for(slug)
        if not events:
            return None
        last = events[-1]
        sem = self.root / "wiki" / "semantic" / f"{slug}.md"
        return BrainRecall(
            slug=slug,
            n_runs=len(events),
            last_timestamp=str(last.get("timestamp", "")),
            last_counts=dict(last.get("counts", {})),
            last_included_ids=[str(i) for i in last.get("included_ids", [])],
            semantic_summary=sem.read_text(encoding="utf-8") if sem.exists() else "",
        )

    def summary(self) -> list[BrainRecall]:
        """Un :class:`BrainRecall` por slug conocido, en orden de aparición."""
        order: list[str] = []
        for event in self._read_events():
            slug = str(event.get("slug", ""))
            if slug and slug not in order:
                order.append(slug)
        return [recall for slug in order if (recall := self.recall(slug)) is not None]

    def _read_events(self) -> list[dict[str, Any]]:
        path = self.root / "genome" / "events.jsonl"
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def _events_for(self, slug: str) -> list[dict[str, Any]]:
        return [e for e in self._read_events() if e.get("slug") == slug]

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

        Si el slug ya tiene memoria, la corrida se registra como actualización
        (living review): el evento y el episodio llevan el delta de incluidos
        (nuevos / retirados) respecto a la corrida previa.

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
        prior = self.recall(slug)  # ANTES de escribir el evento nuevo
        if prior is not None:
            previous = set(prior.last_included_ids)
            current = set(included_ids)
            new_ids = [i for i in included_ids if i not in previous]
            dropped_ids = [i for i in prior.last_included_ids if i not in current]
        else:
            new_ids, dropped_ids = [], []
        self._append_event(
            slug, timestamp, question, counts, included_ids, models, prior, new_ids, dropped_ids
        )
        self._write_semantic(slug, question, narrative, included_ids, titles)
        episode = self._write_episodic(
            slug,
            timestamp,
            question,
            counts,
            included_ids,
            narrative,
            models,
            titles,
            prior=prior,
            new_ids=new_ids,
            dropped_ids=dropped_ids,
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
    def _append_event(
        self, slug, timestamp, question, counts, included_ids, models, prior, new_ids, dropped_ids
    ) -> None:
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
        if prior is not None:
            event["update_of"] = prior.last_timestamp
            event["included_new"] = new_ids
            event["included_dropped"] = dropped_ids
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _frontmatter(**fields: Any) -> str:
        lines = ["---"]
        for key, value in fields.items():
            lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines) + "\n\n"

    def _write_semantic(self, slug, question, narrative, included_ids, titles) -> None:
        path = self.root / "wiki" / "semantic" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        refs = "\n".join(f"- [{i}] {titles.get(i, '')}".rstrip() for i in included_ids)
        front = self._frontmatter(
            tipo="semantic",
            slug=slug,
            actualizado_utc=datetime.now(UTC).isoformat(),
            n_incluidos=len(included_ids),
            origen="revisia --brain",
        )
        path.write_text(
            front + f"# {slug}\n\n"
            f"**Pregunta:** {question}\n\n"
            "## Síntesis vigente\n\n"
            f"{narrative}\n\n"
            f"## Estudios incluidos ({len(included_ids)})\n\n{refs}\n",
            encoding="utf-8",
        )

    def _write_episodic(
        self,
        slug,
        timestamp,
        question,
        counts,
        included_ids,
        narrative,
        models,
        titles,
        *,
        prior=None,
        new_ids=None,
        dropped_ids=None,
    ) -> Path:
        path = self.root / "wiki" / "episodic" / f"{slug}-{timestamp}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        counts_md = "\n".join(f"- {k}: {v}" for k, v in dict(counts).items())
        update_md = ""
        if prior is not None:
            new_ids = new_ids or []
            dropped_ids = dropped_ids or []
            news = (
                "\n".join(f"  - [{i}] {titles.get(i, '')}".rstrip() for i in new_ids)
                or "  - (ninguno)"
            )
            drops = "\n".join(f"  - [{i}]" for i in dropped_ids) or "  - (ninguno)"
            update_md = (
                "\n## Actualización de revisión previa (living review)\n\n"
                f"- Corrida previa: {prior.last_timestamp} "
                f"({len(prior.last_included_ids)} incluidos)\n"
                f"- Nuevos incluidos ({len(new_ids)}):\n{news}\n"
                f"- Retirados ({len(dropped_ids)}):\n{drops}\n"
            )
        front = self._frontmatter(
            tipo="episodic",
            slug=slug,
            corrida=timestamp,
            creado_utc=datetime.now(UTC).isoformat(),
            n_incluidos=len(included_ids),
            origen="revisia --brain",
        )
        path.write_text(
            front + f"# Episodio · {slug} · {timestamp}\n\n"
            f"**Pregunta:** {question}\n\n"
            f"**Modelos:** {', '.join(models) or '(n/d)'}\n\n"
            f"## Conteos PRISMA\n{counts_md}\n"
            f"{update_md}\n"
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
        events = self._read_events()
        if not events:
            return
        lines = [
            "# Índice del cerebro de investigador",
            "",
            "| Revisión | Fecha | Incluidos | Pregunta |",
            "|---|---|---|---|",
        ]
        for r in events:
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
