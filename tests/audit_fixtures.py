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
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from revisia.audit import AuditCheck, AuditReport, run_audit
from revisia.metrics import ScreeningMetrics, kappa_from_matrix, mcc, wmcc
from revisia.schemas.artifacts import JOURNAL_PATHS


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
    dependa de qué fuente lea el auditor."""
    manifest = run_dir / "manifest.yml"
    if manifest.exists():
        edit_yaml(manifest, lambda m: fn(m["protocol"]))
    snapshot = run_dir / "00_protocol" / "protocol.yml"
    if snapshot.exists():
        edit_yaml(snapshot, fn)


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
