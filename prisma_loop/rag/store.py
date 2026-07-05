"""Similitud y store vectorial para grounding.

``InMemoryVectorStore`` es el store por defecto: portátil, sin Docker ni Qdrant,
para que el investigador externo corra el grounding sin infraestructura. Un store
sobre Qdrant puede añadirse después con la misma interfaz para corpus grandes.
"""

from __future__ import annotations

import math

from prisma_loop.rag.embed import Embedder


def cosine(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores (0.0 si alguno es nulo)."""
    if len(a) != len(b):
        raise ValueError("Los vectores deben tener la misma dimensión.")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def semantic_similarity(embedder: Embedder, a: str, b: str) -> float:
    """Similitud semántica entre dos textos según un embedder."""
    return cosine(embedder.embed(a), embedder.embed(b))


class InMemoryVectorStore:
    """Store vectorial en memoria (coseno por fuerza bruta)."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self._vectors: dict[str, list[float]] = {}

    def add(self, doc_id: str, text: str) -> None:
        self._vectors[doc_id] = self.embedder.embed(text)

    def similarity_to(self, text: str, doc_id: str) -> float | None:
        """Similitud del texto con un documento almacenado (``None`` si no existe)."""
        stored = self._vectors.get(doc_id)
        if stored is None:
            return None
        return cosine(self.embedder.embed(text), stored)

    def most_similar(self, text: str, top_k: int = 1) -> list[tuple[str, float]]:
        query = self.embedder.embed(text)
        scored = [(doc_id, cosine(query, vec)) for doc_id, vec in self._vectors.items()]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
