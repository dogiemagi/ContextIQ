import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trustrag.config import ROOT, get_settings  # noqa: E402
from trustrag.service import TrustRAG  # noqa: E402


@pytest.fixture(scope="session")
def rag(tmp_path_factory) -> TrustRAG:
    tmp = tmp_path_factory.mktemp("trustrag")
    s = dataclasses.replace(
        get_settings(),
        docs_dir=ROOT / "data" / "docs", index_dir=tmp / "index", trace_file=tmp / "traces.jsonl",
        feedback_file=tmp / "feedback.jsonl", llm_provider="offline", embeddings="hashing",
        api_key=None, rate_limit_per_min=10_000,
    )
    return TrustRAG(s)
