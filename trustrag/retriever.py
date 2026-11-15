"""Vector store + hybrid retriever (dense + BM25 -> RRF fusion -> rerank -> MMR diversity)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .bm25 import BM25
from .chunking import Chunk
from .text import bigrams, content_terms

MODES = ("dense", "bm25", "hybrid", "hybrid_rerank")


@dataclass
class Hit:
    chunk: Chunk
    score: float
    dense: float = 0.0
    sparse: float = 0.0
    coverage: float = 0.0
    rank: int = 0


class VectorStore:
    """In-memory numpy matrix of L2-normalised vectors with on-disk persistence."""

    def __init__(self, embedder):
        self.embedder = embedder
        self.chunks: list[Chunk] = []
        self.matrix = np.zeros((0, getattr(embedder, "dim", 1)), dtype=np.float32)

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        texts = [c.embed_text for c in chunks]
        self.embedder.fit(texts)
        self.matrix = self.embedder.embed_many(texts)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "chunks.json").write_text(json.dumps([c.to_dict() for c in self.chunks]), encoding="utf-8")
        np.save(directory / "matrix.npy", self.matrix)
        self.embedder.save(directory / "embedder.npz")
        (directory / "meta.json").write_text(json.dumps({"embedder": self.embedder.name}), encoding="utf-8")

    def load(self, directory: Path) -> bool:
        try:
            meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
            if meta["embedder"] != self.embedder.name:
                return False
            self.chunks = [Chunk.from_dict(d) for d in json.loads((directory / "chunks.json").read_text(encoding="utf-8"))]
            self.matrix = np.load(directory / "matrix.npy")
            self.embedder.load(directory / "embedder.npz")
            return True
        except (FileNotFoundError, KeyError, ValueError):
            return False

    @property
    def version(self) -> str:
        h = hashlib.sha1()
        for c in self.chunks:
            h.update(c.id.encode())
            h.update(c.text.encode())
        return h.hexdigest()[:12]


def _rank_map(scores: np.ndarray, candidates: np.ndarray, n: int) -> dict[int, int]:
    order = [int(i) for i in np.argsort(-scores) if i in candidates][:n]
    return {idx: r for r, idx in enumerate(order) if scores[idx] > 0}


class HybridRetriever:
    RRF_K = 60

    def __init__(self, store: VectorStore):
        self.store = store
        self.version = store.version
        # Quarantined chunks (flagged at ingestion as prompt-injection) never become candidates.
        self.allowed = np.array([i for i, c in enumerate(store.chunks) if not c.flagged], dtype=int)
        self.bm25 = BM25([content_terms(c.embed_text) for c in store.chunks])

    @property
    def quarantined(self) -> list[Chunk]:
        return [c for c in self.store.chunks if c.flagged]

    def _coverage(self, q_terms: list[str], chunk: Chunk) -> float:
        if not q_terms:
            return 0.0
        terms = set(content_terms(chunk.embed_text))
        return sum(t in terms for t in set(q_terms)) / len(set(q_terms))

    def search(self, query: str, k: int = 4, mode: str = "hybrid_rerank", n_candidates: int = 20) -> list[Hit]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if not len(self.allowed):
            return []
        q_terms = content_terms(query)
        qvec = self.store.embedder.embed(query)
        dense = self.store.matrix @ qvec
        sparse = self.bm25.scores(q_terms)

        d_rank = _rank_map(dense, self.allowed, n_candidates)
        s_rank = _rank_map(sparse, self.allowed, n_candidates)

        if mode == "dense":
            fused = {i: 1 / (self.RRF_K + r + 1) for i, r in d_rank.items()}
        elif mode == "bm25":
            fused = {i: 1 / (self.RRF_K + r + 1) for i, r in s_rank.items()}
        else:  # Reciprocal Rank Fusion: robust to the two scores living on different scales
            fused = {}
            for ranks in (d_rank, s_rank):
                for i, r in ranks.items():
                    fused[i] = fused.get(i, 0.0) + 1 / (self.RRF_K + r + 1)
        if not fused:
            return []

        top_fused = max(fused.values())
        hits: list[Hit] = []
        q_bi = bigrams(q_terms)
        for i, f in fused.items():
            chunk = self.store.chunks[i]
            cov = self._coverage(q_terms, chunk)
            score = f / top_fused
            if mode == "hybrid_rerank":
                c_bi = bigrams(content_terms(chunk.embed_text))
                phrase = len(q_bi & c_bi) / len(q_bi) if q_bi else 0.0
                score = 0.45 * (f / top_fused) + 0.35 * cov + 0.20 * phrase
            hits.append(Hit(chunk, float(score), float(dense[i]), float(sparse[i]), cov))
        hits.sort(key=lambda h: h.score, reverse=True)

        if mode == "hybrid_rerank":
            hits = self._mmr(hits[:10], k)
        hits = hits[:k]
        for r, h in enumerate(hits, 1):
            h.rank = r
        return hits

    def _mmr(self, hits: list[Hit], k: int, lam: float = 0.75) -> list[Hit]:
        """Maximal Marginal Relevance: keep relevance high while discouraging near-duplicate chunks."""
        index = {c.id: i for i, c in enumerate(self.store.chunks)}
        selected: list[Hit] = []
        pool = list(hits)
        while pool and len(selected) < k:
            def mmr(h: Hit) -> float:
                if not selected:
                    return h.score
                v = self.store.matrix[index[h.chunk.id]]
                sim = max(float(v @ self.store.matrix[index[s.chunk.id]]) for s in selected)
                return lam * h.score - (1 - lam) * sim
            best = max(pool, key=mmr)
            selected.append(best)
            pool.remove(best)
        return selected
