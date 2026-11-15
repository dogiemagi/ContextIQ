"""CLI: `python -m trustrag.ingest [docs_dir]` - (re)build the search index."""
from __future__ import annotations

import sys
from pathlib import Path

from .config import get_settings
from .service import TrustRAG


def main() -> int:
    s = get_settings()
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else s.docs_dir
    rag = TrustRAG(s, auto_ingest=False)
    report = rag.ingest_dir(src)
    print(f"Indexed {report.documents} documents -> {report.chunks} chunks (embeddings={rag.embedder.name})")
    for q in report.quarantined:
        print(f"  QUARANTINED {q['chunk_id']} ({q['source']}): {q['flags']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
