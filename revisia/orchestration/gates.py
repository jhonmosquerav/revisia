"""Solicitudes y políticas de los gates (Ola 1, PR-D; spec 2026-10-04 §4.3 y §8).

Funciones puras. Cada ``*_payload`` construye lo que el humano revisa en un gate
(las claves propias de §4.3; ``schema_version``, ``stage`` y ``autonomy`` las
pone ``review_gate``) y cada ``*_policy`` dice qué puede y qué debe decidir.
``apply_labels`` aplica después las etiquetas de la decisión aprobada.

Ningún payload lleva rutas absolutas ni horas: su hash (``request_sha256``)
tiene que ser estable entre reanudaciones, o el gate no convergería nunca.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision

# Tope de la razón de cada miembro en la nota de la plantilla. La plantilla acota la nota
# entera (``_MAX_NOTA``, hitl.py): lo que pasa de ahí no se lee, y una razón de miles de
# caracteres no tiene por qué viajar en la política.
_MAX_RAZON = 160


def _mode(autonomy: str) -> str:
    """``label_all`` en A0 (el humano etiqueta cada registro); ``exceptions`` en A1."""
    return "label_all" if autonomy == "A0" else "exceptions"


def _votes(decision: ScreeningDecision) -> list[dict]:
    return [
        {
            "model": v.model,
            "label": v.label,
            "confidence": v.confidence,
            "rationale": v.rationale,
            "criteria_violated": list(v.criteria_violated),
        }
        for v in decision.votes
    ]


def _note(decision: ScreeningDecision) -> str:
    """Resumen de los votos para la plantilla (se sanea al escribirla).

    Primero el ``modelo: etiqueta (confianza)`` de TODOS los miembros y, detrás, sus
    razones (acotadas a ``_MAX_RAZON``). La plantilla corta la nota a 120 caracteres: con
    el ensemble sesgado a recall el voto que decide suele ser el discrepante, y si la
    razón del primer miembro iba delante el corte se lo comía (revisión de la Tarea 22).
    """
    votes = [f"{v.model}: {v.label} ({v.confidence:.2f})" for v in decision.votes]
    reasons = []
    for v in decision.votes:
        rationale = v.rationale
        if len(rationale) > _MAX_RAZON:
            rationale = rationale[: _MAX_RAZON - 1] + "…"
        criteria = f" [{', '.join(v.criteria_violated)}]" if v.criteria_violated else ""
        reasons.append(f"{v.model}: «{rationale}»{criteria}")
    if not votes:
        return ""
    return f"{' | '.join(votes)} · {' | '.join(reasons)}"


def _record_fields(record: SearchRecord | None, record_id: str) -> dict:
    """Título, año, DOI y base de un registro; sin registro, el id de título y el resto ``None``.

    Como ``ta_policy`` (``titles.get(..., record_id)``): una decisión cuyo registro falta no
    tumba la solicitud, y las dos ven el mismo corpus.
    """
    if record is None:
        return {"title": record_id, "year": None, "doi": None, "source_db": None}
    return {
        "title": record.title,
        "year": record.year,
        "doi": record.doi,
        "source_db": record.source_db,
    }


def _quality(metrics: ScreeningMetrics | None, thresholds: Mapping[str, float]) -> dict | None:
    """Calidad de la propuesta IA frente al gold y los umbrales del protocolo (D7)."""
    if metrics is None:
        return None
    recall_target = thresholds.get("recall_target")
    meets = None
    if metrics.recall is not None and recall_target is not None:
        meets = metrics.recall >= recall_target
    return {
        "recall": metrics.recall,
        "recall_target": recall_target,
        "kappa": metrics.cohen_kappa,
        "kappa_min": thresholds.get("kappa_min"),
        "gold_positives": metrics.tp + metrics.fn,
        "recall_meets_target": meets,
    }


def ta_payload(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    autonomy: str,
    metrics: ScreeningMetrics | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> dict:
    """Solicitud del gate ``screening_ta`` (spec §4.3).

    ``records`` ordenados por id, cada uno con la propuesta del ensemble y el
    voto de cada miembro; en A0 (``label_all``) todos van a ``must_label``.
    ``quality`` (``None`` sin gold) y ``ai_excluded`` le dicen al revisor, antes
    de aprobar, si un recall bajo umbral bloqueará la publicación y qué
    exclusiones de la IA tendría que etiquetar para evitarlo (D7).
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    by_id = {r.record_id: r for r in records}
    return {
        "mode": _mode(autonomy),
        "n_screened": len(decisions),
        "n_proposed_pass": sum(1 for d in decisions if d.ensemble_label in {"include", "unclear"}),
        "n_proposed_exclude": sum(1 for d in decisions if d.ensemble_label == "exclude"),
        "records": [
            {
                "record_id": d.record_id,
                **_record_fields(by_id.get(d.record_id), d.record_id),
                "proposal": d.ensemble_label,
                "votes": _votes(d),
            }
            for d in decisions
        ],
        "must_label": [d.record_id for d in decisions] if autonomy == "A0" else [],
        "quality": _quality(metrics, thresholds or {}),
        "ai_excluded": [d.record_id for d in decisions if d.ensemble_label == "exclude"],
    }


def ta_policy(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    autonomy: str,
) -> RecordPolicy:
    """Qué puede etiquetar el humano en T/A: cualquier registro cribado (D1).

    En A1 (por defecto) aprueba la propuesta con excepciones opcionales; en A0
    tiene que etiquetarlos todos.
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    titles = {r.record_id: r.title for r in records}
    hints = tuple(
        RecordHint(d.record_id, titles.get(d.record_id, d.record_id), d.ensemble_label, _note(d))
        for d in decisions
    )
    must_label = frozenset(d.record_id for d in decisions) if autonomy == "A0" else frozenset()
    return RecordPolicy(hints=hints, must_label=must_label)


def apply_labels(
    decisions: Iterable[ScreeningDecision],
    labels: Mapping[str, RecordLabel],
    actor: str | None,
) -> list[ScreeningDecision]:
    """Aplica las etiquetas explícitas de una decisión aprobada (D5).

    ``human_label``, ``human_reason`` y ``human_actor`` se escriben solo ante
    una etiqueta explícita: la aprobación en bloque deja la propuesta IA como
    "IA avalada" (``human_label = None``), para que el desglose trAIce R1 siga
    significando algo. ``final_label`` es la humana si existe; si no, la del
    ensemble (``None`` en un no recuperado sin rescate). Devuelve copias.
    """
    labeled: list[ScreeningDecision] = []
    for decision in decisions:
        new = decision.model_copy(deep=True)
        label = labels.get(decision.record_id)
        if label is not None and label.label is not None:
            new.human_label = label.label
            new.human_reason = label.reason
            new.human_actor = actor
        new.final_label = new.human_label or new.ensemble_label
        labeled.append(new)
    return labeled
