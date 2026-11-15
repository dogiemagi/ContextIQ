"""Central configuration. Everything is overridable through environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pick_provider() -> str:
    forced = os.getenv("LLM_PROVIDER", "").strip().lower()
    if forced:
        return forced
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GROQ_API_KEY"):
        return "groq"  # hosted open models, fast, has a free tier
    if _ollama_running():
        return "ollama"  # free local model, no API key needed
    return "offline"  # deterministic extractive generator: runs with zero API keys


def _ollama_running() -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.2):
            return True
    except OSError:
        return False


@dataclass(frozen=True)
class Settings:
    docs_dir: Path
    index_dir: Path
    trace_file: Path
    feedback_file: Path
    llm_provider: str
    anthropic_model: str
    openai_model: str
    embeddings: str  # "hashing" (no deps) or "st" (sentence-transformers)
    top_k: int
    min_coverage: float  # abstain when the best chunk covers less of the query than this
    cache_threshold: float
    cache_ttl: int
    injection_threshold: float
    price_in_per_mtok: float
    price_out_per_mtok: float
    api_key: str | None
    rate_limit_per_min: int
    db_path: Path = ROOT / "data" / "app.db"
    ollama_model: str = "llama3.2"
    groq_model: str = "openai/gpt-oss-20b"
    allow_registration: bool = True
    database_url: str | None = None  # postgresql://... (Neon/Supabase). If unset, SQLite at db_path is used.


def get_settings() -> Settings:
    data = Path(os.getenv("TRUSTRAG_DATA", ROOT / "data"))
    return Settings(
        docs_dir=Path(os.getenv("TRUSTRAG_DOCS", data / "docs")),
        index_dir=Path(os.getenv("TRUSTRAG_INDEX", data / "index")),
        trace_file=Path(os.getenv("TRUSTRAG_TRACES", data / "traces.jsonl")),
        feedback_file=Path(os.getenv("TRUSTRAG_FEEDBACK", data / "feedback.jsonl")),
        llm_provider=_pick_provider(),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        embeddings=os.getenv("EMBEDDINGS", "hashing").lower(),
        top_k=int(os.getenv("TOP_K", "4")),
        min_coverage=float(os.getenv("MIN_COVERAGE", "0.4")),
        cache_threshold=float(os.getenv("CACHE_THRESHOLD", "0.93")),
        cache_ttl=int(os.getenv("CACHE_TTL", "3600")),
        injection_threshold=float(os.getenv("INJECTION_THRESHOLD", "1.0")),
        # USD per million tokens. Set these to your provider's real prices; defaults are 0 so
        # the cost column never shows an invented number.
        price_in_per_mtok=float(os.getenv("PRICE_IN_PER_MTOK", "0")),
        price_out_per_mtok=float(os.getenv("PRICE_OUT_PER_MTOK", "0")),
        api_key=os.getenv("TRUSTRAG_API_KEY") or None,
        rate_limit_per_min=int(os.getenv("RATE_LIMIT_PER_MIN", "60")),
        db_path=Path(os.getenv("TRUSTRAG_DB", data / "app.db")),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        allow_registration=os.getenv("ALLOW_REGISTRATION", "1") != "0",
        database_url=os.getenv("DATABASE_URL") or None,
    )
