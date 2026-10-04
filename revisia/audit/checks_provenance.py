"""Checks de procedencia: ``manifest``, ``provenance``, ``schemas``, ``prompts``.

``schemas`` valida cada artefacto presente contra el modelo que lo produce:
la reconstrucción de la auditoría 2026-09-03 (C3) traía un ``metrics.json``
sin matriz de confusión y un ``verification.json`` sin ``stage`` que ningún
código del motor puede escribir, y el auditor anterior los daba por buenos
porque solo miraba que existieran.

El manifiesto es entrada no confiable: ningún valor suyo se interpola en un
detalle sin pasar por ``short_text``/``short_repr`` (bomba de alias; revisiones
de la Tarea 4).
"""

from __future__ import annotations

from typing import Any

from revisia.audit.artifacts import (
    ARTIFACT_ADAPTERS,
    MANIFEST_ADAPTERS,
    AuditContext,
    Loaded,
    short_repr,
    short_text,
)
from revisia.audit.model import Verdict
from revisia.orchestration.run_context import PROVENANCE_PIPELINE
from revisia.schemas.artifacts import GATED_STAGES

_NA_MANIFIESTO = "no aplica: el manifiesto no se pudo leer (ver `manifest`)."
_MAX_ERRORES = 5
_MAX_MODELOS = 10
_LIMITE_ERROR = 300  # caracteres por artefacto con error: un `loc` hostil no llena el detalle


def _nombres(models: Any) -> str:
    """Los modelos del manifiesto en una línea, acotada en número y en longitud.

    Cada elemento pasa por ``short_text``: ``str`` de una lista anidada hostil (bomba de
    alias) cuelga el auditor, y una cadena enorme llenaría el detalle. ``models_used``
    puede no ser ni una lista (``schemas`` lo marca): entonces se muestra acotado.
    """
    if not isinstance(models, list | tuple):
        return short_text(models)
    names = ", ".join(short_text(m) for m in models[:_MAX_MODELOS])
    more = len(models) - _MAX_MODELOS
    return names + (f" (+{more} más)" if more > 0 else "")


def check_manifest(ctx: AuditContext) -> Verdict:
    """trAIce M2: manifiesto legible, con las llamadas IA y los modelos usados."""
    loaded = ctx.manifest
    if not loaded.present:
        return "FAIL", "manifest.yml ausente: la corrida no es reproducible."
    if not loaded.ok:
        # El motivo (YAML inválido, demasiado anidado, raíz de otro tipo…) va en la fila.
        return "FAIL", f"manifest.yml ilegible ({loaded.error}): la corrida no es reproducible."
    # Las del propio manifiesto (desde la Ola 1, copia de llm_calls.jsonl).
    calls = ctx.llm_calls
    if not calls:
        return "WARN", "manifest.yml sin llamadas IA registradas: no hay procedencia que auditar."
    fakes = sum(1 for c in calls if c.get("provider") == "fake")
    if fakes:
        return "WARN", (
            f"corrida de demostración, no evidencia: {fakes}/{len(calls)} llamadas con "
            "proveedor `fake`."
        )
    models = (ctx.manifest_dict or {}).get("models_used") or []
    return "PASS", (
        f"manifest.yml con {len(calls)} llamada(s) IA y modelos: "
        f"{_nombres(models) or '(sin models_used)'}."
    )


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
    # El manifiesto es entrada no confiable: `short_repr`, no `repr` (bomba de alias).
    found = "ausente" if provenance is None else short_repr(provenance)
    return "FAIL", (
        f"Procedencia {found}: el manifiesto no declara `provenance: pipeline`. "
        "Una corrida reconstruida, o generada antes de que el motor registrara "
        "su procedencia, no es evidencia publicable: regenérala con `revisia run`."
    )


def _validated(ctx: AuditContext) -> list[Loaded[Any]]:
    """Todos los artefactos presentes con modelo, ya validados.

    Sin el ledger, que tiene su propio check con número de línea. Se pide cada uno y se
    filtra por ``present``: los cargadores no lanzan, ni siquiera ante un fichero ilegible.
    """
    results: list[Loaded[Any]] = []
    if ctx.manifest.ok:
        results += [ctx.manifest_section(key) for key in MANIFEST_ADAPTERS]
    else:
        results.append(ctx.manifest)  # ausente (se descarta) o ilegible (el error se ve)
    results.append(ctx.art.run_info())
    results += [ctx.art.artifact(rel) for rel in ARTIFACT_ADAPTERS]
    for gate in GATED_STAGES:
        results.append(ctx.art.yaml(f"{gate}/review_request.yml"))
        results.append(ctx.art.decision(gate))
    return [r for r in results if r.present]


def check_schemas(ctx: AuditContext) -> Verdict:
    """PRISMA 27 / trAIce M5: cada artefacto presente valida el modelo que lo produce."""
    validated = _validated(ctx)
    errors = [
        short_text(f"{r.path}: {r.error}", limit=_LIMITE_ERROR) for r in validated if not r.ok
    ]
    if errors:
        shown = "; ".join(errors[:_MAX_ERRORES])
        more = f" (+{len(errors) - _MAX_ERRORES} más)" if len(errors) > _MAX_ERRORES else ""
        return "FAIL", (
            f"{len(errors)} artefacto(s) no cargan o no validan su modelo: {shown}{more}."
        )
    return "PASS", f"{len(validated)} artefactos validan su modelo."


def check_prompts(ctx: AuditContext) -> Verdict:
    """trAIce M6: cada llamada con el hash de su prompt y de su respuesta."""
    if ctx.manifest_dict is None:
        return "N/A", _NA_MANIFIESTO
    calls = ctx.llm_calls
    if not calls:
        return "WARN", "Sin llamadas IA que auditar."
    complete = [c for c in calls if c.get("prompt_sha256") and c.get("response_sha256")]
    if len(complete) == len(calls):
        return "PASS", (
            f"{len(calls)}/{len(calls)} llamadas con prompt_sha256 y response_sha256 (RunMeta)."
        )
    return "WARN", (
        f"{len(calls) - len(complete)}/{len(calls)} llamadas sin hash de prompt o de "
        "respuesta (ver `schemas`)."
    )
