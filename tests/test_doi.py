"""La única normalización de DOI del paquete (spec 2026-10-18 §6, D19; auditoría A4)."""

from __future__ import annotations

import pytest

from revisia.ingest.doi import DOI_RE, doi_url, normalize_doi


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("10.1000/abc", "10.1000/abc"),
        ("10.1000/ABC", "10.1000/abc"),
        ("https://doi.org/10.1000/ABC", "10.1000/abc"),  # la evidencia de A4
        ("HTTPS://DOI.ORG/10.1000/abc", "10.1000/abc"),
        ("http://dx.doi.org/10.1000/abc", "10.1000/abc"),
        ("doi:10.1000/abc", "10.1000/abc"),
        ("DOI: 10.1000/abc", "10.1000/abc"),
        ("info:doi/10.1000/abc", "10.1000/abc"),
        ("https://doi.org/10.1000%2Fabc", "10.1000/abc"),  # URL-encoded
        ("  10.1000/abc.  ", "10.1000/abc"),
        ("10.1000/abc).", "10.1000/abc"),
        ("10.1000/abc;", "10.1000/abc"),
        ("10.1000/abc]", "10.1000/abc"),
        ("10.1016/j.jclinepi.2021.03.001", "10.1016/j.jclinepi.2021.03.001"),
        ("10.1000/a(b)c", "10.1000/a(b)c"),  # paréntesis interno se conserva
    ],
)
def test_normalize_doi_tabla(crudo: str, esperado: str) -> None:
    assert normalize_doi(crudo) == esperado


@pytest.mark.parametrize(
    "no_doi",
    [
        "",
        "   ",
        "abc",
        "11.1000/abc",
        "10.12/abc",
        "10.1000/",
        "10.1000",
        "PMC123",
        "https://example.org/x",
        None,
        10.1,
        ["10.1000/abc"],
    ],
)
def test_normalize_doi_lo_que_no_es_doi_es_none(no_doi: object) -> None:
    assert normalize_doi(no_doi) is None


def test_normalize_doi_es_idempotente() -> None:
    for crudo in ("https://doi.org/10.1000/ABC", "doi:10.1000/abc", "10.1000/abc"):
        una = normalize_doi(crudo)
        assert una is not None and normalize_doi(una) == una


def test_doi_url_y_patron() -> None:
    assert doi_url("10.1000/abc") == "https://doi.org/10.1000/abc"
    assert DOI_RE.match("10.1000/abc") and not DOI_RE.match("10.1000/a b")
