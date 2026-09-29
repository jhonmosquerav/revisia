"""Modelos retirados por su proveedor.

El quickstart de v0.6.0 se rompió en silencio: el modelo por defecto
(``gemini-2.0-flash``) se apagó el 2026-06-01 y la primera llamada devolvía un
404 a mitad de corrida (auditoría 2026-09-03, C4). Esta tabla permite que
``revisia validate`` lo detecte ANTES de gastar una corrida.

Se mantiene a mano y solo con fechas **publicadas** en la página oficial de
deprecaciones del proveedor: un anuncio que luego se retiró o un "no antes de"
no entra, porque ``validate`` y ``run`` rechazan con código 2 a partir de la
fecha y bloquearían protocolos que funcionan. (El 2026-10-16 de
``gemini-2.5-*`` entró por error en la Ola 0 desde una fuente secundaria: la
página de la Gemini API lo había retirado.)
Gemini: https://ai.google.dev/gemini-api/docs/deprecations (consultada
2026-09-28; ids copiados literalmente de sus tablas de modelos de texto).
La clave es el id canónico del proveedor; ``retirement_for`` también reconoce
los prefijos de ruta (``models/``, ``google/``…) y las variantes ``:tag``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

RETIRED_MODELS: dict[str, date] = {
    # Gemini 2.0
    "gemini-2.0-flash": date(2026, 6, 1),
    "gemini-2.0-flash-001": date(2026, 6, 1),
    "gemini-2.0-flash-lite": date(2026, 6, 1),
    "gemini-2.0-flash-lite-001": date(2026, 6, 1),
    "gemini-2.0-flash-lite-preview": date(2025, 12, 9),
    "gemini-2.0-flash-lite-preview-02-05": date(2025, 12, 9),
    # Gemini 2.5: solo las preview; las estables no tienen fecha anunciada.
    "gemini-2.5-pro-preview-03-25": date(2025, 12, 2),
    "gemini-2.5-pro-preview-05-06": date(2025, 12, 2),
    "gemini-2.5-pro-preview-06-05": date(2025, 12, 2),
    "gemini-2.5-flash-preview-05-20": date(2025, 11, 18),
    "gemini-2.5-flash-preview-09-25": date(2026, 2, 17),
    "gemini-2.5-flash-lite-preview-09-2025": date(2026, 3, 31),
    # Gemini 3.x
    "gemini-3.1-flash-lite-preview": date(2026, 5, 25),
    "gemini-3.1-flash-lite": date(2027, 5, 7),
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
