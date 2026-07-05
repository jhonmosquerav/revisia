"""Embedders para grounding.

Dos implementaciones:

- :class:`HashEmbedder` — determinista, offline, sin dependencias (truco de
  hashing / bag-of-words). No es semántico "de verdad", pero captura solape
  léxico, es portátil (no exige Qdrant ni API) y reproducible. Es el default
  para que cualquiera corra el grounding sin infraestructura.
- :class:`GeminiEmbedder` — embeddings semánticos reales vía ``google-genai``.
  Opt-in.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol, runtime_checkable

_TOKEN_RE = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)


@runtime_checkable
class Embedder(Protocol):
    """Contrato mínimo de un embedder."""

    name: str

    def embed(self, text: str) -> list[float]:
        """Devuelve el vector de un texto."""
        ...


class HashEmbedder:
    """Embedder determinista por hashing de tokens (portátil, sin red)."""

    name = "hash"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _TOKEN_RE.findall(text.lower()):
            bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec


class GeminiEmbedder:
    """Embedder semántico vía Google Gemini (``google-genai``). Opt-in."""

    name = "gemini"

    def __init__(self, model: str = "gemini-embedding-001", dim: int = 768) -> None:
        self.model = model
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        from google import genai
        from google.genai import types as genai_types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY no está definida en el entorno.")
        client = genai.Client(api_key=api_key)
        result = client.models.embed_content(
            model=self.model,
            contents=text,
            config=genai_types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT", output_dimensionality=self.dim
            ),
        )
        return list(result.embeddings[0].values)


class FastEmbedEmbedder:
    """Embedder semántico **local** vía ``fastembed`` (ONNX en CPU). Opt-in.

    Costo cero y offline tras una descarga única del modelo (open weights): no usa
    API ni claves. Un modelo multilingüe (p. ej. ``intfloat/multilingual-e5-small``)
    permite grounding cruzando idiomas (síntesis en español vs. fuentes en inglés)
    sin servicios de pago. Requiere ``uv add fastembed``; si no está instalado,
    falla con un mensaje accionable (es un **enganche preparado, apagado por
    defecto**). El modo por defecto del pipeline NO lo usa.
    """

    name = "fastembed"

    def __init__(self, model: str = "intfloat/multilingual-e5-small") -> None:
        self.model = model
        self._embedder = None  # carga perezosa (descarga del modelo en el 1.er uso)

    def _ensure(self):
        if self._embedder is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError(
                    "El embedder 'fastembed' requiere la dependencia opcional "
                    "'fastembed' (local, sin API). Instálala con `uv add fastembed` "
                    "o usa grounding='agent' (sin vectores). Detalle: " + str(exc)
                ) from exc
            self._embedder = TextEmbedding(model_name=self.model)
        return self._embedder

    def embed(self, text: str) -> list[float]:
        embedder = self._ensure()
        return list(next(iter(embedder.embed([text]))))
