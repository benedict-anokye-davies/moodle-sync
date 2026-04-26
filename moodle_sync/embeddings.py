from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import numpy as np

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    model_name = "hashing-fallback"
    dimensions = 384

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            vector = np.zeros(self.dimensions, dtype=np.float32)
            for token in TOKEN_RE.findall(text.lower()):
                digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "little") % self.dimensions
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign
            norm = float(np.linalg.norm(vector))
            if norm:
                vector /= norm
            rows.append(vector)
        return np.vstack(rows) if rows else np.empty((0, self.dimensions), dtype=np.float32)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        dim = self._model.get_sentence_embedding_dimension()
        self.dimensions = int(dim or 384)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)


def get_embedder(provider: str = "local", model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> Embedder:
    if provider != "local":
        raise ValueError(f"Unsupported embedding provider for M1: {provider}")
    try:
        return SentenceTransformerEmbedder(model_name)
    except Exception:
        return HashingEmbedder()


def cosine_scores(query_vector: np.ndarray, vectors: list[np.ndarray]) -> list[float]:
    if not vectors:
        return []
    matrix = np.vstack(vectors).astype(np.float32)
    query = query_vector.astype(np.float32)
    q_norm = float(np.linalg.norm(query)) or 1.0
    m_norm = np.linalg.norm(matrix, axis=1)
    m_norm[m_norm == 0] = 1.0
    return ((matrix @ query) / (m_norm * q_norm)).astype(float).tolist()
