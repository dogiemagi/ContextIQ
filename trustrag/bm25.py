"""Okapi BM25 implemented from scratch (sparse / lexical retrieval)."""
from __future__ import annotations

import math
from collections import Counter

import numpy as np


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = np.array([len(d) for d in docs], dtype=np.float32)
        self.avgdl = float(self.len.mean()) if len(docs) else 0.0
        df: Counter = Counter()
        for d in self.tf:
            df.update(d.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query_terms: list[str]) -> np.ndarray:
        out = np.zeros(len(self.tf), dtype=np.float32)
        if not self.avgdl:
            return out
        for t in set(query_terms):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(t, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avgdl)
                    out[i] += idf * f * (self.k1 + 1) / denom
        return out
