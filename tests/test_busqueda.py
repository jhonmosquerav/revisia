"""Tests del agente de búsqueda (offline · sin red)."""

from __future__ import annotations

from prisma_loop.agents.busqueda import reconstruct_abstract, work_to_record


def test_reconstruct_abstract_ordena_por_posicion() -> None:
    inverted = {"Hello": [0, 2], "world": [1]}
    assert reconstruct_abstract(inverted) == "Hello world Hello"


def test_reconstruct_abstract_vacio() -> None:
    assert reconstruct_abstract(None) is None
    assert reconstruct_abstract({}) is None


def test_work_to_record_prioriza_doi() -> None:
    work = {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1/AbC",
        "display_name": "Un estudio",
        "publication_year": 2024,
        "authorships": [{"author": {"display_name": "Doe"}}],
        "abstract_inverted_index": {"resultado": [0]},
    }
    rec = work_to_record(work)
    assert rec.record_id == "10.1/abc"
    assert rec.doi == "10.1/abc"
    assert rec.year == 2024
    assert rec.authors == ["Doe"]
    assert rec.abstract == "resultado"
    assert rec.source_db == "OpenAlex"


def test_work_to_record_cae_a_openalex_id() -> None:
    rec = work_to_record({"id": "https://openalex.org/W999", "display_name": "Otro"})
    assert rec.record_id == "W999"
    assert rec.doi is None
    assert rec.abstract is None
