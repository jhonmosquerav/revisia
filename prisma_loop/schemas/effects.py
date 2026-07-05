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

from pydantic import BaseModel

Measure = Literal["precomputed", "logOR", "MD", "SMD"]


class EffectInput(BaseModel):
    """Datos de un estudio para el meta-análisis (uno de los tres formatos)."""

    study_id: str
    label: str | None = None

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
        # Corrección de continuidad 0.5 (Haldane-Anscombe), robusta ante ceros.
        a = self.e1 + 0.5
        b = (self.n1 - self.e1) + 0.5
        c = self.e0 + 0.5
        d = (self.n0 - self.e0) + 0.5
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
