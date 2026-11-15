"""Per-user private workspaces: every user gets their own documents, index, cache and traces.

A user can never retrieve another user's documents because each workspace is a separate
TrustRAG instance rooted in its own directory (data/users/<user_id>/).

The database is the source of truth for documents. The directory is only a *cache*: on a fresh
server (e.g. a Render redeploy that wiped the disk) the first request for a user rebuilds their
files and search index from the database, so nothing the user uploaded is ever lost.
"""
from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path
from threading import Lock

from .config import ROOT, Settings, get_settings
from .service import TrustRAG

_DOC_SUFFIXES = {".md", ".txt"}


class WorkspaceManager:
    def __init__(self, base: Path | None = None, settings: Settings | None = None, db=None):
        self.base_settings = settings or get_settings()
        self.base = Path(base or self.base_settings.docs_dir.parent / "users")
        self.db = db
        self._cache: dict[str, TrustRAG] = {}
        self._lock = Lock()

    def path(self, user_id: str) -> Path:
        if not user_id.isalnum():  # ids are uuid hex; refuse anything path-like
            raise ValueError("bad user id")
        return self.base / user_id

    def get(self, user_id: str) -> TrustRAG:
        with self._lock:
            if user_id not in self._cache:
                root = self.path(user_id)
                s = dataclasses.replace(
                    self.base_settings, docs_dir=root / "docs", index_dir=root / "index",
                    trace_file=root / "traces.jsonl", feedback_file=root / "feedback.jsonl")
                rag = TrustRAG(s, auto_ingest=False)
                if self.db is not None:
                    self._hydrate(user_id, rag)
                self._cache[user_id] = rag
            return self._cache[user_id]

    def _hydrate(self, user_id: str, rag: TrustRAG) -> None:
        """Make the local files + index agree with the database."""
        docs = self.db.documents(user_id)
        folder = rag.s.docs_dir
        folder.mkdir(parents=True, exist_ok=True)
        on_disk = {p.name for p in folder.iterdir() if p.suffix.lower() in _DOC_SUFFIXES}

        if not docs and on_disk:  # files from before the database stored documents: adopt them
            for name in on_disk:
                self.db.save_document(user_id, name, (folder / name).read_text(encoding="utf-8", errors="ignore"))
            if not rag.store.chunks:
                rag.ingest_dir(folder)
            return
        if set(docs) == on_disk and (rag.store.chunks or not docs):
            return  # already in sync
        for name, body in docs.items():
            (folder / name).write_text(body, encoding="utf-8")
        for stale in on_disk - set(docs):
            (folder / stale).unlink(missing_ok=True)
        rag.ingest_dir(folder)

    def sample_docs_dir(self) -> Path:
        return ROOT / "data" / "docs"

    def delete(self, user_id: str) -> None:
        with self._lock:
            self._cache.pop(user_id, None)
        shutil.rmtree(self.path(user_id), ignore_errors=True)
