"""Tests del despacho multi-base y la importación manual RIS/BibTeX."""

from __future__ import annotations

import pytest

from revisia.agents import search_backends
from revisia.agents.search_backends import available_backends, search_database
from revisia.ingest import import_directory, parse_bibtex, parse_ris


def test_backends_registrados() -> None:
    backends = available_backends()
    assert "openalex" in backends
    assert "crossref" in backends
    assert "semanticscholar" in backends
    assert "europepmc" in backends
    # 'pubmed' → NCBI E-utilities (reasignado); Europe PMC vive en 'europepmc'.
    assert "pubmed" in backends


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # noqa: D401
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Sustituto de httpx.Client (context manager) que sirve un payload fijo."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.last_params: dict | None = None

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get(self, url: str, params: dict | None = None) -> _FakeResp:
        self.last_params = params
        return _FakeResp(self._payload)


def test_europepmc_parse_mockeado(monkeypatch) -> None:
    payload = {
        "resultList": {
            "result": [
                {
                    "id": "40000001",
                    "source": "MED",
                    "doi": "10.1/ABC",
                    "title": "LLM screening en RS",
                    "abstractText": "<p>Resumen con <b>HTML</b>.</p>",
                    "authorString": "Doe J, Roe A",
                    "pubYear": "2026",
                },
                {  # sin DOI → record_id derivado del id Europe PMC
                    "id": "PPR123",
                    "source": "PPR",
                    "title": "Preprint sin doi",
                    "abstractText": "Otro resumen.",
                    "authorString": "",
                    "pubYear": "bad-year",
                },
            ]
        }
    }
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: _FakeClient(payload))

    records = search_database("europepmc", "llm systematic review", 10, mailto="x@y.z")
    assert len(records) == 2
    r0 = records[0]
    assert r0.doi == "10.1/abc"
    assert r0.record_id == "10.1/abc"
    assert r0.title == "LLM screening en RS"
    assert "HTML" in (r0.abstract or "") and "<b>" not in (r0.abstract or "")  # HTML limpiado
    assert r0.authors == ["Doe J", "Roe A"]
    assert r0.year == 2026
    assert r0.source_db == "EuropePMC"
    # 2.º registro: sin DOI y año inválido → tolerante
    assert records[1].record_id.startswith("europepmc:")
    assert records[1].year is None


def test_base_desconocida_falla() -> None:
    with pytest.raises(ValueError, match="sin backend"):
        search_database("inventada", "q", 5)


def test_base_de_pago_sugiere_importacion_manual() -> None:
    with pytest.raises(ValueError, match="importación manual"):
        search_database("Scopus", "q", 5)


def test_db_key_normaliza_espacios_y_mayusculas() -> None:
    from revisia.agents.search_backends import db_key

    assert db_key("Europe PMC") == "europepmc"
    assert db_key("Semantic Scholar") == "semanticscholar"
    assert db_key("OpenAlex") == "openalex"


def test_multi_database_usa_cadena_de_base_con_espacios(tmp_path, monkeypatch) -> None:
    # Una base multi-palabra ("Europe PMC") debe encontrar su search_strings/europepmc.txt
    # con el MISMO criterio que el dispatch (db_key), no con f"{db.lower()}.txt".
    from types import SimpleNamespace

    from revisia.orchestration.pipeline import _multi_database_search

    ss = tmp_path / "search_strings"
    ss.mkdir()
    (ss / "europepmc.txt").write_text("cadena curada europe pmc", encoding="utf-8")

    capturado: dict[str, str] = {}

    def fake_search_database(db, query, max_results, *, mailto=None):
        capturado[db] = query
        return []

    monkeypatch.setattr(search_backends, "search_database", fake_search_database)

    protocol = SimpleNamespace(databases=["Europe PMC"])
    _multi_database_search(protocol, tmp_path, "pregunta cruda", 10, None)
    assert capturado["Europe PMC"] == "cadena curada europe pmc"  # usó el .txt, no la pregunta


def test_backends_nuevos_registrados() -> None:
    backends = available_backends()
    for alias in (
        "eric",
        "doaj",
        "unesdoc",
        "bvs",
        "lilacs",
        "gim",
        "agrosavia",
        "clacso",
        "worldbank",
        "okr",
        "doab",
    ):
        assert alias in backends, alias


def test_lilacs_despacha_a_bvs_portal(monkeypatch) -> None:
    from revisia.agents import open_backends

    class _Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def __enter__(self):
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def get(self, url: str, params: dict | None = None) -> _FakeResp:
            self.calls.append((url, params or {}))
            return _FakeResp({"diaServerResponse": [{"response": {"numFound": 0, "docs": []}}]})

    client = _Client()
    monkeypatch.setattr(open_backends, "_client", lambda timeout=60.0, mailto=None: client)
    assert search_database("LILACS", "diabetes", 5) == []
    assert client.calls[0][0] == "https://search.bvsalud.org/portal/"
    assert client.calls[0][1]["q"] == "diabetes"


def test_bases_sin_busqueda_sugieren_importacion_manual() -> None:
    for db in ("Redalyc", "Dialnet", "SciELO", "Google Scholar", "Mendeley"):
        with pytest.raises(ValueError, match="importación manual"):
            search_database(db, "q", 5)


def test_multi_database_degrada_si_una_base_falla(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from revisia.orchestration.pipeline import _multi_database_search
    from revisia.schemas.records import SearchRecord

    def fake_search_database(db, query, max_results, *, mailto=None):
        if db == "BVS":
            raise RuntimeError("503 Service Unavailable")
        return [SearchRecord(record_id=f"{db}:1", title="ok", source_db=db)]

    monkeypatch.setattr(search_backends, "search_database", fake_search_database)
    protocol = SimpleNamespace(databases=["OpenAlex", "BVS", "ERIC"])
    records, failures = _multi_database_search(protocol, tmp_path, "q", 5, None)
    assert [r.source_db for r in records] == ["OpenAlex", "ERIC"]
    assert failures == [{"db": "BVS", "error": "RuntimeError: 503 Service Unavailable"}]


def test_multi_database_redacta_api_key_y_registra_validation_error(tmp_path, monkeypatch) -> None:
    """Un ValueError/ValidationError DENTRO de un backend registrado no se traga (antes
    se confundía con "base sin backend"); y el mensaje no filtra api_key/email."""
    from types import SimpleNamespace

    from revisia.orchestration.pipeline import _multi_database_search

    def fake_search_database(db, query, max_results, *, mailto=None):
        if db == "OpenAlex":
            raise RuntimeError(
                "Client error '429' for url "
                "'https://api.openalex.org/works?search=x&mailto=me%40x.org&api_key=SECRETO123'"
            )
        if db == "ERIC":
            raise ValueError("1 validation error for SearchRecord: year no es entero")
        return []

    monkeypatch.setattr(search_backends, "search_database", fake_search_database)
    protocol = SimpleNamespace(databases=["OpenAlex", "ERIC", "Scopus"])
    _, failures = _multi_database_search(protocol, tmp_path, "q", 5, None)
    dbs = [f["db"] for f in failures]
    assert dbs == ["OpenAlex", "ERIC"]  # Scopus (sin backend) no es un fallo: va por imported/
    assert "SECRETO123" not in failures[0]["error"]
    assert "me%40x.org" not in failures[0]["error"]
    assert "api_key=<redacted>" in failures[0]["error"]
    assert failures[1]["error"].startswith("ValueError:")


def test_parse_ris() -> None:
    ris = """TY  - JOUR
TI  - Un estudio de prueba
AU  - Doe, Jane
AU  - Roe, Ada
PY  - 2021
DO  - 10.1/ABC
AB  - Resumen del estudio.
UR  - https://example.org/x
ER  -
"""
    records = parse_ris(ris)
    assert len(records) == 1
    r = records[0]
    assert r.title == "Un estudio de prueba"
    assert r.authors == ["Doe, Jane", "Roe, Ada"]
    assert r.year == 2021
    assert r.doi == "10.1/abc"
    assert r.source_db == "imported-RIS"


def test_parse_bibtex() -> None:
    bib = """@article{key2021,
  title = {Otro estudio},
  author = {Doe, Jane and Roe, Ada},
  year = {2020},
  doi = {10.2/XYZ},
  abstract = {Un resumen.}
}
"""
    records = parse_bibtex(bib)
    assert len(records) == 1
    r = records[0]
    assert r.title == "Otro estudio"
    assert r.authors == ["Doe, Jane", "Roe, Ada"]
    assert r.year == 2020
    assert r.doi == "10.2/xyz"


def test_record_id_sin_doi_es_hash_determinista() -> None:
    bib = "@misc{k, title = {Sin DOI}}\n"
    r1 = parse_bibtex(bib)[0]
    r2 = parse_bibtex(bib)[0]
    assert r1.record_id.startswith("hash:")
    assert r1.record_id == r2.record_id  # determinista


def test_import_directory_inexistente_vacio(tmp_path) -> None:
    assert import_directory(tmp_path / "no-existe") == []


def test_import_directory_mezcla_ris_y_bib(tmp_path) -> None:
    (tmp_path / "a.ris").write_text("TY  - JOUR\nTI  - A\nER  -\n", encoding="utf-8")
    (tmp_path / "b.bib").write_text("@article{k, title = {B}}\n", encoding="utf-8")
    records = import_directory(tmp_path)
    titles = sorted(r.title for r in records)
    assert titles == ["A", "B"]
