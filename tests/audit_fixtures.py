"""Ayudas de los tests del auditor (spec 2026-10-04 §9.4).

Contiene solo lo que el pipeline no puede producir: helpers de edición de una
corrida (para romper una relación cada vez) y ``auditar``, que comprueba en
cada llamada el invariante del auditor (**si hay algún N/A, hay al menos un
FAIL**: un N/A nunca puede ocultar nada en una corrida publicable, §9.2) y que
hay una sola fila por check.

Los helpers de edición sirven tanto para las corridas de la fase 1 de PR-E
(solo manifiesto) como para las de la Ola 1 (``llm_calls.jsonl``, diarios y
``00_protocol/``): editan todas las copias de un dato a la vez, para romper
solo la relación que el test quiere romper.

Uso (``tests/`` está en ``sys.path`` porque no es un paquete)::

    from audit_fixtures import auditar, edit_json, fila
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from revisia.audit import AuditCheck, AuditReport, run_audit
from revisia.config import ReviewProtocol
from revisia.exclusions import compute_exclusion_breakdown
from revisia.exports import PrismaCounts, render_prisma2020_flow_csv
from revisia.metrics import ScreeningMetrics, kappa_from_matrix, mcc, wmcc
from revisia.provenance.ledger import DecisionEntry
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.artifacts import JOURNAL_PATHS
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision, ScreeningVote
from revisia.schemas.verification import CitationCheck, VerificationReport

_REPO = Path(__file__).resolve().parent.parent


def auditar(run_dir: Path) -> AuditReport:
    """``run_audit`` + el invariante ``N/A ⇒ FAIL`` y una fila por check."""
    report = run_audit(run_dir)
    ids = [c.check_id for c in report.checks]
    assert len(ids) == len(set(ids)), f"filas repetidas: {ids}"
    if any(c.status == "N/A" for c in report.checks):
        assert report.n_fail > 0, "N/A sin ningún FAIL: el N/A estaría ocultando algo"
    return report


def fila(report: AuditReport, check_id: str) -> AuditCheck:
    """La fila ``check_id`` del informe (falla si no está)."""
    matches = [c for c in report.checks if c.check_id == check_id]
    assert matches, f"sin fila {check_id!r}: {[c.check_id for c in report.checks]}"
    return matches[0]


def _apply(data: Any, fn: Callable[[Any], Any]) -> Any:
    """Aplica ``fn``: muta ``data`` en sitio o devuelve un mapa/lista que lo sustituye.

    Cualquier otro valor devuelto se ignora, para que ``lambda d: d.pop("k")``
    funcione como edición en sitio cuando el valor extraído es un escalar. Para
    borrar un mapa o una lista anidados usa ``del`` en una función: devolverlos
    sustituiría el documento entero.
    """
    result = fn(data)
    return result if isinstance(result, dict | list) else data


def edit_json(path: Path, fn: Callable[[Any], Any]) -> None:
    """Carga ``path``, aplica ``fn`` (ver :func:`_apply`) y lo reescribe."""
    data = _apply(json.loads(path.read_text(encoding="utf-8")), fn)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def edit_yaml(path: Path, fn: Callable[[Any], Any]) -> None:
    """Como :func:`edit_json`, para YAML (conserva el orden de claves)."""
    data = _apply(yaml.safe_load(path.read_text(encoding="utf-8")), fn)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, items: list[dict]) -> None:
    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    path.write_text(text, encoding="utf-8")


def edit_ledger(run_dir: Path, fn: Callable[[list[dict]], Any]) -> None:
    """Edita ``decisions_ledger.jsonl`` como lista de dicts (una línea por entrada)."""
    path = run_dir / "decisions_ledger.jsonl"
    _write_jsonl(path, _apply(_read_jsonl(path), fn))


def editar_protocolo(run_dir: Path, fn: Callable[[dict], Any]) -> None:
    """Edita el protocolo registrado: ``manifest.protocol`` y, si existe, la
    instantánea ``00_protocol/protocol.yml`` (Ola 1), para que el test no
    dependa de qué fuente lea el auditor.

    Convención: ``fn`` **muta el protocolo en sitio** y su valor devuelto se
    ignora (revisión de C3). A diferencia de :func:`edit_yaml`, aquí un mapa
    devuelto nunca sustituye nada: ``lambda p: p.pop("registration")`` o
    ``p.setdefault(...)`` devuelven el mapa *extraído*, no un protocolo nuevo, y
    tomarlo como documento de reemplazo pisaba ``manifest.yml`` entero (o dejaba
    el protocolo reducido a ese mapa). Para sustituir el protocolo completo:
    ``p.clear(); p.update(nuevo)``.
    """

    def _en_sitio(protocolo: dict) -> None:
        fn(protocolo)

    manifest = run_dir / "manifest.yml"
    if manifest.exists():
        edit_yaml(manifest, lambda m: _en_sitio(m["protocol"]))
    snapshot = run_dir / "00_protocol" / "protocol.yml"
    if snapshot.exists():
        edit_yaml(snapshot, _en_sitio)


def _llamadas(run_dir: Path) -> list[dict]:
    jsonl = run_dir / "llm_calls.jsonl"
    if jsonl.exists():
        return _read_jsonl(jsonl)
    manifest = yaml.safe_load((run_dir / "manifest.yml").read_text(encoding="utf-8"))
    return list(manifest["llm_calls"])


def editar_llamadas(run_dir: Path, fn: Callable[[list[dict]], Any]) -> None:
    """Edita las llamadas IA en todas sus copias a la vez.

    ``fn`` recibe la lista de llamadas (las de ``llm_calls.jsonl`` si existe; si
    no, las del manifiesto) y la muta o devuelve otra. Se reescriben
    ``llm_calls.jsonl``, las ``metas`` de los diarios que citaban cada llamada
    (relación 12 de §4.4) y el manifiesto, con ``models_used`` y
    ``deterministic_token_level`` recalculados.
    """
    old = _llamadas(run_dir)
    new = _apply(copy.deepcopy(old), fn)
    jsonl = run_dir / "llm_calls.jsonl"
    if jsonl.exists():
        _write_jsonl(jsonl, new)
        replacement = {json.dumps(o, sort_keys=True): n for o, n in zip(old, new, strict=False)}
        for rel in JOURNAL_PATHS.values():
            path = run_dir / rel
            if path.exists():
                entries = _read_jsonl(path)
                for entry in entries:
                    entry["metas"] = [
                        replacement.get(json.dumps(m, sort_keys=True), m) for m in entry["metas"]
                    ]
                _write_jsonl(path, entries)
    manifest_path = run_dir / "manifest.yml"
    if manifest_path.exists():

        def _manifest(manifest: dict) -> None:
            manifest["llm_calls"] = new
            manifest["models_used"] = sorted({f"{c['provider']}:{c['model']}" for c in new})
            manifest["deterministic_token_level"] = all(c["deterministic"] for c in new)

        edit_yaml(manifest_path, _manifest)


def reetiquetar_llamadas(
    run_dir: Path,
    *,
    provider: str = "agent",
    deterministic: bool = False,
    inicio: datetime | None = None,
    paso: timedelta | None = None,
) -> None:
    """Reescribe las llamadas como si vinieran de otro proveedor (coherente).

    Con ``inicio`` y ``paso``, la llamada ``i`` pasa a ``inicio + i·paso`` (para
    simular ráfagas o pausas).
    """

    def _editar(calls: list[dict]) -> None:
        for i, call in enumerate(calls):
            call.update(provider=provider, deterministic=deterministic)
            if inicio is not None and paso is not None:
                call["timestamp_utc"] = (inicio + i * paso).isoformat()

    editar_llamadas(run_dir, _editar)


def primera_llamada(run_dir: Path) -> datetime:
    """Marca de tiempo de la primera llamada IA de la corrida."""
    return datetime.fromisoformat(_llamadas(run_dir)[0]["timestamp_utc"])


def comprimir_llamadas(run_dir: Path, *, ventana: timedelta = timedelta(microseconds=1300)) -> None:
    """Síntoma C3: todas las llamadas (no fake) dentro de ``ventana`` (1,3 ms)."""
    n = len(_llamadas(run_dir))
    reetiquetar_llamadas(run_dir, inicio=primera_llamada(run_dir), paso=ventana / max(n - 1, 1))


def metricas_validas(tp: int, fp: int, fn: int, tn: int, *, fn_weight: float = 10.0) -> dict:
    """Un ``ScreeningMetrics`` válido y coherente con su matriz (como ``model_dump``)."""

    def _ratio(num: int, den: int) -> float | None:
        return num / den if den else None

    return ScreeningMetrics(
        n=tp + fp + fn + tn,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        recall=_ratio(tp, tp + fn),
        lost_evidence=_ratio(fn, tp + fn),
        precision=_ratio(tp, tp + fp),
        mcc=mcc(tp, fp, fn, tn),
        wmcc=wmcc(tp, fp, fn, tn, fn_weight=fn_weight),
        wmcc_fn_weight=fn_weight,
        cohen_kappa=kappa_from_matrix(tp, fp, fn, tn),
    ).model_dump()


def escribir_metricas(run_dir: Path, metrics: dict) -> None:
    """Sustituye ``03_screening/metrics.json``."""
    path = run_dir / "03_screening" / "metrics.json"
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def pausar_en_screening_ft(run_dir: Path) -> None:
    """Deja la corrida como si se hubiera detenido en el gate FT (fase 1 de PR-E).

    Lo que el pipeline aún no habría escrito desaparece: la decisión FT, los
    gates posteriores, las etapas posteriores, el manifiesto y el desglose de
    exclusiones (se escribe tras aprobar el gate FT).
    """
    edit_ledger(run_dir, lambda entries: [e for e in entries if e["stage"] == "screening_ta"])
    (run_dir / "screening_ft" / "decision.yml").unlink()
    for gate in ("extraccion", "rob", "reporte"):
        shutil.rmtree(run_dir / gate)
    for rel in ("05_extraction", "06_synthesis", "07_rob", "08_meta", "deliverable"):
        shutil.rmtree(run_dir / rel)
    (run_dir / "manifest.yml").unlink()
    (run_dir / "03_screening" / "exclusions.json").unlink()


# ── Corrida v0.7 (anterior a la Ola 1) ──────────────────────────────────

_V07_INICIO = datetime(2026, 9, 20, 10, 0, 0, tzinfo=UTC)
_V07_MODELO = "gemini:gemini-2.5-flash"
# record_id → (título, etiqueta T/A, etiqueta FT o None si no pasó T/A).
_V07_REGISTROS = {
    "10.2000/a": ("Cribado con LLM en revisiones de salud", "include", "include"),
    "10.2000/b": ("Estudio ajeno al cribado", "exclude", None),
    "10.2000/c": ("Cribado sin métricas de desempeño", "include", "exclude"),
    "10.2000/d": ("Ensemble de modelos para cribar títulos", "include", "include"),
}


def _v07_marca(segundos: float) -> str:
    return (_V07_INICIO + timedelta(seconds=segundos, microseconds=250_000)).isoformat()


def _v07_decision(record_id: str, label: str, phase: str) -> dict:
    vote = ScreeningVote(
        model=_V07_MODELO,
        label=label,
        confidence=0.8,
        rationale=f"v0.7: {label}",
        criteria_violated=["sin métricas"] if label == "exclude" else [],
    )
    decision = ScreeningDecision(
        record_id=record_id,
        phase=phase,
        votes=[vote],
        ensemble_label=label,
        final_label=label,
        citations_checked=[record_id],
    )
    # v0.7 no tenía los campos que añade la Ola 1.
    return decision.model_dump(exclude={"fulltext_status", "human_reason", "human_actor"})


def write_legacy_v07(tmp_path: Path) -> Path:
    """Escribe una corrida coherente del motor v0.7 (sin ``run.json``).

    Es lo que dejaba el pipeline antes de la Ola 1: 5 identificados (1
    duplicado), un solo screener, 1 exclusión IA en T/A y 1 a texto completo,
    2 incluidos, 12 llamadas de un proveedor real y los 5 gates aprobados por
    un humano. El auditor la evalúa con las relaciones v0.7 (D13).
    """
    run = tmp_path / "runs" / "legado-v07-20260920-100000"
    for sub in ("03_screening", "04_fulltext", "05_extraction", "06_synthesis", "07_rob"):
        (run / sub).mkdir(parents=True)
    (run / "deliverable" / "interop").mkdir(parents=True)

    ta = [
        _v07_decision(rid, label, "title_abstract") for rid, (_, label, _) in _V07_REGISTROS.items()
    ]
    ft = [
        _v07_decision(rid, label, "fulltext")
        for rid, (_, _, label) in _V07_REGISTROS.items()
        if label is not None
    ]
    included = [d["record_id"] for d in ft if d["final_label"] == "include"]
    extractions = {rid: ExtractionRecord(study_id=rid).model_dump() for rid in included}
    assessments = {
        rid: RoBAssessment(study_id=rid, tool="RoB2", overall="low").model_dump()
        for rid in included
    }
    verification = VerificationReport(
        stage="reporte",
        checks=[
            CitationCheck(
                claim="El cribado con LLM alcanza recall alto [10.2000/a].",
                cited_id="10.2000/a",
                exists_in_corpus=True,
                grounded=True,
            )
        ],
    ).model_dump()
    decisions = [ScreeningDecision.model_validate(d) for d in [*ta, *ft]]
    exclusions = compute_exclusion_breakdown(decisions).model_dump()
    counts = {
        "identified": 5,
        "identified_by_source": {"OpenAlex": 3, "Crossref": 2},
        "duplicates_removed": 1,
        "removed_automation": 0,
        "removed_other": 0,
        "screened": 4,
        "excluded_ta": 1,
        "excluded_ta_human": 0,
        "excluded_ta_ai": 1,
        "fulltext_assessed": 3,
        "fulltext_abstract_only": 0,
        "excluded_ft": 1,
        "ft_exclusion_reasons": {"sin métricas": 1},
        "included": 2,
    }
    # 4 T/A + 3 FT + 2 extracciones + 2 RoB + 1 síntesis, una cada 1,2 s.
    calls = [
        RunMeta(
            provider="gemini",
            model="gemini-2.5-flash",
            seed=7,
            temperature=0.0,
            prompt_sha256=sha256_text(f"prompt {i}"),
            response_sha256=sha256_text(f"respuesta {i}"),
            timestamp_utc=_v07_marca(1 + 1.2 * i),
            deterministic=False,
        ).model_dump()
        for i in range(12)
    ]
    protocol = ReviewProtocol(
        slug="legado-v07",
        title="Corrida v0.7 de referencia",
        question={"text": "¿Sirven los LLM para cribar?", "framework": "PICO"},
        databases=["OpenAlex", "Crossref"],
        registration={"osf": "OSF-LEGADO"},
        search_window={"from": "2015-01-01", "to": "2026-09-01", "executed": "2026-09-20"},
        llm={"default": {"provider": "gemini", "model": "gemini-2.5-flash", "seed": 7}},
    ).model_dump(mode="json")
    manifest = {
        "slug": "legado-v07",
        "created_utc": _v07_marca(60),
        "timestamp": "20260920-100000",
        "provenance": "pipeline",
        "protocol": protocol,
        "counts": counts,
        "llm_calls": calls,
        "models_used": [_V07_MODELO],
        "deterministic_token_level": False,
        "verification": verification,
        "risk_of_bias": assessments,
        "exclusions": exclusions,
    }

    def _json(rel: str, data: object) -> None:
        (run / rel).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    _json("03_screening/decisions.json", ta)
    _json("03_screening/exclusions.json", exclusions)
    _json("04_fulltext/decisions.json", ft)
    _json("05_extraction/extractions.json", extractions)
    _json("06_synthesis/verification.json", verification)
    _json("07_rob/assessments.json", assessments)
    (run / "manifest.yml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    gates = (
        ("screening_ta", "A1"),
        ("screening_ft", "A0"),
        ("extraccion", "A0"),
        ("rob", "A0"),
        ("reporte", "A1"),
    )
    ledger = []
    for i, (gate, autonomy) in enumerate(gates):
        (run / gate).mkdir()
        (run / gate / "review_request.yml").write_text(f"stage: {gate}\n", encoding="utf-8")
        (run / gate / "decision.yml").write_text(
            "approved: true\nactor: human:revisora\n", encoding="utf-8"
        )
        entry = DecisionEntry(
            stage=gate,
            actor="human:revisora",
            autonomy=autonomy,
            action="approve",
            timestamp_utc=_v07_marca(6 + 10 * i),
        )
        ledger.append(entry.model_dump_json() + "\n")
    (run / "decisions_ledger.jsonl").write_text("".join(ledger), encoding="utf-8")

    deliverable = run / "deliverable"
    for name in (
        "prisma_flow.md",
        "metodologia.md",
        "tabla_extraccion.md",
        "risk_of_bias.md",
        "referencias.bib",
        "checklist_2020.md",
        "checklist_traice.md",
        "checklist_s.md",
        "checklist_abstracts.md",
    ):
        (deliverable / name).write_text(f"# {name} (v0.7)\n", encoding="utf-8")
    (deliverable / "documento.md").write_text(
        "# Corrida v0.7\n\nEl cribado con LLM alcanza recall alto [10.2000/a].\n",
        encoding="utf-8",
    )
    (deliverable / "interop" / "prisma2020_flow.csv").write_text(
        render_prisma2020_flow_csv(PrismaCounts.model_validate(counts)), encoding="utf-8"
    )
    return run


_SCRIPT_AUDITAR = (
    "import json, sys\n"
    "from revisia.audit import run_audit\n"
    "informe = run_audit(sys.argv[1])\n"
    "print(json.dumps([[c.check_id, c.status, c.detail] for c in informe.checks]))\n"
)


def auditar_en_subproceso(corrida: Path, *, timeout: int) -> dict[str, tuple[str, str]]:
    """``run_audit`` en un proceso aparte: ``{check_id: (estado, detalle)}``.

    Un crash nativo o un cuelgue del auditor no puede tirar la sesión de pytest: se ve como
    un código de salida distinto de 0 o como ``TimeoutExpired``.
    """
    proceso = subprocess.run(
        [sys.executable, "-c", _SCRIPT_AUDITAR, str(corrida)],
        cwd=_REPO,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    mensaje = f"el auditor murió (código {proceso.returncode}): {proceso.stderr[-500:]}"
    assert proceso.returncode == 0, mensaje
    return {i: (status, detalle) for i, status, detalle in json.loads(proceso.stdout)}


# Una bomba de alias (`*a` nueve veces por nivel, diez niveles) carga en milisegundos porque
# PyYAML comparte los nodos; lo que cuelga es recorrerla (`repr`, `str`, validar): 9**10
# hojas. El auditor no puede imprimir el valor hostil del manifiesto (segunda revisión de
# la Tarea 4).
def bomba_de_alias(niveles: int = 10) -> str:
    """Cabecera YAML con las anclas ``a0``…``a9``: ``*a9`` es la bomba."""
    base = "a0: &a0 [x, x, x, x, x, x, x, x, x]\n"
    return base + "".join(
        f"a{i}: &a{i} [{', '.join([f'*a{i - 1}'] * 9)}]\n" for i in range(1, niveles)
    )
