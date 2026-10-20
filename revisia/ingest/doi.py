"""Normalización única de DOI (spec 2026-10-18 §6, D19; auditoría A4).

Sustituye a los cuatro normalizadores que hoy conviven y discrepan entre sí:
`busqueda._normalize_doi`, `open_backends._doi`, el `lower().strip()` de
`search_backends`/`ncbi` y el de `manual_import._record_id`. Con varias
versiones, un mismo DOI (`https://doi.org/10.1000/ABC` frente a `10.1000/abc`)
daba claves distintas y la deduplicación no lo reconocía como duplicado.

Aún sin cablear: `SearchRecord.doi`, los backends, `manual_import` y `dedup`
lo adoptan en PR-B.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

# Se pelan en bucle y sin distinguir mayúsculas: «doi: https://doi.org/…» es real.
_PREFIJO_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*|info:doi/)", re.IGNORECASE)
_PUNTUACION_FINAL = ".,;)]"


def normalize_doi(value: object) -> str | None:
    """Devuelve el DOI en minúsculas y sin prefijos, o `None` si no es un DOI.

    Los DOI no distinguen mayúsculas, por eso se pasa a minúsculas: es la clave
    de deduplicación. La puntuación final (`.`, `)`, …) suele venir de copiar el
    DOI desde una frase; los paréntesis internos se conservan.
    """
    if not isinstance(value, str):
        return None
    texto = unquote(value).strip()
    if not texto:
        return None
    while (sin_prefijo := _PREFIJO_RE.sub("", texto, count=1).strip()) != texto:
        texto = sin_prefijo
    texto = texto.lower().rstrip(_PUNTUACION_FINAL)
    return texto if DOI_RE.match(texto) else None


def doi_url(doi: str) -> str:
    """URL canónica de un DOI ya normalizado (no lo re-normaliza)."""
    return f"https://doi.org/{doi}"
