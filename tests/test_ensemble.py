"""Tests del voto del ensemble (sesgado a recall)."""

from __future__ import annotations

from prisma_loop.llm.ensemble import recall_biased_label


def test_incluye_si_cualquiera_incluye() -> None:
    assert recall_biased_label(["exclude", "include", "exclude"]) == "include"


def test_unclear_si_no_hay_include() -> None:
    assert recall_biased_label(["exclude", "unclear"]) == "unclear"


def test_excluye_solo_si_todos_excluyen() -> None:
    assert recall_biased_label(["exclude", "exclude"]) == "exclude"


def test_sin_votos_es_unclear() -> None:
    assert recall_biased_label([]) == "unclear"
