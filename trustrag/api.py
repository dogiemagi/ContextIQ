"""FastAPI service. Run: `uvicorn trustrag.api:app --reload` (docs at /docs)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import __version__
from .retriever import MODES
from .service import TrustRAG


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    use_cache: bool = True
    retrieval_mode: Literal["dense", "bm25", "hybrid", "hybrid_rerank"] = "hybrid_rerank"


class IngestRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=10, max_length=500_000)


class FeedbackRequest(BaseModel):
    trace_id: str
    rating: Literal[-1, 1]
    comment: str = Field(default="", max_length=1000)


def create_app(service: TrustRAG | None = None) -> FastAPI:
    app = FastAPI(title="TrustRAG", version=__version__,
                  description="Evaluated, guarded and observable agentic RAG.")
    state: dict = {"rag": service}
    hits: dict[str, deque] = defaultdict(deque)

    def rag() -> TrustRAG:
        if state["rag"] is None:  # lazy: importing the module never builds an index
            state["rag"] = TrustRAG()
        return state["rag"]

    def guard(request: Request, x_api_key: str | None = Header(default=None)) -> None:
        s = rag().s
        if s.api_key and x_api_key != s.api_key:
            raise HTTPException(401, "invalid or missing X-API-Key")
        now, window = time.time(), hits[request.client.host if request.client else "?"]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= s.rate_limit_per_min:
            raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "60"})
        window.append(now)

    @app.get("/health")
    def health() -> dict:
        r = rag()
        return {"status": "ok", "version": __version__, "llm": r.llm.name, "embeddings": r.embedder.name,
                "chunks": len(r.store.chunks), "quarantined": len(r.retriever.quarantined), "index_version": r.retriever.version}

    @app.post("/ask", dependencies=[Depends(guard)])
    def ask(body: AskRequest) -> dict:
        return rag().ask(body.question, body.use_cache, body.retrieval_mode).to_dict()

    @app.post("/ingest", dependencies=[Depends(guard)])
    def ingest(body: IngestRequest) -> dict:
        rep = rag().add_document(body.filename, body.content)
        return {"documents": rep.documents, "chunks": rep.chunks, "quarantined": rep.quarantined}

    @app.get("/documents", dependencies=[Depends(guard)])
    def documents() -> list[dict]:
        return rag().documents()

    @app.post("/feedback", dependencies=[Depends(guard)])
    def feedback(body: FeedbackRequest) -> dict:
        if rag().traces.get(body.trace_id) is None:
            raise HTTPException(404, "unknown trace_id")
        rag().feedback(body.trace_id, body.rating, body.comment)
        return {"ok": True}

    @app.get("/metrics", dependencies=[Depends(guard)])
    def metrics() -> dict:
        r = rag()
        return {**r.traces.summary(), "cache": {"hits": r.cache.hits, "misses": r.cache.misses}}

    @app.get("/traces", dependencies=[Depends(guard)])
    def traces(limit: int = 20) -> list[dict]:
        return rag().traces.recent(min(limit, 200))

    @app.get("/traces/{trace_id}", dependencies=[Depends(guard)])
    def trace(trace_id: str) -> dict:
        t = rag().traces.get(trace_id)
        if t is None:
            raise HTTPException(404, "trace not found")
        return t

    @app.get("/modes")
    def modes() -> list[str]:
        return list(MODES)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("trustrag.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
