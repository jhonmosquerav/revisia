"""Tests de los exportadores de bibliografía (BibTeX) y tabla de extracción."""

from __future__ import annotations

from revisia.exports import render_bibtex, render_extraction_table
from revisia.schemas.extraction import ExtractionField, ExtractionRecord
from revisia.schemas.records import SearchRecord


def _record(rid: str = "10.1/abc", **kw) -> SearchRecord:
    base = dict(
        record_id=rid,
        title="Un estudio | con pipe",
        authors=["Doe, Jane", "Roe, Ada"],
        year=2025,
        doi="10.1/abc",
        url="https://example.org/abc",
        source_db="OpenAlex",
    )
    base.update(kw)
    return SearchRecord(**base)


# ── Bibliografía BibTeX ────────────────────────────────────────────────


def test_bibtex_incluye_clave_titulo_y_doi() -> None:
    bib = render_bibtex([_record()])
    assert "@article{10_1_abc," in bib  # clave saneada del record_id
    assert "author = {Doe, Jane and Roe, Ada}" in bib  # autores con ' and '
    assert "year = {2025}" in bib
    assert "doi = {10.1/abc}" in bib


def test_bibtex_sin_year_usa_misc() -> None:
    bib = render_bibtex([_record(year=None)])
    assert bib.startswith("@misc{")


def test_bibtex_neutraliza_llaves() -> None:
    bib = render_bibtex([_record(title="Título con {llaves}")])
    assert "{llaves}" not in bib  # las llaves se neutralizan a paréntesis
    assert "(llaves)" in bib


def test_bibtex_vacio_es_valido() -> None:
    assert render_bibtex([]).startswith("%")  # comentario, no entrada rota


# ── Tabla de extracción ────────────────────────────────────────────────


def _extraction(rid: str, value: str, status: str = "verified") -> ExtractionRecord:
    return ExtractionRecord(
        study_id=rid,
        fields={"diseño": ExtractionField(value=value, status=status)},
    )


def test_tabla_extraccion_lista_estudios_y_valores() -> None:
    rec = _record(rid="10.1/abc")
    table = render_extraction_table([rec], {"10.1/abc": _extraction("10.1/abc", "RCT")})
    assert "Características de los estudios incluidos" in table
    assert "| diseño |" in table  # columna por campo
    assert "RCT" in table
    assert "10.1/abc" in table


def test_tabla_extraccion_marca_needs_review() -> None:
    rec = _record(rid="r2")
    table = render_extraction_table(
        [rec], {"r2": _extraction("r2", "cohorte", status="needs_review")}
    )
    assert "cohorte ⚠️" in table
    assert "needs_review" in table  # leyenda explicativa


def test_tabla_extraccion_sin_estudios() -> None:
    assert "_(sin estudios incluidos)_" in render_extraction_table([], {})


def test_tabla_extraccion_sin_campos_usa_titulo() -> None:
    rec = _record(rid="r3", title="Mi estudio")
    table = render_extraction_table([rec], {})  # sin extracciones
    assert "| Estudio | Título |" in table
    assert "Mi estudio" in table
