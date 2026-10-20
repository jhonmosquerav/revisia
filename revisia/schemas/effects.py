"""Tamaños de efecto para el meta-análisis cuantitativo (§8.1 del canon).

Cada estudio aporta un efecto ``yi`` y su varianza ``vi``. El usuario puede darlos
precomputados o dejar que el sistema los derive de datos crudos:

- ``logOR`` · tabla 2×2 binaria (eventos/total por brazo) → log odds-ratio.
- ``MD``   · medias continuas (media/DE/n por brazo) → diferencia de medias.
- ``SMD``  · medias continuas → diferencia estandarizada (Hedges' g).

Determinista, sin red ni LLM: los datos vienen de ``protocols/<slug>/effects.yml``.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from revisia.schemas.artifacts import ARTIFACT_SCHEMA_VERSION

Measure = Literal["precomputed", "logOR", "MD", "SMD"]
RandomMethod = Literal["DL", "HKSJ"]
ExcludedReason = Literal["not_included", "unit_of_analysis", "invalid"]


class EffectInput(BaseModel):
    """Datos de un estudio para el meta-análisis (uno de los tres formatos)."""

    study_id: str
    label: str | None = None
    # v2 (D16): desenlace y subgrupo del efecto. ``outcome`` es opcional en el modelo porque
    # ``examples/demo-mini-review/effects.yml`` y los tests de ``meta_analyze`` no lo traen;
    # PR-F lo exige en ``EffectsFile`` v2, que es donde el usuario ve el mensaje de migración.
    outcome: str | None = None
    subgroup: str | None = None

    # Precomputado.
    yi: float | None = None
    vi: float | None = None

    # Binario 2×2: eventos y n por brazo (tratamiento/control).
    e1: int | None = None
    n1: int | None = None
    e0: int | None = None
    n0: int | None = None

    # Continuo: media, DE y n por brazo.
    m1: float | None = None
    sd1: float | None = None
    cn1: int | None = None
    m0: float | None = None
    sd0: float | None = None
    cn0: int | None = None

    def to_yi_vi(self, measure: Measure) -> tuple[float, float]:
        """Devuelve ``(yi, vi)`` según la medida elegida.

        Raises:
            ValueError: si faltan datos para la medida pedida.
        """
        if measure == "precomputed":
            if self.yi is None or self.vi is None:
                raise ValueError(f"{self.study_id}: faltan yi/vi precomputados.")
            return self.yi, self.vi
        if measure == "logOR":
            return self._log_or()
        if measure in ("MD", "SMD"):
            return self._continuous(measure)
        raise ValueError(f"Medida desconocida: {measure!r}.")

    def _log_or(self) -> tuple[float, float]:
        if None in (self.e1, self.n1, self.e0, self.n0):
            raise ValueError(f"{self.study_id}: faltan e1/n1/e0/n0 para logOR.")
        a = self.e1
        b = self.n1 - self.e1
        c = self.e0
        d = self.n0 - self.e0
        # Corrección de continuidad 0.5 (Haldane-Anscombe) SOLO si alguna celda es
        # 0: aplicarla siempre sesga hacia el nulo (+0,017 medido en la auditoría
        # 2026-09-03, M10; Sweeting, Sutton y Lambert 2004).
        if 0 in (a, b, c, d):
            a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
        yi = math.log((a * d) / (b * c))
        vi = 1 / a + 1 / b + 1 / c + 1 / d
        return yi, vi

    def _continuous(self, measure: Measure) -> tuple[float, float]:
        if None in (self.m1, self.sd1, self.cn1, self.m0, self.sd0, self.cn0):
            raise ValueError(f"{self.study_id}: faltan medias/DE/n para {measure}.")
        n1, n0 = self.cn1, self.cn0
        if measure == "MD":
            yi = self.m1 - self.m0
            vi = self.sd1**2 / n1 + self.sd0**2 / n0
            return yi, vi
        # SMD · Hedges' g (con corrección de sesgo de muestra pequeña J).
        sp = math.sqrt(((n1 - 1) * self.sd1**2 + (n0 - 1) * self.sd0**2) / (n1 + n0 - 2))
        d = (self.m1 - self.m0) / sp
        j = 1 - 3 / (4 * (n1 + n0) - 9)
        g = j * d
        vi = (n1 + n0) / (n1 * n0) + g**2 / (2 * (n1 + n0))
        return g, vi


class MultiplePerStudy(BaseModel):
    """Declaración del protocolo sobre varios efectos por estudio (D16).

    Dos efectos del mismo estudio y desenlace no son independientes; el Cochrane Handbook
    (§23.3) pide decidir la unidad de análisis y justificarla. Por eso, si ``allowed``, la
    justificación no puede ir vacía.
    """

    allowed: bool
    justification: str

    @model_validator(mode="after")
    def _justificacion(self) -> MultiplePerStudy:
        if self.allowed and not self.justification.strip():
            raise ValueError("allowed=true exige una justificación (Cochrane Handbook §23.3).")
        return self


class ExcludedEffect(BaseModel):
    """Efecto que quedó fuera del meta-análisis y por qué (D16)."""

    study_id: str
    outcome: str | None = None
    reason: ExcludedReason
    detail: str | None = None


class ExcludedEffectsFile(BaseModel):
    """``08_meta/excluded_effects.json``: lo que no entró y los incluidos sin efecto (D16)."""

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    excluded: list[ExcludedEffect] = Field(default_factory=list)
    included_without_effect: list[str] = Field(default_factory=list)


class PredictionInterval(BaseModel):
    """Intervalo de predicción del efecto aleatorio, con sus grados de libertad."""

    low: float
    high: float
    df: int = Field(ge=1)


class DuplicateEffect(BaseModel):
    """Grupo de estudios con el mismo ``(yi, vi)``: posible doble conteo (D16)."""

    study_ids: list[str] = Field(min_length=2)
    yi: float
    vi: float
