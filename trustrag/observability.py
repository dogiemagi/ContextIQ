"""Lightweight tracing + metrics (the same ideas as LangSmith / Langfuse / OpenTelemetry, ~100 lines).

Every request produces a Trace made of timed Spans (guardrails, cache, plan, retrieve, generate...)
plus token usage and cost. Traces are appended to a JSONL file and summarised for the dashboard.
"""
from __future__ import annotations

import json
import time
import uuid
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any, Iterator


class Trace:
    def __init__(self, question: str):
        self.id = uuid.uuid4().hex[:12]
        self.question = question
        self.t0 = time.perf_counter()
        self.started_at = time.time()
        self.spans: list[dict[str, Any]] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.outcome: dict[str, Any] = {}

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
        start = time.perf_counter()
        data: dict[str, Any] = dict(attrs)
        try:
            yield data
        except Exception as exc:  # record the failure on the span, then re-raise
            data["error"] = repr(exc)
            raise
        finally:
            self.spans.append({"name": name,
                               "start_ms": round((start - self.t0) * 1000, 2),
                               "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                               "attrs": data})

    def add_usage(self, input_tokens: int, output_tokens: int, price_in: float, price_out: float) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += (input_tokens * price_in + output_tokens * price_out) / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "question": self.question, "started_at": self.started_at,
                "latency_ms": round((time.perf_counter() - self.t0) * 1000, 2),
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cost_usd": round(self.cost_usd, 6), "spans": self.spans, "outcome": self.outcome}


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return round(s[min(len(s) - 1, int(round(p * (len(s) - 1))))], 2)


class TraceStore:
    def __init__(self, path: Path | None = None, keep: int = 1000):
        self.path = path
        self._recent: deque[dict] = deque(maxlen=keep)
        self._lock = Lock()
        self.feedback: dict[str, int] = {}

    def record(self, trace: Trace) -> dict[str, Any]:
        d = trace.to_dict()
        with self._lock:
            self._recent.append(d)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(d) + "\n")
        return d

    def recent(self, n: int = 20) -> list[dict]:
        with self._lock:
            return list(self._recent)[-n:][::-1]

    def get(self, trace_id: str) -> dict | None:
        with self._lock:
            return next((t for t in self._recent if t["id"] == trace_id), None)

    def add_feedback(self, trace_id: str, rating: int) -> None:
        self.feedback[trace_id] = rating

    def summary(self) -> dict[str, Any]:
        with self._lock:
            traces = list(self._recent)
        n = len(traces)
        if not n:
            return {"requests": 0}
        lat = [t["latency_ms"] for t in traces]
        out = [t["outcome"] for t in traces]
        fb = list(self.feedback.values())
        return {
            "requests": n,
            "latency_p50_ms": _pct(lat, 0.5),
            "latency_p95_ms": _pct(lat, 0.95),
            "cache_hit_rate": round(sum(o.get("cached", False) for o in out) / n, 3),
            "block_rate": round(sum(o.get("blocked", False) for o in out) / n, 3),
            "abstain_rate": round(sum(o.get("abstained", False) for o in out) / n, 3),
            "avg_groundedness": round(sum(o.get("groundedness", 0) or 0 for o in out) / n, 3),
            "total_cost_usd": round(sum(t["cost_usd"] for t in traces), 6),
            "total_tokens": sum(t["input_tokens"] + t["output_tokens"] for t in traces),
            "feedback_score": round(sum(fb) / len(fb), 3) if fb else None,
        }
