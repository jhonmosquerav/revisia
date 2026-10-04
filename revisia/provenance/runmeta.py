"""RunMeta · metadatos de procedencia de cada llamada a un LLM.

Cada invocación de un proveedor devuelve, junto al resultado, un ``RunMeta``
que captura todo lo necesario para PRISMA-trAIce y para reproducir (o declarar
la no-reproducibilidad de) la llamada: proveedor, modelo, versión, seed,
temperatura, hash del prompt y de la respuesta, timestamp y tokens.

El campo ``deterministic`` es honesto a propósito: vale ``True`` solo si el
proveedor garantiza salida estable a igualdad de seed/params. Cuando es
``False``, el manifiesto declara que la ejecución es reproducible "a nivel
decisión" (vía el ledger) pero no "a nivel token".
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def sha256_text(text: str) -> str:
    """Devuelve el hash SHA-256 hexadecimal de un texto (UTF-8)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    """Timestamp ISO-8601 en UTC del instante actual."""
    return datetime.now(UTC).isoformat()


def canonical_json(value: object) -> str:
    """Serialización JSON canónica: claves ordenadas, sin espacios, UTF-8 literal.

    Es la base de todos los hashes de contenido de la Ola 1 (``request_sha256``,
    ``decision_sha256``, ``input_sha256`` del diario): dos estructuras iguales
    dan el mismo texto sin importar el orden de inserción de sus claves.
    ``allow_nan=False`` rechaza ``NaN``/``Infinity``, que no son JSON y harían
    el hash irreproducible fuera de Python (spec 2026-10-04 §4.1).

    Raises:
        ValueError: si ``value`` contiene ``NaN`` o infinitos.
        TypeError: si ``value`` no es serializable a JSON.
    """
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def canonical_sha256(value: object) -> str:
    """SHA-256 hexadecimal de ``canonical_json(value)`` codificado en UTF-8."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class RunMeta(BaseModel):
    """Procedencia de una sola llamada a un proveedor LLM.

    Attributes:
        provider: identificador del proveedor (ej. ``"gemini"``).
        model: nombre del modelo solicitado.
        model_version: versión exacta reportada por el proveedor, si la da.
        seed: semilla usada (``None`` si el proveedor no la soporta).
        temperature: temperatura de muestreo usada.
        top_p: nucleus sampling, si se usó.
        prompt_sha256: hash del prompt efectivo (system + prompt).
        response_sha256: hash de la respuesta cruda.
        timestamp_utc: instante de la llamada.
        input_tokens: tokens de entrada, si el proveedor los reporta.
        output_tokens: tokens de salida, si el proveedor los reporta.
        deterministic: ``True`` solo si el proveedor garantiza determinismo.
    """

    provider: str
    model: str
    model_version: str | None = None
    seed: int | None = None
    temperature: float
    top_p: float | None = None
    prompt_sha256: str
    response_sha256: str
    timestamp_utc: str = Field(default_factory=utc_now_iso)
    input_tokens: int | None = None
    output_tokens: int | None = None
    deterministic: bool = False
