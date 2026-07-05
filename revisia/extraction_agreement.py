"""Doble extracción independiente + acuerdo entre extractores (§6 del canon).

PRISMA exige que **al menos el 20%** de los estudios se extraigan por duplicado y
se reporte el acuerdo entre extractores. Aquí:

- ``select_double_extraction_subset`` elige de forma determinista ≥20% de los
  estudios incluidos (espaciados para representatividad).
- ``compute_extraction_agreement`` contrasta dos juegos de extracción y reporta
  acuerdo de valor + Cohen's kappa sobre la *presencia* de cada campo.

La segunda extracción la produce un segundo extractor (otro modelo de
``ensemble_llm['extraccion']`` o el mismo con otra semilla); este módulo solo
mide el acuerdo, no extrae.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from revisia.metrics import cohen_kappa
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.records import SearchRecord


class ExtractionAgreement(BaseModel):
    """Acuerdo entre dos extractores sobre el subconjunto de doble extracción."""

    n_studies: int = 0
    n_field_pairs: int = 0
    n_value_match: int = 0
    value_agreement: float | None = None
    presence_kappa: float = 0.0


def select_double_extraction_subset(
    included: list[SearchRecord], *, fraction: float = 0.20
) -> list[SearchRecord]:
    """Selecciona ≥``fraction`` de los incluidos, espaciados y determinista."""
    n = len(included)
    if n == 0:
        return []
    k = max(1, math.ceil(fraction * n))
    ordered = sorted(included, key=lambda r: r.record_id)
    if k >= n:
        return ordered
    # Índices espaciados uniformemente (representatividad, no los k primeros).
    step = n / k
    idxs = sorted({min(n - 1, int(i * step)) for i in range(k)})
    return [ordered[i] for i in idxs]


def _norm(value: str | None) -> str | None:
    """Normaliza un valor de campo para comparar (minúsculas, sin espacios extra)."""
    if value is None:
        return None
    return " ".join(value.lower().split()) or None


def compute_extraction_agreement(
    primary: dict[str, ExtractionRecord],
    secondary: dict[str, ExtractionRecord],
) -> ExtractionAgreement:
    """Mide el acuerdo entre dos extracciones sobre los estudios en común."""
    common = sorted(set(primary) & set(secondary))
    present_a: list[bool] = []
    present_b: list[bool] = []
    n_pairs = 0
    n_match = 0
    for study_id in common:
        fields_a = primary[study_id].fields
        fields_b = secondary[study_id].fields
        for key in sorted(set(fields_a) | set(fields_b)):
            va = _norm(fields_a[key].value) if key in fields_a else None
            vb = _norm(fields_b[key].value) if key in fields_b else None
            present_a.append(va is not None)
            present_b.append(vb is not None)
            n_pairs += 1
            if va is not None and va == vb:
                n_match += 1

    return ExtractionAgreement(
        n_studies=len(common),
        n_field_pairs=n_pairs,
        n_value_match=n_match,
        value_agreement=(n_match / n_pairs) if n_pairs else None,
        presence_kappa=cohen_kappa(present_a, present_b) if n_pairs else 0.0,
    )
