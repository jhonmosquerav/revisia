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
_PUNTUACION_FINAL = ".,;"
_PAREJAS = {")": "(", "]": "["}


def _sin_puntuacion_final(texto: str) -> str:
    """Quita la puntuación final de una frase y los cierres que no abren dentro del DOI.

    ``10.1000/abc(1)`` es un DOI real (el paréntesis abre dentro): solo se quita un ``)`` o un
    ``]`` final desbalanceado, el que viene de copiar el DOI de una cita entre paréntesis.
    """
    while texto:
        ultimo = texto[-1]
        desbalanceado = ultimo in _PAREJAS and texto.count(ultimo) > texto.count(_PAREJAS[ultimo])
        if ultimo not in _PUNTUACION_FINAL and not desbalanceado:
            return texto
        texto = texto[:-1]
    return texto


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
    # Un DOI empieza por `10.`: un `(` o `[` inicial es de la frase (`(doi:10.1000/xyz)`).
    while (sin_prefijo := _PREFIJO_RE.sub("", texto.lstrip("([").strip(), count=1)) != texto:
        texto = sin_prefijo.strip()
    texto = _sin_puntuacion_final(texto.lower())

    return texto if DOI_RE.match(texto) else None


def doi_url(doi: str) -> str:
    """URL canónica de un DOI ya normalizado (no lo re-normaliza)."""
    return f"https://doi.org/{doi}"
