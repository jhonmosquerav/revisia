"""Las corridas reales de ``tests/conftest.py`` tienen lo que los tests del auditor necesitan."""

from __future__ import annotations

import json

import yaml

from revisia.schemas.artifacts import RunInfo


def _ledger(run) -> list[dict]:
    lines = (run / "decisions_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def test_corrida_real_tiene_exclusiones_ia_y_gold_de_dos_clases(corrida) -> None:
    manifest = yaml.safe_load((corrida / "manifest.yml").read_text(encoding="utf-8"))
    counts = manifest["counts"]
    assert (counts["identified"], counts["duplicates_removed"], counts["screened"]) == (7, 1, 6)
    assert (counts["excluded_ta"], counts["excluded_ft"], counts["included"]) == (2, 1, 3)
    assert (counts["fulltext_sought"], counts["fulltext_not_retrieved"]) == (4, 0)
    assert (counts["excluded_ft_human"], counts["excluded_ft_ai"]) == (1, 0)
    assert counts["identified_by_source"] == {"OpenAlex": 4, "Crossref": 3}
    # 6 registros × 2 miembros T/A + 4 FT + 3 extracciones + 1 doble + 3 RoB + 1 síntesis.
    llamadas = (corrida / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(manifest["llm_calls"]) == len(llamadas) == 24
    assert {c["provider"] for c in manifest["llm_calls"]} == {"fake"}
    metrics = json.loads((corrida / "03_screening" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["tp"] > 0 and metrics["tn"] > 0  # gold de dos clases
    ledger = _ledger(corrida)
    assert {e["actor"] for e in ledger} == {"human:revisora"}
    assert [e["stage"] for e in ledger if e["action"] == "approve"] == [
        "screening_ta",
        "screening_ft",
        "extraccion",
        "rob",
        "reporte",
    ]
    # FT en A0: una etiqueta humana por registro recuperado (D1).
    labels = {e["target"]: e["detail"]["to"] for e in ledger if e["action"] == "label"}
    assert labels == {
        "10.1000/llm-1": "include",
        "10.1000/asreview": "include",
        "10.1000/ensemble": "include",
        "10.1000/secundario": "exclude",
    }
    info = RunInfo.model_validate_json((corrida / "run.json").read_text(encoding="utf-8"))
    assert info.status == "completed"
    assert (corrida / "00_protocol" / "gold.yml").exists()


def test_corrida_en_pausa_ft_se_detuvo_en_el_gate_de_texto_completo(corrida_en_pausa_ft) -> None:
    info = RunInfo.model_validate_json(
        (corrida_en_pausa_ft / "run.json").read_text(encoding="utf-8")
    )
    assert (info.status, info.stage) == ("paused", "screening_ft")
    assert (corrida_en_pausa_ft / "screening_ft" / "review_request.yml").exists()
    assert not (corrida_en_pausa_ft / "screening_ft" / "decision.yml").exists()
    assert not (corrida_en_pausa_ft / "manifest.yml").exists()
    assert [e["stage"] for e in _ledger(corrida_en_pausa_ft)] == ["screening_ta"]
