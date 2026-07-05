"""Interfaz de línea de comandos de prisma-loop.

Subcomandos:
  * ``prisma-loop validate <dir>`` — carga y valida un protocol.yml y muestra
    el pipeline configurado (etapas, autonomía, proveedor por etapa).
  * ``prisma-loop run <dir>`` — ejecuta el pipeline end-to-end (tracer bullet),
    con checkpoints humanos. Usa ``--auto-approve`` para correrlo sin pausas.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from prisma_loop import __version__
from prisma_loop.config import STAGES, load_protocol


def _protocol_warnings(protocol, protocol_dir: str) -> list[str]:
    """Advertencias de buenas prácticas (no bloquean): evitan que una corrida
    arranque con las limitaciones típicas de una RS rápida."""
    warns: list[str] = []
    if len(protocol.databases) < 3:
        warns.append(
            f"Solo {len(protocol.databases)} base(s): añade Europe PMC / Semantic Scholar "
            "o importa RIS/BibTeX (Scopus/WoS) para cobertura PRISMA."
        )
    if "screening_ta" not in protocol.ensemble:
        warns.append(
            "screening_ta sin ensemble (un solo revisor-IA): añádelo a 'ensemble' + "
            "'ensemble_llm' con 2 modelos para diversidad y voto a recall."
        )
    if not (Path(protocol_dir) / "gold.yml").exists():
        warns.append(
            "Sin gold.yml: no se calcularán kappa/recall/lost-evidence. Crea uno "
            "(o usa 'prisma-loop gold-template <run_dir>')."
        )
    if getattr(protocol, "grounding", "embedder") == "embedder":
        warns.append(
            "grounding=embedder (léxico, NO cruza idiomas). Si revisas en un idioma "
            "distinto al de las fuentes, usa 'grounding: agent' (cross-lingual, gratis)."
        )
    return warns


def _cmd_validate(protocol_dir: str) -> int:
    protocol = load_protocol(protocol_dir)
    print(f"✓ Protocolo válido: {protocol.title}  [{protocol.slug}]")
    print(f"  Pregunta ({protocol.question.framework.value}): {protocol.question.text}")
    print(f"  Bases: {', '.join(protocol.databases) or '(ninguna declarada)'}")
    print(f"  RoB tool: {protocol.rob_tool} · Extensión: {protocol.prisma_extension}")
    if protocol.registration:
        reg = ", ".join(f"{k}={v}" for k, v in protocol.registration.items())
        print(f"  Registro: {reg}")
    print("  Pipeline:")
    for stage in STAGES:
        autonomy = protocol.autonomy_for(stage)
        try:
            prov = protocol.provider_for(stage)
            prov_desc = f"{prov.provider}:{prov.model}"
        except KeyError:
            prov_desc = "(sin proveedor)"
        ens = " [ensemble]" if stage in protocol.ensemble else ""
        print(f"    - {stage:<14} {autonomy}  {prov_desc}{ens}")
    warns = _protocol_warnings(protocol, protocol_dir)
    if warns:
        print("  Advertencias (no bloquean la corrida):")
        for w in warns:
            print(f"    ⚠ {w}")
    return 0


def _cmd_gold_template(args: argparse.Namespace) -> int:
    """Emite un gold.yml (ids cribados, comentados) para etiquetado humano."""
    import json

    run_dir = Path(args.run_dir)
    decisions = run_dir / "03_screening" / "decisions.json"
    if not decisions.exists():
        print(f"error: no se encontró {decisions}", file=sys.stderr)
        return 2
    data = json.loads(decisions.read_text(encoding="utf-8"))
    ids: list[str] = []
    seen: set[str] = set()
    for d in data:
        rid = d.get("record_id")
        if rid and rid not in seen:
            seen.add(rid)
            ids.append(rid)
    out = Path(args.out) if args.out else run_dir / "gold_template.yml"
    lines = [
        "# gold.yml · etiqueta cada id: true (incluir) / false (excluir).",
        "# Descomenta (quita '# ') las líneas que etiquetes; las comentadas se ignoran.",
        "# Copia el archivo final como gold.yml dentro de tu carpeta protocols/<slug>/.",
        "gold:",
        *(f'  # "{rid}": true' for rid in ids),
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✓ Plantilla gold con {len(ids)} ids → {out}")
    print("  Etiqueta (true/false), descomenta y cópiala como gold.yml en tu protocolo.")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from prisma_loop.orchestration.flow import run_review

    if args.brain:
        from prisma_loop.memory import ResearchBrain

        prior = ResearchBrain(args.brain).recall(load_protocol(args.protocol_dir).slug)
        if prior:
            print(
                f"🧠 Memoria previa: {prior.n_runs} corrida(s), última {prior.last_timestamp}, "
                f"{len(prior.last_included_ids)} incluidos. Esta corrida se registrará como "
                "actualización (living review)."
            )
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    result = run_review(
        args.protocol_dir,
        timestamp=timestamp,
        runs_root=args.runs_root,
        max_results=args.max,
        auto_approve=args.auto_approve,
        mailto=args.mailto,
    )
    icon = {"completed": "✓", "paused": "⏸", "rejected": "✗"}.get(result.status, "•")
    print(f"\n{icon} {result.status.upper()} · {result.message}")
    if result.run_dir:
        print(f"  Corrida: {result.run_dir}")
    if result.status == "completed":
        c = result.counts
        print(
            f"  PRISMA: identificados={c.identified} · dedup={c.duplicates_removed} "
            f"· cribados={c.screened} · incluidos={c.included}"
        )
        if result.hallucination_flagged:
            print("  ⚠ El verificador marcó posibles citas no fundamentadas: revisar.")
        print(f"  Entregable: {result.run_dir / 'deliverable'}")
        if args.brain and result.run_dir:
            from prisma_loop.memory import ResearchBrain

            ResearchBrain(args.brain).record_from_run(result.run_dir)
            print(f"  Cerebro: revisión sedimentada en {args.brain}/")
    if result.metrics is not None:
        m = result.metrics
        recall = "n/d" if m.recall is None else f"{m.recall:.2f}"
        lost = "n/d" if m.lost_evidence is None else f"{m.lost_evidence:.2f}"
        print(
            f"  Métricas (vs gold n={m.n}): recall={recall} · lost-evidence={lost} "
            f"· MCC={m.mcc:.2f} · WMCC={m.wmcc:.2f} · kappa={m.cohen_kappa:.2f}"
        )
    return 0 if result.status in {"completed", "paused"} else 1


def _cmd_brain(args: argparse.Namespace) -> int:
    """Inspecciona un cerebro de investigador (memoria markdown, solo lectura)."""
    from prisma_loop.memory import ResearchBrain

    brain = ResearchBrain(args.brain_dir)
    if args.slug:
        recall = brain.recall(args.slug)
        if recall is None:
            print(f"(sin memoria para '{args.slug}' en {args.brain_dir})")
            return 1
        print(
            f"🧠 {recall.slug} · {recall.n_runs} corrida(s) · última {recall.last_timestamp} "
            f"· {len(recall.last_included_ids)} incluidos"
        )
        for key, value in recall.last_counts.items():
            print(f"  - {key}: {value}")
        if recall.semantic_summary:
            print("\n--- síntesis vigente (wiki/semantic) ---\n")
            print(recall.semantic_summary)
        return 0
    recalls = brain.summary()
    if not recalls:
        print(f"(cerebro vacío o inexistente en {args.brain_dir})")
        return 1
    print(f"🧠 Cerebro en {args.brain_dir} · {len(recalls)} revisión(es):")
    for recall in recalls:
        print(
            f"  - {recall.slug}: {recall.n_runs} corrida(s), última {recall.last_timestamp}, "
            f"{len(recall.last_included_ids)} incluidos"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prisma-loop",
        description="Sistema multiagéntico reproducible para revisiones sistemáticas PRISMA.",
    )
    parser.add_argument("--version", action="version", version=f"prisma-loop {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Valida un protocol.yml y muestra el pipeline.")
    p_validate.add_argument("protocol_dir", help="Carpeta del protocolo (contiene protocol.yml).")

    p_run = sub.add_parser("run", help="Ejecuta el pipeline end-to-end (tracer bullet).")
    p_run.add_argument("protocol_dir", help="Carpeta del protocolo (contiene protocol.yml).")
    p_run.add_argument(
        "--max", type=int, default=50, help="Máx. de registros a recuperar por base."
    )
    p_run.add_argument("--runs-root", default="runs", help="Raíz de salidas (default: runs/).")
    p_run.add_argument("--mailto", default=None, help="Email para el polite pool de OpenAlex.")
    p_run.add_argument(
        "--auto-approve",
        action="store_true",
        help="Aprueba automáticamente los checkpoints humanos (demo/CI).",
    )
    p_run.add_argument(
        "--brain",
        default=None,
        help="Sedimenta la revisión en un cerebro de investigador (carpeta markdown).",
    )

    p_gold = sub.add_parser(
        "gold-template",
        help="Genera un gold.yml (ids cribados) para etiquetado humano y activar kappa.",
    )
    p_gold.add_argument("run_dir", help="Carpeta de la corrida (runs/<slug>-<fecha>).")
    p_gold.add_argument(
        "--out", default=None, help="Ruta de salida (default: <run_dir>/gold_template.yml)."
    )

    p_brain = sub.add_parser(
        "brain",
        help="Inspecciona un cerebro de investigador (memoria markdown acumulada con --brain).",
    )
    p_brain.add_argument("brain_dir", help="Carpeta del cerebro (la que pasaste a --brain).")
    p_brain.add_argument(
        "slug", nargs="?", default=None, help="Slug de una revisión (muestra su memoria)."
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "gold-template":
        return _cmd_gold_template(args)
    if args.command == "brain":
        return _cmd_brain(args)
    protocol_dir = args.protocol_dir
    if not Path(protocol_dir).exists():
        print(f"error: la carpeta {protocol_dir!r} no existe.", file=sys.stderr)
        return 2
    if args.command == "validate":
        return _cmd_validate(protocol_dir)
    if args.command == "run":
        return _cmd_run(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
