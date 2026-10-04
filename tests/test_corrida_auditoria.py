"""La corrida real de ``tests/conftest.py`` tiene lo que los tests del auditor necesitan."""

from __future__ import annotations

import json

import yaml


def test_corrida_real_tiene_exclusiones_ia_y_gold_de_dos_clases(corrida) -> None:
    manifest = yaml.safe_load((corrida / "manifest.yml").read_text(encoding="utf-8"))
    counts = manifest["counts"]
    assert (counts["identified"], counts["duplicates_removed"], counts["screened"]) == (7, 1, 6)
    assert (counts["excluded_ta"], counts["excluded_ft"], counts["included"]) == (2, 1, 3)
    assert counts["identified_by_source"] == {"OpenAlex": 4, "Crossref": 3}
    # 6 registros × 2 miembros T/A + 4 FT + 3 extracciones + 1 doble + 3 RoB + 1 síntesis.
    assert len(manifest["llm_calls"]) == 24
    assert {c["provider"] for c in manifest["llm_calls"]} == {"fake"}
    metrics = json.loads((corrida / "03_screening" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["tp"] > 0 and metrics["tn"] > 0  # gold de dos clases
    ledger = (corrida / "decisions_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    actores = {json.loads(line)["actor"] for line in ledger}
    assert actores == {"human:revisora"}
    assert len(ledger) == 5
