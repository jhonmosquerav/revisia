"""Grounding / RAG: embedders y store para verificación semántica de citas."""

from __future__ import annotations

from revisia.rag.embed import Embedder, GeminiEmbedder, HashEmbedder
from revisia.rag.store import InMemoryVectorStore, cosine, semantic_similarity

__all__ = [
    "Embedder",
    "GeminiEmbedder",
    "HashEmbedder",
    "InMemoryVectorStore",
    "cosine",
    "semantic_similarity",
]
