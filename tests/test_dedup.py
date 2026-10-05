"""Tests del agente de deduplicación."""

from __future__ import annotations

import json
from pathlib import Path

from revisia.agents.dedup import deduplicate, deduplicate_with_report
from revisia.config import load_protocol
from revisia.ingest import parse_ris
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.schemas.artifacts import DedupReport
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def test_dedup_por_doi_normalizado() -> None:
    recs = [
        SearchRecord(record_id="a", title="A", doi="10.1/x"),
        SearchRecord(record_id="b", title="B distinto", doi="10.1/X"),
    ]
    unique, discarded = deduplicate(recs)
    assert len(unique) == 1
    assert discarded == 1


def test_dedup_por_titulo_normalizado() -> None:
    recs = [
        SearchRecord(record_id="a", title="Hello, World!"),
        SearchRecord(record_id="b", title="hello   world"),
    ]
    unique, discarded = deduplicate(recs)
    assert len(unique) == 1
    assert discarded == 1


def test_dedup_conserva_distintos_y_orden() -> None:
    recs = [
        SearchRecord(record_id="a", title="Primero"),
        SearchRecord(record_id="b", title="Segundo"),
    ]
    unique, discarded = deduplicate(recs)
    assert [r.record_id for r in unique] == ["a", "b"]
    assert discarded == 0


def test_dedup_fusiona_extra_faltante_del_duplicado() -> None:
    # Conserva el primero (OpenAlex, sin pmcid) pero hereda el pmcid del
    # duplicado (PubMed), para no perder el texto completo por el orden de bases.
    recs = [
        SearchRecord(
            record_id="a", title="T", doi="10.1/x", source_db="OpenAlex", extra={"oa_url": "u"}
        ),
        SearchRecord(
            record_id="b", title="T", doi="10.1/X", source_db="PubMed", extra={"pmcid": "PMC1"}
        ),
    ]
    unique, discarded = deduplicate(recs)
    assert discarded == 1
    assert len(unique) == 1
    assert unique[0].source_db == "OpenAlex"  # conserva el primero visto
    assert unique[0].extra["pmcid"] == "PMC1"  # ...pero hereda el pmcid del duplicado
    assert unique[0].extra["oa_url"] == "u"  # y conserva lo suyo


def test_dedup_no_sobreescribe_extra_existente() -> None:
    recs = [
        SearchRecord(record_id="a", title="T", doi="10.1/x", extra={"pmcid": "PMC_KEEP"}),
        SearchRecord(record_id="b", title="T", doi="10.1/X", extra={"pmcid": "PMC_OTHER"}),
    ]
    unique, _ = deduplicate(recs)
    assert unique[0].extra["pmcid"] == "PMC_KEEP"  # el valor del conservado no se pisa


def test_dedup_ids_repetidos_se_desambiguan() -> None:
    # Hallazgo 3 del spec: el RIS conserva doi="https://doi.org/…" (otra clave de
    # dedup) pero su id es el mismo que el del artículo traído de OpenAlex.
    ris = "TY  - JOUR\nTI  - Mismo artículo\nDO  - https://doi.org/10.1000/ABC\nER  -\n"
    (importado,) = parse_ris(ris)
    openalex = SearchRecord(
        record_id="10.1000/abc", title="Mismo artículo", doi="10.1000/abc", source_db="OpenAlex"
    )
    assert importado.record_id == openalex.record_id == "10.1000/abc"

    unicos, informe = deduplicate_with_report([openalex, importado, importado.model_copy()])
    assert [r.record_id for r in unicos] == ["10.1000/abc", "10.1000/abc#2"]
    assert [(r.from_id, r.to_id) for r in informe.renamed] == [("10.1000/abc", "10.1000/abc#2")]
    assert (informe.n_in, informe.n_out) == (3, 2)
    (duplicado,) = informe.duplicates
    assert duplicado.kept_record_id == "10.1000/abc#2"  # el id final del conservado
    assert duplicado.key == "doi:https://doi.org/10.1000/abc"
    assert importado.record_id == "10.1000/abc"  # el original no se toca


def test_records_json_previo_a_fusion_de_dedup(tmp_path: Path) -> None:
    def busqueda(query: str, n: int) -> list[SearchRecord]:
        return [
            SearchRecord(record_id="a", title="Uno", doi="10.1/x", source_db="OpenAlex"),
            SearchRecord(
                record_id="b",
                title="Uno (PubMed)",
                doi="10.1/X",
                source_db="PubMed",
                extra={"pmcid": "PMC1"},
            ),
        ]

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=busqueda)

    crudos = json.loads((ctx.run_dir / "01_search" / "records.json").read_text("utf-8"))
    assert [r["extra"] for r in crudos] == [{}, {"pmcid": "PMC1"}]  # antes de la fusión
    unicos = json.loads((ctx.run_dir / "02_dedup" / "records.json").read_text("utf-8"))
    assert [(r["record_id"], r["extra"]) for r in unicos] == [("a", {"pmcid": "PMC1"})]
    informe = DedupReport.model_validate_json(
        (ctx.run_dir / "02_dedup" / "dedup.json").read_text("utf-8")
    )
    assert [(d.record_id, d.kept_record_id) for d in informe.duplicates] == [("b", "a")]
