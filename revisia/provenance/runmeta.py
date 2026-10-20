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
from typing import Literal

from pydantic import BaseModel, Field

RUNMETA_SCHEMA_VERSION: int = 2
"""Versión del esquema de ``RunMeta``. Vive aquí (y no en ``schemas.artifacts``) porque
``schemas.artifacts`` importa este módulo y no al revés."""

Outcome = Literal["ok", "invalid_output", "transient_error", "deterministic_error"]
ModelSource = Literal["config", "backend", "callback"]


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
    """Procedencia de un intento de llamada a un proveedor LLM (una meta por intento, D14).

    Los campos de la v1 conservan su significado: dicen **lo pedido**. Los
    ``*_applied`` dicen **lo aplicado** de verdad por el backend (A6): un CLI que
    ignora la seed deja ``seed_applied=None`` aunque ``seed`` valga 7. Los defaults
    de la v2 reproducen la v1, así que una línea escrita por la 0.8 valida sin tocarla.

    Attributes:
        provider: identificador del proveedor (ej. ``"gemini"``).
        model: nombre del modelo solicitado.
        model_version: versión exacta reportada por el proveedor, si la da.
        seed: semilla pedida (``None`` si el proveedor no la soporta).
        temperature: temperatura pedida.
        top_p: nucleus sampling pedido, si se usó.
        prompt_sha256: hash del texto enviado, con el schema inyectado y el sufijo
            de reintento cuando van en el texto (A7).
        response_sha256: hash de la respuesta cruda; un intento fallido hashea el
            texto crudo recibido (o ``""``).
        timestamp_utc: instante de la llamada.
        input_tokens: tokens de entrada, si el proveedor los reporta.
        output_tokens: tokens de salida, si el proveedor los reporta.
        deterministic: ``True`` solo si el proveedor garantiza determinismo.
        schema_version: versión del esquema de la meta (2).
        seed_applied: semilla realmente aplicada por el backend (A6).
        temperature_applied: temperatura realmente aplicada (A6).
        top_p_applied: top_p realmente aplicado (A6).
        schema_sha256: hash del schema de salida inyectado, si lo hubo.
        prompt_template: plantilla versionada renderizada (``"extraccion/v2.md"``).
        prompt_template_sha256: hash del contenido de esa plantilla.
        attempt: número de intento dentro de la llamada lógica (desde 1).
        outcome: resultado del intento (D9: separa reanudar de pasar al humano).
        effort: esfuerzo de razonamiento aplicado, si el backend lo admite.
        backend_version: versión del backend (p. ej. del CLI).
        latency_ms: duración del intento en milisegundos.
        cost_usd: coste reportado del intento (D12).
        model_source: de dónde salió el nombre del modelo (config, backend o callback).
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
    schema_version: int = RUNMETA_SCHEMA_VERSION
    seed_applied: int | None = None
    temperature_applied: float | None = None
    top_p_applied: float | None = None
    schema_sha256: str | None = None
    prompt_template: str | None = None
    prompt_template_sha256: str | None = None
    attempt: int = Field(default=1, ge=1)
    outcome: Outcome = "ok"
    effort: str | None = None
    backend_version: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    model_source: ModelSource = "config"
