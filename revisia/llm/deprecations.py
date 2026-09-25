"""Modelos retirados por su proveedor.

El quickstart de v0.6.0 se rompió en silencio: el modelo por defecto
(``gemini-2.0-flash``) se apagó el 2026-06-01 y la primera llamada devolvía un
404 a mitad de corrida (auditoría 2026-09-03, C4). Esta tabla permite que
``revisia validate`` lo detecte ANTES de gastar una corrida.

Se mantiene a mano: la fuente es la documentación oficial de cada proveedor.
Gemini: https://ai.google.dev/gemini-api/docs/deprecations y
https://ai.google.dev/gemini-api/docs/changelog (consultadas 2026-09-08).
La clave es el id canónico del proveedor; ``retirement_for`` también reconoce
los prefijos de ruta (``models/``, ``google/``…) y las variantes ``:tag``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

RETIRED_MODELS: dict[str, date] = {
    "gemini-2.0-flash": date(2026, 6, 1),
    "gemini-2.0-flash-001": date(2026, 6, 1),
    "gemini-2.0-flash-lite": date(2026, 6, 1),
    "gemini-2.0-flash-lite-001": date(2026, 6, 1),
    "gemini-2.5-flash": date(2026, 10, 16),
    "gemini-2.5-flash-lite": date(2026, 10, 16),
    "gemini-2.5-pro": date(2026, 10, 16),
    "gemini-3.1-flash-lite-preview": date(2026, 5, 25),
}


@dataclass(frozen=True, slots=True)
class Retirement:
    """Retirada anunciada de un modelo."""

    model: str
    shutdown: date

    def is_past(self, today: date) -> bool:
        """``True`` si el modelo ya está apagado en ``today``."""
        return today >= self.shutdown


def _candidate_ids(model: str) -> tuple[str, ...]:
    """Ids con los que buscar ``model`` en la tabla.

    Un mismo modelo se escribe con prefijo según la vía de acceso:
    ``models/gemini-2.0-flash`` (recurso de la API de Gemini),
    ``google/gemini-2.0-flash-001`` o ``…:free`` (OpenRouter),
    ``publishers/google/models/…`` (Vertex AI). Se prueba el último segmento de
    la ruta, sin distinguir mayúsculas, y después sin la variante ``:tag``.
    """
    base = model.strip().lower().rsplit("/", 1)[-1]
    sin_variante = base.split(":", 1)[0]
    return (base, sin_variante) if sin_variante != base else (base,)


def retirement_for(model: str) -> Retirement | None:
    """Retirada conocida de ``model``, o ``None`` si no consta ninguna.

    ``Retirement.model`` conserva el id tal como se escribió, para que el
    mensaje al usuario coincida con su ``protocol.yml``.
    """
    for candidate in _candidate_ids(model):
        shutdown = RETIRED_MODELS.get(candidate)
        if shutdown is not None:
            return Retirement(model, shutdown)
    return None
