"""Importación manual de registros · RIS y BibTeX.

Las bases de pago (Scopus, Web of Science, EMBASE…) no exponen API abierta, pero
todas exportan RIS o BibTeX. El investigador deja esos archivos en
``protocols/<slug>/imported/`` y este módulo los convierte en ``SearchRecord``,
de modo que entran al mismo pipeline (dedup, screening, …) que las búsquedas
programáticas. Parsers en Python puro, sin dependencias.
"""

from __future__ import annotations

import re
from pathlib import Path

from revisia.provenance.runmeta import sha256_text
from revisia.schemas.records import SearchRecord


def _record_id(doi: str | None, title: str) -> str:
    if doi:
        return doi.lower().replace("https://doi.org/", "").strip()
    return f"hash:{sha256_text(title.strip().lower())[:16]}"


def _year(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"\d{4}", value)
    return int(m.group()) if m else None


def parse_ris(text: str, *, source_db: str = "imported-RIS") -> list[SearchRecord]:
    """Parsea un archivo RIS en una lista de ``SearchRecord``."""
    records: list[SearchRecord] = []
    cur: dict[str, list[str]] = {}

    def flush() -> None:
        if not cur:
            return
        title = (cur.get("TI") or cur.get("T1") or ["(sin título)"])[0]
        doi = (cur.get("DO") or [None])[0]
        records.append(
            SearchRecord(
                record_id=_record_id(doi, title),
                title=title,
                abstract=(cur.get("AB") or [None])[0],
                authors=cur.get("AU", []),
                year=_year((cur.get("PY") or cur.get("Y1") or [None])[0]),
                doi=doi.lower().strip() if doi else None,
                url=(cur.get("UR") or [None])[0],
                source_db=source_db,
            )
        )
        cur.clear()

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        m = re.match(r"^([A-Z][A-Z0-9])  - ?(.*)$", line)
        if not m:
            continue
        tag, value = m.group(1), m.group(2).strip()
        if tag == "ER":
            flush()
        else:
            cur.setdefault(tag, []).append(value)
    flush()
    return records


def parse_bibtex(text: str, *, source_db: str = "imported-BibTeX") -> list[SearchRecord]:
    """Parsea un archivo BibTeX en una lista de ``SearchRecord``.

    Parser pragmático: capta valores entre llaves o comillas sin anidamiento
    profundo (cubre las exportaciones de Scopus/WoS/EconLit). El primer token
    tras ``{`` es la clave de cita y se ignora.
    """
    records: list[SearchRecord] = []
    for entry in re.finditer(r"@(\w+)\s*\{([^@]*)", text, re.DOTALL):
        body = entry.group(2)
        fields: dict[str, str] = {}
        for fm in re.finditer(r'(\w+)\s*=\s*(?:\{([^{}]*)\}|"([^"]*)")', body):
            value = fm.group(2) if fm.group(2) is not None else fm.group(3)
            fields[fm.group(1).lower()] = " ".join(value.split())
        if not fields:  # entrada sin campos (p. ej. solo clave) → se ignora
            continue
        title = fields.get("title", "(sin título)")
        doi = fields.get("doi")
        authors = [a.strip() for a in re.split(r"\s+and\s+", fields.get("author", "")) if a.strip()]
        records.append(
            SearchRecord(
                record_id=_record_id(doi, title),
                title=title,
                abstract=fields.get("abstract"),
                authors=authors,
                year=_year(fields.get("year")),
                doi=doi.lower().strip() if doi else None,
                url=fields.get("url"),
                source_db=source_db,
            )
        )
    return records


def import_directory(directory: str | Path) -> list[SearchRecord]:
    """Importa todos los ``.ris``/``.bib`` de una carpeta (vacío si no existe)."""
    base = Path(directory)
    if not base.exists():
        return []
    records: list[SearchRecord] = []
    for path in sorted(base.iterdir()):
        suffix = path.suffix.lower()
        if suffix == ".ris":
            records += parse_ris(path.read_text(encoding="utf-8"))
        elif suffix in (".bib", ".bibtex"):
            records += parse_bibtex(path.read_text(encoding="utf-8"))
    return records
