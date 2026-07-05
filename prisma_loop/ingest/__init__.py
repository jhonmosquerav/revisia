"""Ingesta de registros desde exportaciones externas (RIS/BibTeX)."""

from __future__ import annotations

from prisma_loop.ingest.manual_import import (
    import_directory,
    parse_bibtex,
    parse_ris,
)

__all__ = ["import_directory", "parse_bibtex", "parse_ris"]
