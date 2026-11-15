"""Composition root: wires embedder, index, retriever, cache, tracer, LLM and agent together."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .agent import Agent, AgentResult
from .cache import SemanticCache
from .chunking import Chunk, chunk_markdown
from .config import Settings, get_settings
from .embeddings import get_embedder
from .guardrails import detect_prompt_injection
from .llm import get_llm
from .observability import TraceStore
from .retriever import HybridRetriever, VectorStore
from .text import content_terms


def safe_filename(filename: str) -> str:
    """The on-disk / in-database name for an uploaded file (no paths, no odd characters, .md/.txt suffix)."""
    safe = re.sub(r"[^\w.\-]", "_", Path(filename).name) or "upload.md"
    return safe if safe.lower().endswith((".md", ".txt")) else safe + ".md"


@dataclass
class IngestReport:
    documents: int
    chunks: int
    quarantined: list[dict] = field(default_factory=list)


class TrustRAG:
    def __init__(self, settings: Settings | None = None, auto_ingest: bool = True):
        self.s = settings or get_settings()
        self.embedder = get_embedder(self.s.embeddings)
        self.store = VectorStore(self.embedder)
        self.traces = TraceStore(self.s.trace_file)
        self.llm = get_llm(self.s.llm_provider, self.s.anthropic_model, self.s.openai_model, self.s.ollama_model,
                           self.s.groq_model)
        self.cache = SemanticCache(self.embedder, self.s.cache_threshold, self.s.cache_ttl)
        self.retriever: HybridRetriever
        self.agent: Agent
        if self.store.load(self.s.index_dir):
            self._wire()
        elif auto_ingest and self.s.docs_dir.exists():
            self.ingest_dir(self.s.docs_dir)
        else:
            self._wire()

    def _wire(self) -> None:
        self.retriever = HybridRetriever(self.store)
        self.agent = Agent(self.retriever, self.llm, self.cache, self.traces, self.s)

    # ------------------------------------------------------------------ ingestion
    def ingest_dir(self, directory: Path) -> IngestReport:
        files = sorted(p for p in Path(directory).glob("**/*") if p.suffix.lower() in {".md", ".txt"})
        chunks: list[Chunk] = []
        for f in files:
            chunks += chunk_markdown(f.name, f.read_text(encoding="utf-8", errors="ignore"))
        return self._index(chunks, len(files))

    def add_document(self, filename: str, content: str) -> IngestReport:
        safe = safe_filename(filename)
        self.s.docs_dir.mkdir(parents=True, exist_ok=True)
        (self.s.docs_dir / safe).write_text(content, encoding="utf-8")
        return self.ingest_dir(self.s.docs_dir)

    def _index(self, chunks: list[Chunk], n_docs: int) -> IngestReport:
        for c in chunks:  # ingestion-time scan: quarantine poisoned chunks (indirect prompt injection)
            r = detect_prompt_injection(c.text, self.s.injection_threshold)
            if r.blocked:
                c.flagged, c.flags = True, r.matches
        self.store.build(chunks)
        self.store.save(self.s.index_dir)
        self.cache.clear()
        self._wire()
        q = [{"chunk_id": c.id, "source": c.source, "flags": c.flags, "preview": c.text[:120]} for c in chunks if c.flagged]
        return IngestReport(documents=n_docs, chunks=len(chunks), quarantined=q)

    # ------------------------------------------------------------------ querying
    def ask(self, question: str, use_cache: bool = True, retrieval_mode: str = "hybrid_rerank",
            history: list[dict] | None = None) -> AgentResult:
        return self.agent.ask(self.condense(question, history or []), use_cache=use_cache,
                              retrieval_mode=retrieval_mode)

    _FOLLOWUP = re.compile(r"\b(it|its|that|this|those|these|they|them|their|there|also|same|too|else|more)\b", re.I)

    def condense(self, question: str, history: list[dict]) -> str:
        """Conversation memory: turn a follow-up ("and for Enterprise?") into a standalone question."""
        prev = [m["content"] for m in history if m["role"] == "user" and not m.get("blocked")]
        if not prev:
            return question
        last = prev[-1]
        if self.llm.is_real and self.llm.aux_calls:
            try:
                r = self.llm.complete(
                    "Rewrite the user's last message as ONE standalone question using the earlier question for context. "
                    "If it is already standalone, return it unchanged. Output only the question.",
                    f"Earlier question: {last}\nLast message: {question}", max_tokens=80)
                out = r.text.strip().strip('"')
                if 3 < len(out) < 400:
                    return out
            except Exception:
                pass
        if len(content_terms(question)) <= 3 or self._FOLLOWUP.search(question):
            return f"{last} {question}"
        return question

    def remove_document(self, filename: str) -> bool:
        target = self.s.docs_dir / Path(filename).name
        if not target.exists():
            return False
        target.unlink()
        self.ingest_dir(self.s.docs_dir)
        return True

    def feedback(self, trace_id: str, rating: int, comment: str = "") -> None:
        self.traces.add_feedback(trace_id, rating)
        self.s.feedback_file.parent.mkdir(parents=True, exist_ok=True)
        with self.s.feedback_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"trace_id": trace_id, "rating": rating, "comment": comment}) + "\n")

    def documents(self) -> list[dict]:
        docs: dict[str, dict] = {}
        for c in self.store.chunks:
            d = docs.setdefault(c.source, {"source": c.source, "title": c.title, "chunks": 0, "quarantined": 0})
            d["chunks"] += 1
            d["quarantined"] += int(c.flagged)
        return list(docs.values())
