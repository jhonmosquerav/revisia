"""Checks del ledger y de la supervisión humana.

``ledger``, ``hitl``, ``request_hash`` y ``final_gate``.

El ledger es entrada no confiable como el manifiesto: los textos que trae (etapa,
acción, actor…) se acotan con ``short_text`` antes de entrar en un detalle.

Antes de la Ola 1, ``hitl`` nunca daba FAIL y una aprobación de ``--auto-approve``
en el gate final solo era WARN: una corrida sin ninguna decisión humana salía
"APTA para preparar publicación" (auditoría 2026-09-03, C1/A11). Ahora una etapa
de juicio sin decisión humana, un ``auto-approve`` en cualquier gate (D8) o un
gate final sin aprobación humana son FAIL.

Desde la Ola 1 el humano decide registro a registro en el cribado (D1): las etiquetas
del ledger, las ``human_label`` de ``decisions.json`` y los ``records`` de
``decision.yml`` tienen que coincidir (``hitl``), y cada decisión tiene que responder a
la solicitud que el humano revisó (``request_hash``, D4): el ``request_sha256`` se
recalcula desde ``review_request.yml`` y los artefactos aprobados desde el disco
(relación 15 de §4.4). Es el respaldo de la relación 13 de ``arithmetic``, que admite
líneas de diario obsoletas: lo que el humano aprobó es lo que hay en disco.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from revisia.audit.artifacts import AuditContext, short_repr, short_text
from revisia.audit.checks_flow import (
    AGREEMENT,
    ASSESSMENTS,
    DOCUMENTO,
    EXTRACTIONS,
    FT,
    TA,
    VERIFICATION,
)
from revisia.audit.model import Verdict
from revisia.config import JUDGMENT_STAGES, STAGES
from revisia.config import effective_autonomy as autonomia_aplicada
from revisia.orchestration.hitl import HumanDecision
from revisia.provenance.ledger import (
    AUTO_APPROVE_ACTOR,
    GATE_DECISION_ACTIONS,
    LEDGER_ACTIONS,
    DecisionEntry,
    is_human_actor,
)
from revisia.provenance.runmeta import canonical_sha256, sha256_text
from revisia.schemas.artifacts import GATED_STAGES, GateSummary

_NA_LEDGER = "no aplica: sin ledger legible (ver `ledger`)."
_MAX_PROBLEMAS = 5
_LIMITE_PROBLEMA = 300  # caracteres por problema mostrado
_MAX_LISTADOS = 5  # etapas o actores que se listan dentro de un problema
_MAX_IDS = 3  # ids de registro que se listan dentro de un problema (caben en `_LIMITE_PROBLEMA`)
_LIMITE_ID = 60  # caracteres de un id de registro
# Gates donde el motor escribe una `label` por registro etiquetado (spec §4.3).
_ETAPAS_DE_CRIBADO = tuple(s for s in GATED_STAGES if s.startswith("screening_"))
# Etapa de cada acción de la Ola 2 (`DecisionEntry`; spec 2026-10-18 §4.2, D3, D5, D21).
_ETAPA_DE_LA_EDICION: dict[str, str] = {
    "edit_field": "extraccion",
    "edit_domain": "rob",
    "rescue_text": "screening_ft",
}
# Decisiones por registro de cada gate de cribado (H en las reglas de `hitl`, spec §9.3).
DECISIONES_DE_CRIBADO = {"screening_ta": TA, "screening_ft": FT}
# Artefacto aprobado en bloque y su `artifact_sha256` en la solicitud (D1, spec §4.3).
ARTEFACTOS_APROBADOS = {"extraccion": EXTRACTIONS, "rob": ASSESSMENTS}
# Actor de un `decision.yml` que no declara `actor:`: un humano sin nombre. Público: `hitl`,
# `final_gate` y `grounding` dan el mismo WARN con él (revisión final de la Ola 1, E3).
ACTOR_POR_DEFECTO: str = HumanDecision.model_fields["actor"].default
# El WARN de ese actor, igual en todas las filas que lo dan.
CONSEJO_ACTOR = f"actor `{ACTOR_POR_DEFECTO}` (declara `actor:` en decision.yml)"
# Objetivo de una `flag_review`: `flag:<índice>` con dígitos ASCII (un `²` no es un índice).
_BANDERA = re.compile(r"flag:([0-9]{1,9})", re.ASCII)
# Caracteres de JSON canónico (cada alias expandido cuenta entero: cadenas, claves y separadores)
# por carácter del fichero que se admiten como mucho antes de hashear: un fichero del motor
# no es mayor que ~1,1× su YAML (medido), y una bomba de alias lo supera enseguida (ver
# `_hash_acotado`).
_BYTES_POR_CARACTER = 4
_BYTES_MINIMOS = 1_000
_ALIAS_DESMESURADOS = "estructura YAML con alias que se expanden más allá del tamaño del fichero"
_NO_ES_JSON = "valores que no son JSON"
# Claves del `detail` de un `approve`/`reject` que añade el motor y no vienen de `decision.yml`.
_CLAVES_DEL_MOTOR = frozenset({"request_sha256", "decision_sha256", "n_labels", "forced_human"})
# Entradas de la plantilla sin etiquetar: (ids de `records`, claves de `flags`).
_SinEtiquetar = tuple[tuple[str, ...], tuple[str, ...]]


def indice_de_bandera(target: str | None) -> int | None:
    """El índice de la cita de una ``flag_review`` (``flag:<n>``), o ``None`` si no lo es."""
    match = _BANDERA.fullmatch(target or "")
    return int(match.group(1)) if match else None


def _ola1(ctx: AuditContext) -> bool:
    """Corrida de la Ola 1: tiene ``run.json`` (aunque no valide; eso lo marca ``schemas``)."""
    return ctx.art.exists("run.json")


def _forzado(ctx: AuditContext) -> bool | None:
    """¿El gate final se forzó a humano por citas marcadas (M5)?

    Lo decide el verificador (``hallucination_flagged`` de ``verification.json``, lo que el
    pipeline usa como ``forced``); sin él, lo que registró el manifiesto (``final_gate``).
    ``None`` si no se puede saber.
    """
    verification = ctx.art.artifact(VERIFICATION)
    if verification.ok:
        return verification.value.hallucination_flagged
    block = ctx.manifest_section("final_gate")
    return block.value.forced_human if block.ok else None


def autonomia_efectiva_de_la_corrida(ctx: AuditContext) -> dict[str, str] | None:
    """Autonomía con la que se aplica cada gate: la del protocolo y la regla única de M5.

    Con citas marcadas el motor fuerza el gate final a humano y una A2/A3 declarada para
    ``reporte`` pasa a A1 en la solicitud, el ledger y ``manifest.autonomy_effective``
    (``config.effective_autonomy``, la misma función que usa el motor). Antes de la Tarea 15 el
    auditor tomaba la del protocolo y daba un FAIL falso en ``ledger`` a esa corrida legítima.
    El auditor no se fía del manifiesto (que es entrada no confiable): recalcula la efectiva y
    ``ledger`` la contrasta con él. Si no se sabe si el gate se forzó y ``reporte`` se declaró
    A2/A3, su efectiva no es verificable y no aparece (la causa la dan ``stage_artifacts`` o
    ``schemas``). ``None`` si no hay protocolo legible.
    """
    if ctx.protocol is None:
        return None
    autonomy = {gate: ctx.protocol.autonomy_for(gate) for gate in GATED_STAGES}
    forced = _forzado(ctx)
    declared = autonomy["reporte"]
    if forced is None:
        if autonomia_aplicada(declared, forced_human=True) != declared:
            del autonomy["reporte"]
    else:
        autonomy["reporte"] = autonomia_aplicada(declared, forced_human=forced)
    return autonomy


def _limitar(problems: list[str]) -> str:
    shown = "; ".join(short_text(p, limit=_LIMITE_PROBLEMA) for p in problems[:_MAX_PROBLEMAS])
    more = len(problems) - _MAX_PROBLEMAS
    return shown + (f" (+{more} más)" if more > 0 else "")


def _ids(items: Iterable[object]) -> str:
    """Hasta ``_MAX_IDS`` ids del ledger o de un artefacto, ordenados y acotados, y cuántos más."""
    ordered = sorted(set(items), key=lambda item: (item is None, str(item)))
    shown = ", ".join(short_text(item, limit=_LIMITE_ID) for item in ordered[:_MAX_IDS])
    more = len(ordered) - _MAX_IDS
    return shown + (f" (+{more} más)" if more > 0 else "")


def _clave(value: object) -> object:
    """Un valor del ``detail`` del ledger usable como clave: el ``detail`` es un mapa libre y un
    hash que llega como lista o mapa no es hashable (y no debe reventar el check). Su ``repr``
    acotado (``short_repr``) cuesta poco aunque venga anidado cientos de niveles."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return ("no es un hash", short_repr(value))


def _hash(entry: DecisionEntry, key: str) -> str | None:
    """``detail[key]`` si es texto; cualquier otra cosa no es un hash del motor."""
    value = entry.detail.get(key)
    return value if isinstance(value, str) else None


def _relacion_16(entries: tuple[tuple[int, DecisionEntry], ...]) -> list[str]:
    """Relación 16 de §4.4 y las etapas de §4.3.

    Las ``label`` y ``flag_review`` de una decisión se escriben antes de su ``approve`` y nunca
    acompañan a un ``reject`` (``review_gate`` no aplica etiquetas al rechazar); la tupla
    ``(stage, action, target, request_sha256, decision_sha256)`` es única (el motor no repite una
    entrada al reanudar). Una ``label`` solo existe en los gates de cribado y una
    ``flag_review`` solo en ``reporte``. Las entradas sin ``request_sha256`` (ledger anterior a la
    Ola 1) no entran en la unicidad: entonces no había tuplas.

    Las acciones de la Ola 2 siguen la misma regla (``DecisionEntry``; spec 2026-10-18 §4.2, D3,
    D5, D21): ``edit_field`` solo en ``extraccion``, ``edit_domain`` solo en ``rob`` y
    ``rescue_text`` solo en ``screening_ft``, antes de su ``approve`` y nunca con un ``reject``
    (revisión final de PR-0: antes pasaban en cualquier etapa y orden).
    """
    problems: list[str] = []
    cierres: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for number, entry in entries:
        sha = _hash(entry, "decision_sha256")
        if entry.action in GATE_DECISION_ACTIONS and sha is not None:
            cierres.setdefault((entry.stage, sha), []).append((number, entry.action))
    vistas: dict[tuple[object, ...], int] = {}
    for number, entry in entries:
        request = entry.detail.get("request_sha256")
        tupla = (
            entry.stage,
            entry.action,
            entry.target,
            _clave(request),
            _clave(entry.detail.get("decision_sha256")),
        )
        if request is not None and tupla in vistas:
            problems.append(
                f"línea {number}: repite la tupla de la línea {vistas[tupla]} (relación 16)"
            )
        vistas.setdefault(tupla, number)
        if entry.action not in ("label", "flag_review", *_ETAPA_DE_LA_EDICION):
            continue
        accion, etapa = short_text(entry.action), short_text(entry.stage)
        if entry.action == "label" and entry.stage not in _ETAPAS_DE_CRIBADO:
            problems.append(
                f"línea {number}: `label` en `{etapa}` (solo en los gates de cribado, §4.3)"
            )
        if entry.action == "flag_review" and entry.stage != "reporte":
            problems.append(f"línea {number}: `flag_review` en `{etapa}` (solo en `reporte`, §4.3)")
        propia = _ETAPA_DE_LA_EDICION.get(entry.action)
        if propia is not None and entry.stage != propia:
            problems.append(f"línea {number}: `{accion}` en `{etapa}` (solo en `{propia}`, §4.3)")
        sha = _hash(entry, "decision_sha256")
        decidida = cierres.get((entry.stage, sha), []) if sha is not None else []
        if any(action == "reject" for _, action in decidida):
            problems.append(f"línea {number}: `{accion}` acompaña a un `reject` (relación 16)")
        elif decidida and min(n for n, _ in decidida) < number:
            problems.append(f"línea {number}: `{accion}` después de su `approve` (relación 16)")
    return problems


def _autonomia_del_manifiesto(ctx: AuditContext, autonomy: dict[str, str]) -> list[str]:
    """``manifest.autonomy_effective`` es la efectiva que recalcula el auditor (spec §4.3).

    El motor la escribe en todo manifiesto de la Ola 1: sin ella, el manifiesto no dice con qué
    autonomía se aplicó cada gate. Si no valida, el FAIL lo da ``schemas``.
    """
    if not _ola1(ctx) or ctx.manifest_dict is None:
        return []
    registered = ctx.manifest_section("autonomy_effective")
    if not registered.present:
        return ["manifest.yml sin `autonomy_effective` (el motor lo escribe desde la Ola 1)"]
    if not registered.ok:
        return []
    problems: list[str] = []
    distintas = [
        g for g in GATED_STAGES if g in autonomy and registered.value.get(g) != autonomy[g]
    ]
    if distintas:
        problems.append(
            "manifest.autonomy_effective ≠ la efectiva (protocolo + M5) en " + ", ".join(distintas)
        )
    ajenas = sorted(set(registered.value) - set(GATED_STAGES))
    if ajenas:
        problems.append(
            f"manifest.autonomy_effective con etapas que no son gates: {_listar(ajenas)}"
        )
    return problems


_NA_SIN_GATES_DECIDIDOS = (
    "no aplica: corrida {estado}, ningún gate decidido todavía (el ledger se crea con la primera "
    "decisión; `final_gate` da el FAIL de la pausa)."
)


def _sin_gates_decididos(ctx: AuditContext) -> bool:
    """La corrida está detenida en o antes del primer gate y ningún gate se decidió aún.

    Entonces el ledger legítimamente no existe (o está vacío): se crea con la primera decisión.
    Un ledger ausente en una pausa posterior, o en una corrida terminada, sí es manipulación.
    """
    pendiente = ctx.state.pending_stage
    return (
        _detenida(ctx)
        and not ctx.gates
        and pendiente in STAGES
        and STAGES.index(pendiente) <= STAGES.index(GATED_STAGES[0])
    )


def check_ledger(ctx: AuditContext) -> Verdict:
    """trAIce M8 / PRISMA 8: ledger legible, con lo que el motor escribe y en orden.

    Una línea corrupta ya no se descarta en silencio (antes, ``audit.py:85-86``)
    y una acción que ``review_gate`` nunca emite (``propose``/``exclude``/
    ``verify`` en la reconstrucción C3) delata un ledger escrito a mano. La autonomía de
    cada entrada es la efectiva (:func:`autonomia_efectiva_de_la_corrida`, con M5) y las etiquetas y
    adjudicaciones cumplen la relación 16. En una pausa legítima en el primer gate aún no hay
    ledger: ``N/A`` (revisión final de la Ola 1), con el FAIL de la pausa en ``final_gate``.
    """
    view = ctx.ledger
    if not view.present:
        if _sin_gates_decididos(ctx):
            return "N/A", _NA_SIN_GATES_DECIDIDOS.format(estado=ctx.state.describe())
        return "FAIL", "decisions_ledger.jsonl ausente: sin trazabilidad de decisiones."
    if view.read_error:
        return "FAIL", f"decisions_ledger.jsonl ilegible ({view.read_error})."
    if not view.entries and not view.errors:
        if _sin_gates_decididos(ctx):
            return "N/A", _NA_SIN_GATES_DECIDIDOS.format(estado=ctx.state.describe())
        return "FAIL", "decisions_ledger.jsonl vacío: sin trazabilidad de decisiones."

    problems = list(view.errors)
    for number, entry in view.entries:
        if entry.stage not in STAGES:
            problems.append(f"línea {number}: etapa desconocida `{short_text(entry.stage)}`")
        if entry.action not in LEDGER_ACTIONS:
            problems.append(
                f"línea {number}: acción `{short_text(entry.action)}` que el motor no emite"
            )

    # Los gates se deciden por primera vez en el orden de STAGES; tras un
    # rechazo se puede volver a decidir una etapa anterior (D14).
    first: dict[str, int] = {}
    for number, entry in view.entries:
        if entry.action in GATE_DECISION_ACTIONS and entry.stage in STAGES:
            first.setdefault(entry.stage, number)
    ordered = sorted(first, key=first.__getitem__)
    if ordered != sorted(ordered, key=STAGES.index):
        problems.append("gates fuera del orden de STAGES: " + " → ".join(ordered))

    autonomy = autonomia_efectiva_de_la_corrida(ctx)
    if autonomy is not None:
        for number, entry in view.entries:
            expected = autonomy.get(entry.stage)
            if expected is not None and entry.autonomy != expected:
                problems.append(
                    f"línea {number}: autonomía {short_text(entry.autonomy)} en "
                    f"`{short_text(entry.stage)}`, la efectiva es {short_text(expected)}"
                )
        problems += _autonomia_del_manifiesto(ctx, autonomy)
    problems += _relacion_16(view.entries)

    if problems:
        return "FAIL", f"{len(problems)} problema(s) en el ledger: {_limitar(problems)}."
    if autonomy is None:
        note = " (autonomía no verificable: sin protocolo legible)"
    elif "reporte" not in autonomy and any(e.stage == "reporte" for e in view.decisions):
        note = (
            " (autonomía de `reporte` no verificable: ni verification.json ni "
            "manifest.final_gate dicen si se forzó a humano)"
        )
    else:
        note = ""
    return "PASS", f"{len(view.entries)} entradas válidas, en orden{note}."


def _detenida(ctx: AuditContext) -> bool:
    """``run.json`` y el estado deducido dicen que la corrida está en pausa o interrumpida."""
    return (
        ctx.run_info is not None
        and ctx.run_info.status in ("paused", "interrupted")
        and ctx.state.status in ("paused", "interrupted")
    )


def _gates_pendientes(ctx: AuditContext) -> tuple[str, ...]:
    """Los gates que una corrida detenida tiene por decidir: el pendiente y los que le siguen.

    Tras una reinclusión D14 sobre una corrida completada (o un rechazo y una nueva decisión),
    el ledger conserva la decisión SUSTITUIDA del gate que se reabre y las de los posteriores,
    frente a artefactos que el motor ya rehízo (o rehará al reanudar). Juzgarlas daba FAIL por lo
    que ya no vale («FT en A0: … sin etiqueta humana», «responde a otra solicitud»). Es seguro:
    con la corrida detenida ``final_gate`` es siempre FAIL, así que no puede quedar publicable
    (revisión final de la Ola 1, E2a). ``()`` si la corrida no está detenida.
    """
    pendiente = ctx.state.pending_stage
    if not _detenida(ctx) or pendiente not in STAGES:
        return ()
    desde = STAGES.index(pendiente)
    return tuple(gate for gate in GATED_STAGES if STAGES.index(gate) >= desde)


def _nota_pendientes(pendientes: tuple[str, ...]) -> str:
    """Lo que se añade a un detalle cuando hay gates pendientes que no se evaluaron."""
    if not pendientes:
        return ""
    etapas = ", ".join(f"`{stage}`" for stage in pendientes)
    return f" Gates pendientes (no se evalúan hasta que se decidan de nuevo): {etapas}."


def _orden_etapa(stage: str) -> tuple[int, str]:
    """Clave de orden por ``STAGES``; una etapa desconocida (ledger hostil) va al final."""
    return (STAGES.index(stage), "") if stage in STAGES else (len(STAGES), stage)


def _listar(items: list[str]) -> str:
    """Hasta ``_MAX_LISTADOS`` elementos del ledger, acotados, y cuántos no se muestran."""
    shown = ", ".join(short_text(item) for item in items[:_MAX_LISTADOS])
    more = len(items) - _MAX_LISTADOS
    return shown + (f" (+{more} más)" if more > 0 else "")


def _excluded_human(ctx: AuditContext) -> int | None:
    """``excluded_human`` declarado (el fichero o, si no se lee, la copia del manifiesto)."""
    loaded = ctx.art.artifact("03_screening/exclusions.json")
    if loaded.ok:
        return loaded.value.excluded_human
    copy = ctx.manifest_section("exclusions")
    return copy.value.excluded_human if copy.ok else None


def de_la_decision_efectiva(ctx: AuditContext, entry: DecisionEntry) -> bool:
    """La ``label`` o ``flag_review`` ``entry`` pertenece a la decisión efectiva de su etapa.

    Tras un fallo con el ``decision.yml`` cambiado, o tras un rechazo y una nueva decisión
    (D14), el ledger conserva las entradas de las decisiones sustituidas: cuentan
    solo las que llevan el ``decision_sha256`` **y** el ``request_sha256`` de la aprobación
    efectiva. Es la regla de ``n_labels`` de ``summarize_gates`` (mismo ``decision_sha256``)
    más una exigencia: ``summarize_gates`` no mira la solicitud y el auditor sí. Sin decisión
    efectiva en la etapa, ninguna cuenta. Lo usan ``hitl`` (etiquetas por registro),
    ``request_hash``, ``final_gate`` y ``grounding`` (adjudicaciones de citas), para que una
    sola regla evite que se contradigan.
    """
    gate = ctx.gates.get(entry.stage)
    if gate is None:
        return False
    decision = entry.detail.get("decision_sha256")
    if gate.decision_sha256 is None:
        # Ledger anterior a PR-D (fase 1): ni la aprobación ni las `label` llevan hashes y no
        # hay cómo distinguir decisiones, así que cuentan todas las de la etapa. Una `label`
        # con hash frente a una aprobación sin él es de otra decisión.
        return decision is None
    return (
        decision == gate.decision_sha256
        and entry.detail.get("request_sha256") == gate.request_sha256
    )


def _etiquetas_de_cribado(ctx: AuditContext) -> tuple[list[DecisionEntry], list[DecisionEntry]]:
    """``label`` de los gates de cribado: (las de la decisión efectiva, las ajenas a ella)."""
    propias: list[DecisionEntry] = []
    ajenas: list[DecisionEntry] = []
    for entry in ctx.ledger.decisions:
        if entry.action == "label" and entry.stage in _ETAPAS_DE_CRIBADO:
            (propias if de_la_decision_efectiva(ctx, entry) else ajenas).append(entry)
    return propias, ajenas


def _es_exclusion_humana(label: DecisionEntry) -> bool:
    """La ``label`` excluye el registro y la puso un humano (``human:<nombre>``).

    Solo estas respaldan el ``excluded_human`` de ``exclusions.json`` (C3): una ``label`` de un
    agente o de ``auto-approve (demo)``, o una que incluye, no cuenta como exclusión humana.
    «Humano» es ``is_human_actor``, la definición única del motor (PR-D): un ``human:`` sin
    nombre visible no dice quién decidió.
    """
    return label.detail.get("to") == "exclude" and is_human_actor(label.actor)


def _etiquetas_por_registro(ctx: AuditContext, gate: GateSummary) -> list[str]:
    """D1/D5 en un gate de cribado aprobado por un humano (spec §9.3, ``hitl`` fase 2).

    L = ``{target: (to, reason)}`` de las ``label`` de la decisión efectiva, H = ``human_label``
    (con ``human_reason``) de ``decisions.json`` y D = ``records`` de ``decision.yml``: L = H = D,
    sin dos etiquetas que choquen, cada una del actor del ``approve``, con ``from`` = la propuesta
    de la IA (``ensemble_label``) y su ``human_actor`` el del ``approve``. Que ``decisions.json``
    lleve una ``human_label`` sin su ``label`` en el ledger es lo que haría quien quisiera bajar a
    WARN un recall bajo (D7) sin que un humano revisara nada.
    """
    stage = gate.stage
    rel = DECISIONES_DE_CRIBADO[stage]
    loaded = ctx.art.artifact(rel)
    if not loaded.ok:
        estado = "ausente" if not loaded.present else "inválido"
        return [
            f"`{stage}`: {rel} {estado}: las etiquetas por registro no se pueden contrastar "
            "(ver `stage_artifacts` y `schemas`)"
        ]
    decisions = {d.record_id: d for d in loaded.value}
    problems: list[str] = []
    etiquetas: dict[str | None, tuple[Any, Any]] = {}
    chocan: list[str | None] = []
    otro_actor: list[str | None] = []
    otro_from: list[str | None] = []
    otra_razon: list[str | None] = []
    for entry in ctx.ledger.decisions:
        if entry.stage != stage or entry.action != "label":
            continue
        if not de_la_decision_efectiva(ctx, entry):
            continue
        target = entry.target
        valor = (entry.detail.get("to"), entry.detail.get("reason"))
        if target in etiquetas and etiquetas[target] != valor:
            chocan.append(target)
        etiquetas[target] = valor
        if entry.actor != gate.actor:
            otro_actor.append(target)
        decision = decisions.get(target) if isinstance(target, str) else None
        if decision is not None:
            if entry.detail.get("from") != decision.ensemble_label:
                otro_from.append(target)
            if entry.detail.get("reason") != decision.human_reason:
                otra_razon.append(target)
    actor = short_text(gate.actor)
    if chocan:
        problems.append(f"`{stage}`: etiquetas que chocan para {_ids(chocan)}")
    if otro_actor:
        problems.append(
            f"`{stage}`: etiquetas de otro actor que el del `approve` ({actor}): {_ids(otro_actor)}"
        )
    if otro_from:
        problems.append(f"`{stage}`: `from` ≠ ensemble_label de la IA: {_ids(otro_from)}")
    if otra_razon:
        problems.append(f"`{stage}`: razón de la etiqueta ≠ human_reason: {_ids(otra_razon)}")
    humanas = {rid: d.human_label for rid, d in decisions.items() if d.human_label is not None}
    del_ledger = {target: to for target, (to, _) in etiquetas.items()}
    distintas = [
        k for k in del_ledger.keys() | humanas.keys() if del_ledger.get(k) != humanas.get(k)
    ]
    if distintas:
        problems.append(
            f"`{stage}`: etiquetas del ledger ≠ human_label de decisions.json: {_ids(distintas)}"
        )
    sin_actor = [
        rid
        for rid, d in decisions.items()
        if d.human_label is not None and d.human_actor != gate.actor
    ]
    if sin_actor:
        problems.append(
            f"`{stage}`: human_actor ≠ actor del `approve` ({actor}): {_ids(sin_actor)}"
        )
    decision_file = ctx.art.decision(stage)
    if decision_file.ok and isinstance(decision_file.value, HumanDecision):
        escritas = {
            rid: (r.label, r.reason)
            for rid, r in decision_file.value.records.items()
            if r.label is not None
        }
        distintas = [
            k for k in escritas.keys() | etiquetas.keys() if escritas.get(k) != etiquetas.get(k)
        ]
        if distintas:
            problems.append(
                f"`{stage}`: etiquetas del ledger ≠ records de decision.yml: {_ids(distintas)}"
            )
    if stage == "screening_ft":
        problems += _reglas_ft(ctx, gate, list(decisions.values()))
    return problems


def _reglas_ft(ctx: AuditContext, gate: GateSummary, decisions: list[Any]) -> list[str]:
    """Lo que solo resuelve un humano a texto completo (D1, D2, D9; relación 7 de §4.4).

    En A0 cada recuperado lleva etiqueta humana; ningún ``unclear`` queda sin resolver; una
    exclusión humana lleva razón (va a la lista 16b); un no recuperado sin rescate no tiene
    ``final_label`` y un rescate lleva razón. La autonomía es la del protocolo (el gate de
    texto completo nunca se fuerza); sin protocolo legible, la del ledger.
    """
    problems: list[str] = []
    autonomy = (autonomia_efectiva_de_la_corrida(ctx) or {}).get("screening_ft", gate.autonomy)
    sin_etiqueta = [
        d.record_id for d in decisions if d.fulltext_status == "retrieved" and d.human_label is None
    ]
    if autonomy == "A0" and sin_etiqueta:
        problems.append(
            f"FT en A0: {len(sin_etiqueta)} recuperado(s) sin etiqueta humana: {_ids(sin_etiqueta)}"
        )
    unclear = [d.record_id for d in decisions if d.final_label == "unclear"]
    if unclear:
        problems.append(f"FT: `unclear` sin resolver por un humano: {_ids(unclear)}")
    sin_razon = [
        d.record_id
        for d in decisions
        if d.human_label == "exclude" and not (d.human_reason or "").strip()
    ]
    if sin_razon:
        problems.append(f"FT: exclusión humana sin razón: {_ids(sin_razon)}")
    no_recuperados = [d for d in decisions if d.fulltext_status == "not_retrieved"]
    sin_rescate = [
        d.record_id for d in no_recuperados if d.human_label is None and d.final_label is not None
    ]
    if sin_rescate:
        problems.append(
            f"FT: no recuperado(s) con final_label sin rescate humano: {_ids(sin_rescate)}"
        )
    rescate_sin_razon = [
        d.record_id
        for d in no_recuperados
        if d.human_label is not None and not (d.human_reason or "").strip()
    ]
    if rescate_sin_razon:
        problems.append(f"FT: rescate sin razón: {_ids(rescate_sin_razon)}")
    return problems


def check_hitl(ctx: AuditContext) -> Verdict:
    """trAIce M8/R1 / PRISMA 8: decide un humano en cada etapa de juicio.

    Una etapa de juicio con decisión efectiva debe tenerla de un humano (``is_human_actor``:
    ``human:`` y un nombre visible, la misma regla que aplica el motor) y con
    su ``review_request.yml`` (si no, no pasó por el gate: así era la reconstrucción
    C3); si falta una y hay otra posterior, se saltó un gate. Cualquier
    ``auto-approve (demo)`` del ledger es FAIL (D8). Además, las exclusiones humanas
    que declara ``exclusions.json`` no pueden superar las ``label`` ``exclude`` de la
    decisión efectiva de cada gate de cribado: la vía contra el ``excluded_human: 3``
    de C3, que funciona aunque falte ``decisions.json``.

    En una corrida de la Ola 1 (con ``run.json``), cada gate de cribado aprobado por un humano
    cumple además las reglas por registro (:func:`_etiquetas_por_registro`). Una corrida v0.7
    se audita por etapa: sus decisiones no tenían registros y su FAIL de publicabilidad ya lo
    da ``protocol_snapshot`` (D13); repetirlo aquí no diría nada nuevo.
    """
    view = ctx.ledger
    if not view.entries:
        return "N/A", _NA_LEDGER
    fails: list[str] = []
    warns: list[str] = []

    if view.errors:
        # Una línea ilegible puede ser un `reject` o un `auto-approve`: la decisión
        # efectiva no es verificable (la causa está en `ledger`).
        fails.append(
            f"{len(view.errors)} línea(s) ilegible(s) en el ledger: no se puede saber quién decidió"
        )

    auto = sorted(
        {e.stage for e in view.decisions if e.actor == AUTO_APPROVE_ACTOR}, key=_orden_etapa
    )
    if auto:
        fails.append(
            f"decisiones de `{AUTO_APPROVE_ACTOR}` en {_listar(auto)} "
            "(D8: --auto-approve no es revisión humana)"
        )

    pendientes = _gates_pendientes(ctx)
    humanas: list[GateSummary] = []
    for stage in JUDGMENT_STAGES:
        if stage in pendientes:
            continue  # se decide de nuevo al reanudar: su decisión de ahora está sustituida
        gate = ctx.gates.get(stage)
        if gate is None:
            later = [g for g in GATED_STAGES[GATED_STAGES.index(stage) + 1 :] if g in ctx.gates]
            if later:
                fails.append(f"gate saltado: `{stage}` sin decisión y `{later[0]}` decidida")
            elif stage in ctx.state.reached:
                fails.append(f"`{stage}` alcanzada sin decisión")
            continue
        if not is_human_actor(gate.actor):
            fails.append(
                f"`{stage}`: decisión efectiva de `{short_text(gate.actor)}` "
                f"({short_text(gate.action)}), no humana"
            )
            continue
        humanas.append(gate)
        if stage not in ctx.requests:
            fails.append(
                f"`{stage}`: decisión humana sin solicitud (falta `{stage}/review_request.yml`)"
            )
        elif gate.actor == ACTOR_POR_DEFECTO:
            warns.append(f"`{stage}`: {CONSEJO_ACTOR}")

    propias, ajenas = _etiquetas_de_cribado(ctx)
    declared = _excluded_human(ctx)
    # Registros distintos: la tupla de una etiqueta es única en una decisión (spec §4.3).
    respaldadas = len(
        {(e.stage, e.target) for e in propias if _es_exclusion_humana(e) and e.target}
    )
    if declared is not None and declared > respaldadas:
        otras = sum(1 for e in ajenas if e.detail.get("to") == "exclude")
        fails.append(
            f"exclusions.json declara {short_text(declared)} exclusiones humanas "
            f"y el ledger solo registra {respaldadas} etiqueta(s) `exclude` de la decisión "
            "efectiva de cada gate de cribado"
            + (
                f" (además, {otras} etiqueta(s) `exclude` ajenas a esa decisión no cuentan)"
                if otras
                else ""
            )
        )

    # Por registro (Ola 1): van al final porque pueden ser muchos y lo de arriba (quién decidió,
    # C3) es lo primero que tiene que leer quien abre el informe.
    if _ola1(ctx):
        for gate in humanas:
            if gate.stage in DECISIONES_DE_CRIBADO and gate.action == "approve":
                fails += _etiquetas_por_registro(ctx, gate)

    nota = _nota_pendientes(pendientes)
    if fails:
        return "FAIL", f"{_limitar(fails)}.{nota}"
    if warns:
        return "WARN", f"{_limitar(warns)}.{nota}"
    if not humanas:
        # Ni una etapa de juicio decidida (una corrida que se detuvo en el primer gate):
        # `final_gate` da el FAIL de la pausa.
        return "N/A", ctx.state.na_detail()
    actores = sorted({g.actor for g in humanas})
    return "PASS", (
        f"decisión humana en {len(humanas)} etapa(s) de juicio alcanzada(s) "
        f"({_listar(actores)}); {len(propias)} etiqueta(s) por registro.{nota}"
    )


# ── request_hash: relación 15 ─────────────────────────────────────────


def _caracteres_json(texto: str, memo: dict[int, int]) -> int:
    """Caracteres que ocupa ``texto`` en el JSON canónico (comillas y escapes incluidos).

    Una cadena anclada llega a muchos lugares como el mismo objeto: se mide una vez (por
    ``id``; todos los objetos viven mientras dura el recorrido de ``_cabe_en_el_fichero``).
    """
    coste = memo.get(id(texto))
    if coste is None:
        coste = memo[id(texto)] = len(json.dumps(texto, ensure_ascii=False))
    return coste


def _caracteres_de_escalar(valor: object, memo: dict[int, int]) -> int:
    """Caracteres que ocupa un escalar (o una clave) en el JSON canónico, por exceso."""
    if isinstance(valor, str):
        return _caracteres_json(valor, memo)
    if valor is None or isinstance(valor, bool):
        return 5
    if isinstance(valor, int):
        return valor.bit_length() * 30103 // 100000 + 2  # cifras decimales, sin construirlas
    if isinstance(valor, float):
        return 24
    # Lo que no es JSON (una fecha, un conjunto…) y ningún contenedor: `canonical_sha256` lo
    # rechazará. Las tuplas de `!!pairs` y `!!omap` son contenedores: se vuelcan como arrays.
    return 32


def _cabe_en_el_fichero(value: object, *, texto: str) -> bool:
    """¿El JSON canónico de ``value`` cabe en ``_BYTES_POR_CARACTER`` veces el fichero ``texto``?

    Una bomba de alias YAML carga en milisegundos porque PyYAML comparte los nodos, pero
    volcarla a JSON expande cada alias: ``*a`` nueve veces por nivel son 9**10 hojas, y una
    cadena anclada de 24 KB referenciada 2 500 veces son 60 MB en un fichero de 30 KB, con
    pocos nodos. Contar nodos no la ve: se cuentan los caracteres de JSON de cada visita
    (cadenas y claves enteras, más separadores), contra un tope proporcional al tamaño del
    fichero. Las tuplas de ``!!pairs`` y ``!!omap`` se recorren como listas: el JSON canónico
    las vuelca como arrays. Un fichero del motor no es mayor que ~1,1× su YAML (medido); la
    única excepción es la lista que FT en A1 comparte por alias entre ``must_label`` y
    ``must_resolve``, que su JSON duplica (~2×, medido) y que sigue dentro del tope. Cada visita
    cuesta lo que carga, así que el recorrido (iterativo) y la memoria que usa son del orden del
    tope, no de la expansión.
    """
    presupuesto = _BYTES_POR_CARACTER * len(texto) + _BYTES_MINIMOS
    memo: dict[int, int] = {}
    gastado = 0
    pendientes: list[object] = [value]
    while pendientes:
        actual = pendientes.pop()
        if isinstance(actual, dict):
            gastado += 2
            for clave, valor in actual.items():
                gastado += _caracteres_de_escalar(clave, memo) + 2  # los dos puntos y la coma
                pendientes.append(valor)
        elif isinstance(actual, list | tuple):
            gastado += 2 + len(actual)  # corchetes y comas
            pendientes.extend(actual)
        else:
            gastado += _caracteres_de_escalar(actual, memo)
        if gastado > presupuesto:
            return False
    return True


def _hash_acotado(value: object, *, texto: str) -> tuple[str | None, str]:
    """``(canonical_sha256(value), "")`` o ``(None, motivo)``, sin colgar, sin agotar la memoria
    y sin lanzar.

    ``value`` se cargó de ``texto``. Si su JSON no cabe en el tamaño del fichero
    (:func:`_cabe_en_el_fichero`), no se hashea. Tampoco si el valor no es JSON (una fecha YAML
    sin comillas, un ``NaN``, un entero de miles de cifras, claves de tipos mezclados): no se
    puede atar a un hash.
    """
    if not _cabe_en_el_fichero(value, texto=texto):
        return None, _ALIAS_DESMESURADOS
    try:
        return canonical_sha256(value), ""
    except (TypeError, ValueError, RecursionError, OverflowError):
        return None, _NO_ES_JSON


def _solicitud(ctx: AuditContext, stage: str) -> tuple[dict | None, list[str]]:
    """La solicitud de ``stage`` sin su ``request_sha256``, y lo que falla al recalcularlo."""
    rel = f"{stage}/review_request.yml"
    loaded = ctx.art.yaml(rel)
    if not loaded.ok:
        return None, [f"`{rel}` ilegible ({short_text(loaded.error)})"]
    request = dict(loaded.value)
    declared = request.pop("request_sha256", None)
    texto = ctx.art.text(rel).value or ""
    recalculado, motivo = _hash_acotado(request, texto=texto)
    problems: list[str] = []
    if recalculado is None:
        problems.append(
            f"`{stage}`: el contenido de la solicitud no se puede hashear ({motivo}): no "
            "está atada a su request_sha256"
        )
    elif recalculado != declared:
        problems.append(
            f"`{stage}`: solicitud editada (su request_sha256 no es el de su contenido)"
        )
    if request.get("stage") != stage:
        problems.append(
            f"`{stage}`: la solicitud es de otra etapa ({short_text(request.get('stage'))})"
        )
    request["request_sha256"] = declared
    return request, problems


@dataclass
class _Hallazgos:
    """Lo que ``request_hash`` encuentra en una o varias decisiones.

    ``fails`` son FAIL; ``warns``, lo que no se puede comprobar sin ser una contradicción;
    ``reconstruidas``, las etapas cuyo ``decision.yml`` falta y cuya decisión se rehízo del
    ledger con el mismo hash.
    """

    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    reconstruidas: list[str] = field(default_factory=list)

    def sumar(self, otros: _Hallazgos) -> None:
        self.fails += otros.fails
        self.warns += otros.warns
        self.reconstruidas += otros.reconstruidas


def _entrada_efectiva(ctx: AuditContext, stage: str) -> DecisionEntry | None:
    """La última entrada de decisión de ``stage`` (la que reduce ``summarize_gates``)."""
    efectiva = None
    for entry in ctx.ledger.decisions:
        if entry.stage == stage and entry.action in GATE_DECISION_ACTIONS:
            efectiva = entry
    return efectiva


def _decision_del_ledger(
    ctx: AuditContext, stage: str, gate: GateSummary, sin_etiquetar: _SinEtiquetar = ((), ())
) -> HumanDecision | None:
    """La ``HumanDecision`` que el motor hasheó, rehecha solo con el ledger.

    Es lo que hace el motor al reanudar sin ``decision.yml`` (``review_gate``: el ledger manda,
    ``_from_ledger``) y es la inversa de ``_register``: ``approved`` sale de la acción, ``actor``
    del actor, ``reason`` y los campos extra del ``detail`` del ``approve`` (sin los hashes,
    ``n_labels`` ni ``forced_human``, que añade el motor), ``records`` de las ``label`` y ``flags``
    de las ``flag_review`` de la decisión efectiva (un ``reject`` no registra ninguna). Las
    entradas de ``sin_etiquetar`` (``{label: null}`` o ``{verdict: null}``) no dejan rastro en el
    ledger pero sí en el hash: son las de la plantilla que el humano no rellenó. ``None`` si el
    ledger no describe una decisión válida (una ``label`` con un valor que no existe).

    Sin ``decision.yml`` la comprobación da PASS solo si el ledger reproduce la decisión tal cual
    se hasheó. Hay casos benignos que dan WARN aunque el motor haya hecho bien su trabajo: extras
    con valor ``null`` (el ``approve`` los omite con ``exclude_none``); entradas ``{label: null,
    reason: …}`` (el ledger no registra una ``label`` sin valor, así que su ``reason`` se pierde);
    extras llamados ``n_labels`` o ``forced_human`` (el motor los sobrescribe en el ``detail`` y
    aquí se descartan); y una plantilla de la que solo se conservan algunas entradas ``null``
    (la reconstrucción prueba ninguna de ellas o todas).
    """
    entrada = _entrada_efectiva(ctx, stage)
    if entrada is None or gate.request_sha256 is None:
        return None
    aprobada = gate.action == "approve"
    records: dict[str, dict[str, Any]] = {}
    flags: dict[str, dict[str, Any]] = {}
    for entry in ctx.ledger.decisions if aprobada else ():
        if entry.stage != stage or not de_la_decision_efectiva(ctx, entry):
            continue
        if entry.action == "label" and entry.target is not None:
            records[entry.target] = {
                "label": entry.detail.get("to"),
                "reason": entry.detail.get("reason"),
            }
        elif entry.action == "flag_review" and indice_de_bandera(entry.target) is not None:
            flags[(entry.target or "").removeprefix("flag:")] = {
                "verdict": entry.detail.get("verdict"),
                "reason": entry.detail.get("reason"),
            }
    for rid in sin_etiquetar[0]:
        records.setdefault(rid, {"label": None, "reason": None})
    for indice in sin_etiquetar[1]:
        flags.setdefault(indice, {"verdict": None, "reason": None})
    extras = {k: v for k, v in entrada.detail.items() if k not in _CLAVES_DEL_MOTOR}
    try:
        return HumanDecision.model_validate(
            {
                **extras,
                "request_sha256": gate.request_sha256,
                "approved": aprobada,
                "actor": entrada.actor,
                "records": records,
                "flags": flags,
            }
        )
    except (ValueError, TypeError, RecursionError):
        return None


def _entradas_de_la_plantilla(stage: str, request: dict) -> _SinEtiquetar:
    """Las entradas que ``decision.template.yml`` trae para ``request``: un ``{label: null}`` por
    registro (cribado) y un ``{verdict: null}`` por cita a adjudicar (``reporte``)."""
    if stage in DECISIONES_DE_CRIBADO:
        ids = _ids_de_la_solicitud(request) or []
        return tuple(rid for rid in ids if rid is not None), ()
    pedidas = request.get("must_adjudicate")
    if stage == "reporte" and isinstance(pedidas, list):
        return (), tuple(str(i) for i in pedidas if isinstance(i, int) and not isinstance(i, bool))
    return (), ()


def _sin_decision_yml(
    ctx: AuditContext, stage: str, gate: GateSummary, request: dict
) -> _Hallazgos:
    """Una decisión humana sin ``decision.yml``: se rehace del ledger y se recalcula su hash.

    ``decision.yml`` es el canal de entrada del humano, no un artefacto de la corrida (spec
    §4.3): el motor reanuda aunque se borre. Si el ledger reproduce el ``decision_sha256``
    registrado, la decisión está atada igual que con el fichero (PASS con nota); si no, el hash
    no se puede comprobar, pero ausente el fichero tampoco hay contradicción que probar: WARN
    (las contradicciones del ledger las dan ``ledger``, ``hitl`` y el resto de las filas).

    Se prueba la decisión con solo lo etiquetado y, si la plantilla trae entradas, la que las deja
    en ``null`` (quien rellena ``decision.template.yml`` solo etiqueta unos pocos y el motor
    hashea el resto): que alguna dé el hash registrado prueba que es la que se hasheó.
    """
    if gate.decision_sha256 is None:
        return _Hallazgos()  # `_atada` ya dice que la decisión efectiva no lleva decision_sha256
    for sin_etiquetar in dict.fromkeys([((), ()), _entradas_de_la_plantilla(stage, request)]):
        decision = _decision_del_ledger(ctx, stage, gate, sin_etiquetar)
        if decision is None:
            continue
        try:
            sha = canonical_sha256(decision.model_dump(mode="json"))
        except (TypeError, ValueError, RecursionError, OverflowError):
            continue
        if sha == gate.decision_sha256:
            return _Hallazgos(reconstruidas=[stage])
    return _Hallazgos(
        warns=[
            f"`{stage}`: decision_sha256 no recalculable sin decision.yml (el ledger no "
            "reproduce la decisión que se hasheó; puede ser benigno: ver el docstring; o "
            "manipulación del ledger)"
        ]
    )


def _decision_yml(ctx: AuditContext, stage: str, gate: GateSummary, request: dict) -> _Hallazgos:
    """``decision.yml`` es la decisión registrada: misma solicitud, mismo hash, mismo actor.

    Si falta, la decisión se rehace del ledger (:func:`_sin_decision_yml`). Una decisión que no
    es humana (``--auto-approve``) no escribe el fichero y ``hitl`` da el FAIL (D8).
    """
    loaded = ctx.art.decision(stage)
    if not loaded.present:
        if is_human_actor(gate.actor):
            return _sin_decision_yml(ctx, stage, gate, request)
        return _Hallazgos()
    if not loaded.ok:
        return _Hallazgos(
            fails=[f"`{stage}/decision.yml` inválido ({short_text(loaded.error)}; ver `schemas`)"]
        )
    decision: HumanDecision = loaded.value
    problems: list[str] = []
    if decision.request_sha256 != request["request_sha256"]:
        problems.append(f"`{stage}`: decision.yml responde a otra solicitud")
    rel = f"{stage}/decision.yml"
    crudo = ctx.art.yaml(rel)
    sha, motivo = None, _NO_ES_JSON
    if crudo.ok and not _cabe_en_el_fichero(crudo.value, texto=ctx.art.text(rel).value or ""):
        motivo = _ALIAS_DESMESURADOS
    elif crudo.ok:
        # El motor hashea el modelo validado (`_register`), cuyo volcado convierte una fecha
        # YAML en texto: se vuelca solo tras comprobar que el crudo no expande más que el fichero.
        try:
            sha = canonical_sha256(decision.model_dump(mode="json"))
        except (TypeError, ValueError, RecursionError, OverflowError):
            sha = None
    if sha is None:
        problems.append(f"`{stage}`: decision.yml no se puede hashear ({motivo})")
    elif sha != gate.decision_sha256:
        problems.append(
            f"`{stage}`: decision.yml no es la decisión registrada en el ledger "
            "(decision_sha256 distinto)"
        )
    if decision.actor != gate.actor:
        problems.append(
            f"`{stage}`: actor de decision.yml ({short_text(decision.actor)}) ≠ "
            f"ledger ({short_text(gate.actor)})"
        )
    return _Hallazgos(fails=problems)


def _ids_de_la_solicitud(request: dict) -> list[str | None] | None:
    """Ids de ``records`` de una solicitud de cribado (``None`` donde no hay un id de texto)."""
    records = request.get("records")
    if not isinstance(records, list):
        return None
    ids = [r.get("record_id") if isinstance(r, dict) else None for r in records]
    return [rid if isinstance(rid, str) else None for rid in ids]


def _contenido(ctx: AuditContext, stage: str, gate: GateSummary, request: dict) -> list[str]:
    """Lo que la solicitud dice que se decidió es lo que hay en disco (relación 15).

    En cribado, los ids de la solicitud son los de ``decisions.json`` (un registro cribado no
    puede desaparecer como si fuera un duplicado) y las etiquetas de la decisión efectiva son de
    registros de la solicitud. En extracción y RoB, el ``artifact_sha256`` es el del artefacto
    en disco; en el reporte, el ``documento_sha256`` es el de ``documento.md`` y
    ``must_adjudicate`` son las citas marcadas de ``verification.json``. Un artefacto que no se
    lee no se compara aquí: su ausencia la marcan ``stage_artifacts`` y ``schemas``.
    """
    problems: list[str] = []
    if stage in DECISIONES_DE_CRIBADO:
        ids = _ids_de_la_solicitud(request)
        if ids is None:
            return [f"`{stage}`: solicitud sin `records` legibles"]
        rel = DECISIONES_DE_CRIBADO[stage]
        loaded = ctx.art.artifact(rel)
        if loaded.ok:
            en_disco = [d.record_id for d in loaded.value]
            if sorted(map(str, ids)) != sorted(en_disco):
                distintos = set(map(str, ids)) ^ set(en_disco)
                problems.append(
                    f"`{stage}`: ids de la solicitud ≠ ids de {rel}: "
                    f"{_ids(distintos) or 'repetidos'}"
                )
        fuera = {
            e.target
            for e in ctx.ledger.decisions
            if e.stage == stage and e.action == "label" and de_la_decision_efectiva(ctx, e)
        } - set(ids)
        if fuera:
            problems.append(f"`{stage}`: etiquetas fuera de la solicitud: {_ids(fuera)}")
    elif stage in ARTEFACTOS_APROBADOS:
        rel = ARTEFACTOS_APROBADOS[stage]
        if stage == "extraccion":
            problems += _acuerdo_de_la_solicitud(ctx, request)
        if "artifact_sha256" not in request:
            problems.append(f"`{stage}`: la solicitud no lleva artifact_sha256")
        else:
            loaded = ctx.art.json(rel)
            if loaded.ok:
                sha, motivo = _hash_acotado(loaded.value, texto=ctx.art.text(rel).value or "")
                if sha is None:
                    problems.append(f"`{stage}`: {rel} no se puede hashear ({motivo})")
                elif sha != request["artifact_sha256"]:
                    problems.append(
                        f"`{stage}`: {rel} no es el artefacto aprobado (su hash no es el "
                        "artifact_sha256 de la solicitud)"
                    )
    elif stage == "reporte":
        problems += _contenido_del_reporte(ctx, request)
    return problems


# Campos de `agreement.json` que la solicitud de extracción copia en `second_extraction`.
_CAMPOS_ACUERDO = ("n_studies", "n_field_pairs", "value_agreement", "presence_kappa")


def _acuerdo_de_la_solicitud(ctx: AuditContext, request: dict) -> list[str]:
    """``agreement.json`` es el acuerdo que vio el humano al aprobar la extracción (E5, FG5).

    La solicitud de ``extraccion`` (hasheada en ``request_sha256``) copia el acuerdo entre
    extractores en ``second_extraction``; ``agreement.json`` y su copia del manifiesto se podían
    editar a la vez sin que nada lo viera (la relación de copias solo los compara entre sí). Un
    ``agreement.json`` sin ese bloque, o el bloque sin el fichero, tampoco salen del motor. Sin la
    clave en la solicitud no se compara (una solicitud anterior a PR-D).
    """
    if "second_extraction" not in request:
        return []
    bloque = request["second_extraction"]
    loaded = ctx.art.json(AGREEMENT)
    if bloque is None:
        if loaded.present:
            return [f"`extraccion`: {AGREEMENT} existe y la solicitud no tiene `second_extraction`"]
        return []
    if not loaded.present:
        return [f"`extraccion`: la solicitud tiene `second_extraction` y falta {AGREEMENT}"]
    if not loaded.ok or not isinstance(loaded.value, dict) or not isinstance(bloque, dict):
        return []  # ilegible o con otra forma: lo marca `schemas`
    distintos = [c for c in _CAMPOS_ACUERDO if loaded.value.get(c) != bloque.get(c)]
    if distintos:
        return [
            f"`extraccion`: {AGREEMENT} no es el acuerdo de la solicitud aprobada "
            f"(`second_extraction`; distinto en {', '.join(distintos)})"
        ]
    return []


def _contenido_del_reporte(ctx: AuditContext, request: dict) -> list[str]:
    problems: list[str] = []
    if "documento_sha256" not in request:
        problems.append("`reporte`: la solicitud no lleva documento_sha256")
    else:
        documento = ctx.art.text(DOCUMENTO)
        if documento.ok and sha256_text(documento.value) != request["documento_sha256"]:
            problems.append(
                f"`reporte`: {DOCUMENTO} no es el documento aprobado (su hash no es el "
                "documento_sha256 de la solicitud)"
            )
    verification = ctx.art.artifact(VERIFICATION)
    if verification.ok:
        marcadas = verification.value.flagged_indices()
        pedidas = request.get("must_adjudicate")
        if pedidas != marcadas:
            problems.append(
                f"`reporte`: must_adjudicate {short_text(pedidas)} ≠ citas marcadas de "
                f"{VERIFICATION} {short_text(marcadas)}"
            )
    return problems


def _n_labels(ctx: AuditContext, stage: str) -> list[str]:
    """El ``n_labels`` del ``approve`` o ``reject`` es el número de ``label`` de su decisión.

    El motor escribe ``n_labels = len(labels)`` en la decisión (``_register``) y una ``label``
    por etiqueta antes de ella (spec §4.3): contar las del ledger (``summarize_gates`` cuenta por
    ``decision_sha256``; aquí, además, con su solicitud) y contrastarlas con lo declarado delata
    una etiqueta borrada o añadida al ledger a mano, también cuando no hay ``decisions.json``.
    """
    entrada = _entrada_efectiva(ctx, stage)
    if entrada is None:
        return []
    declarado = entrada.detail.get("n_labels")
    reales = sum(
        1
        for e in ctx.ledger.decisions
        if e.stage == stage and e.action == "label" and de_la_decision_efectiva(ctx, e)
    )
    if type(declarado) is int and declarado == reales:
        return []
    return [
        f"`{stage}`: la decisión declara n_labels={short_repr(declarado)} y el ledger tiene "
        f"{reales} etiqueta(s) de esa decisión"
    ]


def _atada(ctx: AuditContext, stage: str, gate: GateSummary) -> _Hallazgos:
    """Relación 15 para la decisión efectiva ``gate`` de ``stage``."""
    request, problems = _solicitud(ctx, stage)
    hallazgos = _Hallazgos(fails=problems)
    if request is None:
        return hallazgos
    declared = request["request_sha256"]
    if gate.request_sha256 != declared:
        problems.append(f"`{stage}`: la decisión efectiva responde a otra solicitud")
    if gate.decision_sha256 is None:
        problems.append(f"`{stage}`: la decisión efectiva no lleva decision_sha256")
    else:
        # Una entrada con el `decision_sha256` de la decisión efectiva y otra solicitud: o se
        # editó la entrada o la decisión no es la que se registró (`de_la_decision_efectiva` ya
        # no la cuenta, y `hitl` ve la etiqueta que falta).
        ajenas = [
            e.target
            for e in ctx.ledger.decisions
            if e.stage == stage
            and e.action in ("label", "flag_review")
            and e.detail.get("decision_sha256") == gate.decision_sha256
            and e.detail.get("request_sha256") != gate.request_sha256
        ]
        if ajenas:
            problems.append(
                f"`{stage}`: etiquetas o adjudicaciones de la decisión efectiva con otra "
                f"solicitud: {_ids(ajenas)}"
            )
        problems += _n_labels(ctx, stage)
    hallazgos.sumar(_decision_yml(ctx, stage, gate, request))
    problems += _contenido(ctx, stage, gate, request)
    return hallazgos


def check_request_hash(ctx: AuditContext) -> Verdict:
    """trAIce M8: cada decisión responde a la solicitud que se revisó (relación 15, D4).

    Por cada gate con decisión efectiva (``approve`` o ``reject``) y ``review_request.yml``: el
    ``request_sha256`` se recalcula desde el contenido de la solicitud y es el de la decisión
    efectiva, el de cada ``label``/``flag_review`` suya y el de su ``decision.yml``, que es la
    decisión registrada (``decision_sha256``) y del mismo actor; el ``n_labels`` del ``approve``
    es el número de ``label`` de esa decisión; y lo aprobado (ids, artefactos, documento, citas a
    adjudicar) es lo que hay en disco. Una solicitud editada tras aprobarla, una decisión de otra
    solicitud o un artefacto cambiado después delatan una aprobación que no es la que se
    registró.

    ``decision.yml`` es el canal de entrada: sin él (el motor reanuda igual) la decisión se
    rehace del ledger y se recalcula su hash (PASS con nota; WARN si no cuadra).

    Un gate sin ``review_request.yml`` no se mira aquí: esa decisión no pasó por el gate y el
    FAIL lo dan ``hitl`` o ``final_gate`` (la reconstrucción C3 queda con una sola vía por
    síntoma). ``auto-proceed`` (A2/A3) no escribe solicitud. Sin ``run.json`` (corrida v0.7) no
    aplica: sus decisiones no llevaban hashes y ``protocol_snapshot`` ya da el FAIL (D13).
    """
    view = ctx.ledger
    if not view.entries:
        return "N/A", _NA_LEDGER
    if not _ola1(ctx):
        return "N/A", (
            "no aplica: corrida anterior a la Ola 1 (sin run.json), sus decisiones no llevan "
            "request_sha256 (ver `protocol_snapshot`, D13)."
        )
    hallazgos = _Hallazgos()
    if view.errors:
        hallazgos.fails.append(
            f"{len(view.errors)} línea(s) ilegible(s) en el ledger: la decisión efectiva no es "
            "verificable (ver `ledger`)"
        )
    humanas = otras = 0
    pendientes = _gates_pendientes(ctx)
    for stage in GATED_STAGES:
        gate = ctx.gates.get(stage)
        if gate is None or gate.action not in ("approve", "reject") or stage not in ctx.requests:
            continue
        if stage in pendientes:
            continue  # se decide de nuevo al reanudar: la solicitud y la decisión son de antes
        hallazgos.sumar(_atada(ctx, stage, gate))
        if is_human_actor(gate.actor):
            humanas += 1
        else:
            otras += 1
    nota = _nota_pendientes(pendientes)
    if hallazgos.fails:
        return "FAIL", f"{_limitar(hallazgos.fails)}.{nota}"
    if hallazgos.warns:
        return "WARN", f"{_limitar(hallazgos.warns)}.{nota}"
    total = humanas + otras
    if total == 0:
        return "N/A", (
            "no aplica: ninguna decisión de gate con solicitud que verificar (ver `hitl` y "
            "`final_gate`)."
        )
    notas = ["hash recalculado"]
    if otras:
        notas.append(f"{otras} no humanas: ver `hitl`")
    if hallazgos.reconstruidas:
        etapas = ", ".join(f"`{s}`" for s in hallazgos.reconstruidas)
        notas.append(f"decision.yml ausente en {etapas}: reconstruida del ledger")
    resumen = "; ".join(notas)
    if otras:
        return "PASS", f"{total} decisiones atadas a su solicitud ({resumen}).{nota}"
    if humanas == 1:
        return "PASS", f"1 decisión humana atada a su solicitud ({resumen}).{nota}"
    return "PASS", f"{humanas} decisiones humanas atadas a su solicitud ({resumen}).{nota}"


# ── final_gate: relaciones 17 y 18 ────────────────────────────────────


def _relacion_17(ctx: AuditContext, gate: GateSummary) -> list[str]:
    """Relación 17 de §4.4 sobre una aprobación humana del reporte.

    ``manifest.final_gate.forced_human`` ⇔ ``hallucination_flagged``; con citas marcadas la
    decisión se forzó a humana (``forced_human`` en el ``approve``) y cada cita marcada tiene una
    ``flag_review`` de la decisión efectiva, del mismo actor, ``false_positive`` y con razón.
    Sin ``verification.json`` legible no hay nada que contrastar (lo marcan ``stage_artifacts`` y
    ``schemas``); el motor escribe ``final_gate`` en todo manifiesto de la Ola 1.
    """
    verification = ctx.art.artifact(VERIFICATION)
    if not verification.ok:
        return []
    problems: list[str] = []
    flagged = verification.value.hallucination_flagged
    block = ctx.manifest_section("final_gate")
    if block.ok:
        if block.value.forced_human != flagged:
            problems.append(
                f"manifest.final_gate.forced_human={block.value.forced_human} y "
                f"hallucination_flagged={flagged} (relación 17)"
            )
    elif not block.present and _ola1(ctx) and ctx.manifest_dict is not None:
        problems.append("manifest.yml sin `final_gate` (el motor lo escribe desde la Ola 1)")
    if gate.forced_human != flagged:
        forzada = "se forzó" if gate.forced_human else "no se forzó"
        problems.append(
            f"la decisión final {forzada} a humana (forced_human={gate.forced_human}) y "
            f"hallucination_flagged={flagged} (relación 17)"
        )
    marcadas = verification.value.flagged_indices()
    adjudicadas = {
        indice_de_bandera(e.target)
        for e in ctx.ledger.decisions
        if e.stage == "reporte"
        and e.action == "flag_review"
        and e.actor == gate.actor
        and de_la_decision_efectiva(ctx, e)
        and e.detail.get("verdict") == "false_positive"
        and isinstance(e.detail.get("reason"), str)
        and e.detail["reason"].strip()
    }
    faltan = [i for i in marcadas if i not in adjudicadas]
    if faltan:
        indices = "[" + _ids_numericos(faltan) + "]"
        problems.append(
            f"citas marcadas {indices} sin `flag_review` de {short_text(gate.actor)} en ese "
            "`approve` (relación 17)"
        )
    return problems


def _ids_numericos(items: list[int]) -> str:
    shown = ", ".join(str(i) for i in items[:_MAX_LISTADOS])
    more = len(items) - _MAX_LISTADOS
    return shown + (f" (+{more} más)" if more > 0 else "")


def _sin_terminar(ctx: AuditContext) -> str | None:
    """El ledger tiene una decisión final del reporte pero ``run.json`` no dice ``completed``.

    ``derive_state`` da ``completed`` a quien tiene un ``approve`` del reporte (así se audita
    entero), pero ese ``approve`` puede ser de una vuelta anterior: tras reincluir un registro
    en T/A la corrida se detiene de nuevo en un gate y ``run.json`` dice ``paused`` (o
    ``interrupted``, o ``running`` si el proceso murió) mientras el ledger conserva el reporte
    aprobado. Una corrida que no terminó no tiene decisión final (auditoría de la Tarea 15).
    Una corrida terminada y reanudada otra vez vuelve a ``completed`` y no entra aquí.
    """
    info = ctx.run_info
    gate = ctx.gates.get("reporte")
    if info is None or info.status == "completed":
        return None
    if gate is None or gate.action not in ("approve", "auto-proceed"):
        return None
    donde = f" en `{short_text(info.stage)}`" if info.stage else ""
    return f"run.json dice `{info.status}`{donde}: la corrida no terminó."


def _solicitud_vigente(ctx: AuditContext) -> str | None:
    """El ``request_sha256`` declarado en el ``reporte/review_request.yml`` de ahora."""
    loaded = ctx.art.yaml("reporte/review_request.yml")
    declarado = loaded.value.get("request_sha256") if loaded.ok else None
    return declarado if isinstance(declarado, str) else None


def check_final_gate(ctx: AuditContext) -> Verdict:
    """trAIce M8: el reporte final lo aprueba un humano, a través de su gate.

    Con D8, ``auto-approve`` y ``auto-proceed`` dejan de ser un WARN que no bloquea la
    publicación: son FAIL, igual que una corrida en pausa, interrumpida o rechazada y
    una aprobación humana sin ``reporte/review_request.yml`` (la decisión no pasó por
    el gate). Relación 17: con citas marcadas el gate se forzó a humano y cada cita se
    adjudicó; relación 18: ``run.json`` no dice ``completed`` sin un ``approve`` del reporte.
    """
    view = ctx.ledger
    state = ctx.state
    if not view.entries and _detenida(ctx):
        # En pausa en el primer gate el ledger aún está vacío: un `N/A` diría «no aplica» de una
        # corrida que no tiene decisión final (§9.2; revisión final de la Ola 1, E2c). Lo dice
        # `run.json`: un ledger borrado de una corrida completada sigue siendo `N/A` aquí (el
        # FAIL lo da `ledger`, sin duplicarlo).
        return "FAIL", f"corrida {state.describe()}: sin decisión final."
    if not view.entries:
        return "N/A", _NA_LEDGER
    if view.errors:
        # Tras una aprobación válida, una línea ilegible puede ser un `reject`: dar PASS
        # contradeciría el FAIL de `ledger` (revisión de la Tarea 5).
        return "FAIL", (
            f"{len(view.errors)} línea(s) ilegible(s) en decisions_ledger.jsonl: la decisión "
            "final no es verificable (ver `ledger`)."
        )
    reporte = [e for e in view.decisions if e.stage == "reporte"]
    if reporte and reporte[-1].action not in GATE_DECISION_ACTIONS | {"flag_review"}:
        last = reporte[-1]
        return "FAIL", (
            f"Acción desconocida `{short_text(last.action)}` en la decisión final "
            f"({short_text(last.actor)})."
        )

    gate = ctx.gates.get("reporte")
    # Relación 18: `run.json` dice `completed` solo si la decisión efectiva del reporte es un
    # `approve` (un rechazo final ya no se informa como completado, auditoría 2026-09-03, C1).
    completada = ctx.run_info is not None and ctx.run_info.status == "completed"
    nota = ""
    if completada and (gate is None or gate.action != "approve"):
        nota = " run.json dice `completed` sin un `approve` del reporte (relación 18)."

    if state.status in ("paused", "interrupted"):
        return "FAIL", f"corrida {state.describe()}: sin decisión final.{nota}"
    if state.status == "rejected":
        rejected = ctx.gates.get(state.pending_stage or "")
        actor = short_text(rejected.actor) if rejected is not None else "un actor desconocido"
        if state.pending_stage == "reporte":
            return "FAIL", f"El reporte final fue rechazado por {actor}.{nota}"
        return "FAIL", f"corrida {state.describe()} por {actor}: sin decisión final.{nota}"

    if gate is None:
        return "FAIL", f"Sin decisión sobre el reporte final.{nota}"
    sin_terminar = _sin_terminar(ctx)
    if sin_terminar is not None:
        return "FAIL", sin_terminar
    if gate.action != "approve" or not is_human_actor(gate.actor):
        return "FAIL", (
            f"El reporte final no lo aprobó un humano: {short_text(gate.actor)}/"
            f"{short_text(gate.action)} (D8: el gate final exige una decisión humana).{nota}"
        )
    if "reporte" not in ctx.requests:
        return "FAIL", (
            "aprobación humana sin solicitud: falta `reporte/review_request.yml` "
            "(la decisión no pasó por el gate)."
        )
    if _ola1(ctx) and gate.request_sha256 != _solicitud_vigente(ctx):
        return "FAIL", (
            "la aprobación del reporte responde a otra solicitud que la vigente "
            "(`reporte/review_request.yml`): no es la decisión final efectiva."
        )
    problems = _relacion_17(ctx, gate)
    if problems:
        return "FAIL", f"{_limitar(problems)}."
    if gate.actor == ACTOR_POR_DEFECTO:
        return "WARN", f"Reporte final aprobado por humano, pero con el {CONSEJO_ACTOR}."
    return "PASS", f"Reporte final aprobado por humano ({short_text(gate.actor)})."
