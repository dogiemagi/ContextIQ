"""Semantic cache: reuse an answer when a *similar* question was answered before.

Keyed by index version, so re-ingesting documents automatically invalidates stale answers.
"""
from __future__ import annotations

import re
import time
from collections import OrderedDict
from typing import Any

import numpy as np


def _norm(q: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", q.lower()).strip()


class SemanticCache:
    def __init__(self, embedder, threshold: float = 0.93, ttl: int = 3600, max_size: int = 256):
        self.embedder, self.threshold, self.ttl, self.max_size = embedder, threshold, ttl, max_size
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, query: str, version: str) -> tuple[Any, float] | None:
        now = time.time()
        key = _norm(query)
        qvec = None
        best, best_sim, best_key = None, 0.0, None
        for k, item in list(self._items.items()):
            if now - item["t"] > self.ttl:
                del self._items[k]
                continue
            if item["version"] != version:
                continue
            if k == key:
                best, best_sim, best_key = item, 1.0, k
                break
            if qvec is None:
                qvec = self.embedder.embed(query)
            sim = float(item["vec"] @ qvec)
            if sim > best_sim:
                best, best_sim, best_key = item, sim, k
        if best is not None and best_sim >= self.threshold:
            self._items.move_to_end(best_key)
            self.hits += 1
            return best["value"], best_sim
        self.misses += 1
        return None

    def set(self, query: str, version: str, value: Any) -> None:
        self._items[_norm(query)] = {"t": time.time(), "version": version, "value": value,
                                     "vec": np.asarray(self.embedder.embed(query))}
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()
