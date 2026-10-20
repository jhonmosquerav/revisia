"""Ingesta de registros desde exportaciones externas (RIS/BibTeX)."""

from __future__ import annotations

from revisia.ingest.doi import doi_url, normalize_doi
from revisia.ingest.manual_import import (
    import_directory,
    import_file,
    parse_bibtex,
    parse_ris,
)

__all__ = [
    "doi_url",
    "import_directory",
    "import_file",
    "normalize_doi",
    "parse_bibtex",
    "parse_ris",
]
