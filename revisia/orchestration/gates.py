"""Solicitudes y políticas de los gates (Ola 1, PR-D; spec 2026-10-04 §4.3 y §8).

Funciones puras. Cada ``*_payload`` construye lo que el humano revisa en un gate
(las claves propias de §4.3; ``schema_version``, ``stage`` y ``autonomy`` las
pone ``review_gate``) y cada ``*_policy`` dice qué puede y qué debe decidir.
``apply_labels`` aplica después las etiquetas de la decisión aprobada.

Ningún payload lleva rutas absolutas ni horas: su hash (``request_sha256``)
tiene que ser estable entre reanudaciones, o el gate no convergería nunca.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
from revisia.schemas.artifacts import TRANSIENT_FULLTEXT_REASONS, RetrievalOutcome
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision

# Tope de la razón de cada miembro en la nota de la plantilla. La plantilla acota la nota
# entera (``_MAX_NOTA``, hitl.py): lo que pasa de ahí no se lee, y una razón de miles de
# caracteres no tiene por qué viajar en la política.
_MAX_RAZON = 160
# Tope del id de modelo en la nota. Los votos de todos los miembros van enteros delante de las
# razones y ``_MAX_NOTA`` (hitl.py) está dimensionado para 5 votos con ids de este tamaño: un id
# más largo (``openrouter:`` + proveedor + modelo con versión) se abrevia con «…» en lugar de
# empujar el voto de otro miembro fuera de la nota.
_MAX_MODELO = 40


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


def _model(model: str) -> str:
    """El id de modelo acotado a ``_MAX_MODELO`` caracteres (con «…» si se corta)."""
    return model if len(model) <= _MAX_MODELO else model[: _MAX_MODELO - 1] + "…"


def _note(decision: ScreeningDecision) -> str:
    """Resumen de los votos para la plantilla (se sanea al escribirla).

    Primero el ``modelo: etiqueta (confianza)`` de TODOS los miembros (ids acotados a
    ``_MAX_MODELO``) y, detrás, sus razones (acotadas a ``_MAX_RAZON``). La plantilla corta
    la nota entera a ``_MAX_NOTA``: con el ensemble sesgado a recall el voto que decide
    suele ser el discrepante, así que los votos van delante y solo se corta lo que viene
    detrás, las razones (revisión de las Tareas 22 y 23). Un miembro sin razón ni criterios
    no tiene entrada en las razones.
    """
    if not decision.votes:
        return ""
    votes = " | ".join(f"{_model(v.model)}: {v.label} ({v.confidence:.2f})" for v in decision.votes)
    reasons = []
    for v in decision.votes:
        rationale = v.rationale.strip()
        if len(rationale) > _MAX_RAZON:
            rationale = rationale[: _MAX_RAZON - 1] + "…"
        parts = []
        if rationale:
            parts.append(f"«{rationale}»")
        if v.criteria_violated:
            parts.append(f"[{', '.join(v.criteria_violated)}]")
        if parts:
            reasons.append(f"{_model(v.model)}: {' '.join(parts)}")
    return f"{votes} · {' | '.join(reasons)}" if reasons else votes


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


def _threshold(thresholds: Mapping[str, float], key: str) -> float | None:
    """El umbral ``key`` o ``None`` si falta o no es finito.

    ``.nan`` y ``.inf`` son YAML válido y ``protocol.thresholds`` los acepta, pero un
    ``nan`` o ``inf`` en la solicitud rompe su hash (``canonical_sha256`` no admite no
    finitos): la corrida moriría en ``screening_ta`` y no convergería al reanudar. Un umbral
    no finito no compara nada, es como si no estuviera.
    """
    value = thresholds.get(key)
    return value if value is not None and math.isfinite(value) else None


def _quality(metrics: ScreeningMetrics | None, thresholds: Mapping[str, float]) -> dict | None:
    """Calidad de la propuesta IA frente al gold y los umbrales del protocolo (D7)."""
    if metrics is None:
        return None
    recall_target = _threshold(thresholds, "recall_target")
    meets = None
    if metrics.recall is not None and recall_target is not None:
        meets = metrics.recall >= recall_target
    return {
        "recall": metrics.recall,
        "recall_target": recall_target,
        "kappa": metrics.cohen_kappa,
        "kappa_min": _threshold(thresholds, "kappa_min"),
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


def _ft_requirements(
    decisions: list[ScreeningDecision], autonomy: str
) -> tuple[list[str], list[str], list[str]]:
    """``(must_label, must_resolve, rescuable)`` del gate de texto completo (D1, D2)."""
    retrieved = [d.record_id for d in decisions if d.fulltext_status == "retrieved"]
    unclear = [d.record_id for d in decisions if d.ensemble_label == "unclear"]
    rescuable = [d.record_id for d in decisions if d.fulltext_status == "not_retrieved"]
    must_label = retrieved if autonomy == "A0" else unclear
    return must_label, unclear, rescuable


def ft_payload(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    retrieval: Mapping[str, RetrievalOutcome],
    autonomy: str,
) -> dict:
    """Solicitud del gate ``screening_ft`` (spec §4.3).

    Un registro por informe buscado, recuperado o no. ``must_label`` son todos
    los recuperados en A0 y solo los ``unclear`` en A1; ``must_resolve``, los
    ``unclear`` (nunca pasan sin humano); ``rescuable``, los no recuperados, que
    el humano puede evaluar si consiguió el texto por otra vía (D2).

    Lleva la recuperación de cada informe (``fulltext``, ``fulltext_reason``,
    ``fulltext_source_url``): si un fallo transitorio se resuelve al reanudar, la
    solicitud cambia y una decisión escrita contra la anterior no se aplica.
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    by_id = {r.record_id: r for r in records}
    must_label, must_resolve, rescuable = _ft_requirements(decisions, autonomy)
    rows = []
    for d in decisions:
        vote = d.votes[0] if d.votes else None
        outcome = retrieval.get(d.record_id)
        fields = _record_fields(by_id.get(d.record_id), d.record_id)
        rows.append(
            {
                "record_id": d.record_id,
                "title": fields["title"],
                "year": fields["year"],
                "doi": fields["doi"],
                "fulltext": d.fulltext_status,
                "fulltext_reason": outcome.reason if outcome else None,
                "fulltext_source_url": outcome.source_url if outcome else None,
                "proposal": d.ensemble_label,
                "confidence": vote.confidence if vote else None,
                "rationale": vote.rationale if vote else None,
                "criteria_violated": list(vote.criteria_violated) if vote else [],
            }
        )
    return {
        "mode": _mode(autonomy),
        "n_sought": len(decisions),
        "n_retrieved": sum(1 for d in decisions if d.fulltext_status == "retrieved"),
        "n_not_retrieved": len(rescuable),
        "records": rows,
        "must_label": must_label,
        "must_resolve": must_resolve,
        "rescuable": rescuable,
    }


def _not_retrieved_note(outcome: RetrievalOutcome) -> str:
    """Nota de un informe no recuperado: su motivo y, si es transitorio, qué pasará.

    Un fallo transitorio (``TRANSIENT_FULLTEXT_REASONS``) no se congela en el diario: se
    reintenta al reanudar. El humano puede rescatarlo igualmente (quizá tiene el PDF), pero
    si en la reanudación el texto llega, el informe pasa a recuperado y con propuesta IA, la
    solicitud cambia y su rescate, atado a la solicitud anterior, no se aplica: tendrá que
    decidir de nuevo. El aviso va delante del detalle (que puede ser largo) porque la
    plantilla corta la nota entera.
    """
    detail = outcome.detail or "sin detalle"
    if outcome.reason in TRANSIENT_FULLTEXT_REASONS:
        return (
            f"no recuperado: {outcome.reason} · transitorio: se reintenta al reanudar y, si el "
            f"texto llega, esta solicitud cambia y habrá que decidir de nuevo · {detail}"
        )
    return f"no recuperado: {outcome.reason} ({detail})"


def ft_policy(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    retrieval: Mapping[str, RetrievalOutcome],
    autonomy: str,
) -> RecordPolicy:
    """Qué puede y debe etiquetar el humano en FT (D1, D2, D9).

    Excluir exige razón (va a la lista 16b) y etiquetar un no recuperado es un
    rescate, también con razón. Un no recuperado transitorio también es rescatable,
    pero su nota avisa de que se reintentará al reanudar (``_not_retrieved_note``).
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    titles = {r.record_id: r.title for r in records}
    must_label, must_resolve, rescuable = _ft_requirements(decisions, autonomy)
    hints = []
    for d in decisions:
        note = _note(d)
        outcome = retrieval.get(d.record_id)
        if d.fulltext_status == "not_retrieved" and outcome is not None:
            note = _not_retrieved_note(outcome)
        hints.append(
            RecordHint(d.record_id, titles.get(d.record_id, d.record_id), d.ensemble_label, note)
        )
    return RecordPolicy(
        hints=tuple(hints),
        must_label=frozenset(must_label),
        must_resolve=frozenset(must_resolve),
        rescue_ids=frozenset(rescuable),
        reason_on_exclude=True,
    )


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
