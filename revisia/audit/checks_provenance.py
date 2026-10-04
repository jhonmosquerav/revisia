"""Checks de procedencia: ``manifest``, ``provenance``, ``prompts``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.orchestration.run_context import PROVENANCE_PIPELINE

_NA_MANIFIESTO = "no aplica: el manifiesto no se pudo leer (ver `manifest`)."


def check_manifest(ctx: AuditContext) -> Verdict:
    """trAIce M2: manifiesto con las llamadas IA y los modelos usados."""
    if ctx.manifest_dict is None:
        # El motivo (YAML inválido, demasiado anidado, raíz de otro tipo…) va en la fila.
        motivo = f" ({ctx.manifest.error})" if ctx.manifest.error else ""
        return "FAIL", f"manifest.yml ausente o ilegible{motivo}: la corrida no es reproducible."
    models = ctx.manifest_dict.get("models_used") or []
    calls = ctx.llm_calls
    if models and calls:
        return "PASS", (
            f"manifest.yml con {len(calls)} llamada(s) IA y modelos: {', '.join(map(str, models))}."
        )
    if calls or models:
        return "WARN", "manifest.yml presente pero con procedencia IA incompleta."
    return "WARN", "manifest.yml sin llamadas IA registradas (¿corrida determinista/fake?)."


def check_provenance(ctx: AuditContext) -> Verdict:
    """Procedencia: la corrida la produjo el pipeline (auditoría 2026-09-03, C3)."""
    if ctx.manifest_dict is None:
        return "N/A", _NA_MANIFIESTO
    provenance = ctx.manifest_dict.get("provenance")
    if provenance == PROVENANCE_PIPELINE:
        return "PASS", (
            "El manifiesto declara `provenance: pipeline` (marca escrita por el motor; "
            "no es una firma)."
        )
    found = "ausente" if provenance is None else repr(provenance)
    return "FAIL", (
        f"Procedencia {found}: el manifiesto no declara `provenance: pipeline`. "
        "Una corrida reconstruida, o generada antes de que el motor registrara "
        "su procedencia, no es evidencia publicable: regenérala con `revisia run`."
    )


def check_prompts(ctx: AuditContext) -> Verdict:
    """trAIce M6: cada llamada con su prompt hash-eado."""
    if ctx.manifest_dict is None:
        return "N/A", _NA_MANIFIESTO
    calls = ctx.llm_calls
    hashed = [c for c in calls if c.get("prompt_sha256")]
    if calls and len(hashed) == len(calls):
        return "PASS", f"{len(hashed)}/{len(calls)} llamadas con prompt hash-eado (RunMeta)."
    if calls:
        return "WARN", f"Solo {len(hashed)}/{len(calls)} llamadas llevan prompt_hash."
    return "WARN", "Sin llamadas IA que auditar."
