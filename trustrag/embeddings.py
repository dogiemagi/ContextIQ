"""Embedding back-ends behind one interface.

* HashingEmbedder - zero-dependency IDF-weighted hashed bag of uni+bi-grams. Deterministic,
  fast, and what the tests/CI use.
* STEmbedder      - real semantic embeddings via sentence-transformers (EMBEDDINGS=st).
"""
from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np

from .text import content_terms


class HashingEmbedder:
    name = "hashing"

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.idf = np.ones(dim, dtype=np.float32)

    def _features(self, text: str) -> list[tuple[str, float]]:
        terms = content_terms(text)
        feats = [(t, 1.0) for t in terms]
        feats += [(f"{a}_{b}", 0.7) for a, b in zip(terms, terms[1:])]
        return feats

    def _bucket(self, feat: str) -> int:
        return zlib.crc32(feat.encode("utf-8")) % self.dim

    def fit(self, texts: list[str]) -> None:
        df = np.zeros(self.dim, dtype=np.float32)
        for t in texts:
            df[list({self._bucket(f) for f, _ in self._features(t)})] += 1
        n = len(texts)
        self.idf = (np.log((n + 1) / (df + 1)) + 1).astype(np.float32)

    def embed(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        counts: dict[int, float] = {}
        for f, w in self._features(text):
            b = self._bucket(f)
            counts[b] = counts.get(b, 0.0) + w
        for b, c in counts.items():
            v[b] = (1.0 + np.log(c)) * self.idf[b] if c >= 1 else c * self.idf[b]
        norm = np.linalg.norm(v)
        return v / norm if norm else v

    def embed_many(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self.embed(t) for t in texts]) if texts else np.zeros((0, self.dim), np.float32)

    def save(self, path: Path) -> None:
        np.savez(path, idf=self.idf)

    def load(self, path: Path) -> None:
        self.idf = np.load(path)["idf"]


class STEmbedder:
    name = "st"

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # optional dependency

        self.model = SentenceTransformer(model)
        self.dim = self.model.get_sentence_embedding_dimension()

    def fit(self, texts: list[str]) -> None:  # pre-trained: nothing to fit
        return None

    def embed(self, text: str) -> np.ndarray:
        return self.model.encode(text, normalize_embeddings=True).astype(np.float32)

    def embed_many(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True).astype(np.float32)

    def save(self, path: Path) -> None:
        return None

    def load(self, path: Path) -> None:
        return None


def get_embedder(kind: str):
    if kind == "st":
        return STEmbedder()
    return HashingEmbedder()
