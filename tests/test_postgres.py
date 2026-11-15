"""Runs the same behaviours against a REAL Postgres (Neon, Supabase, local...).

Skipped unless you provide a throwaway database:
    set TEST_DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
    python -m pytest tests/test_postgres.py -v
Tests create uniquely-named users and delete them afterwards (tables are created if missing).
"""
import dataclasses
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from test_webapp import b64
from trustrag.config import get_settings
from trustrag.db import Database
from trustrag.webapp import create_webapp

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set TEST_DATABASE_URL to a throwaway Postgres to run")


@pytest.fixture()
def db():
    d = Database(URL)
    created: list[str] = []
    d.track = created.append
    yield d
    for uid in created:
        d.delete_user(uid)
    d.close()


def email():
    return f"t-{uuid.uuid4().hex[:10]}@example.com"


def test_backend_is_postgres_and_schema_is_idempotent(db):
    assert db.backend == "postgres"
    Database(URL).close()  # second init must not fail


def test_users_sessions_and_duplicates(db):
    from trustrag.db import AuthError

    e = email()
    u = db.register(e, "long-enough-pw", "Pat")
    db.track(u["id"])
    with pytest.raises(AuthError):
        db.register(e.upper(), "long-enough-pw")
    assert db.login(e, "long-enough-pw")["id"] == u["id"]
    token = db.create_session(u["id"])
    assert db.user_for_token(token)["email"] == e
    db.end_session(token)
    assert db.user_for_token(token) is None


def test_conversations_messages_documents_and_cascade(db):
    u = db.register(email(), "long-enough-pw")
    c = db.new_conversation(u["id"])
    m1 = db.add_message(c["id"], "user", "hello")
    m2 = db.add_message(c["id"], "assistant", "hi there", {"citations": [{"id": "S1"}]})
    assert [m["role"] for m in db.messages(c["id"])] == ["user", "assistant"]
    assert db.rate_message(u["id"], m2, 1) and db.messages(c["id"])[1]["meta"]["rating"] == 1
    assert db.stats(u["id"]) == {"conversations": 1, "questions": 1} and m1
    db.save_document(u["id"], "a.md", "one")
    db.save_document(u["id"], "a.md", "two")  # replace, not duplicate
    assert db.documents(u["id"]) == {"a.md": "two"}
    db.delete_user(u["id"])  # ON DELETE CASCADE must clean everything
    assert db.documents(u["id"]) == {} and db.conversations(u["id"]) == []


def test_full_app_flow_and_disk_wipe_on_postgres(tmp_path):
    def settings(root):
        return dataclasses.replace(get_settings(), database_url=URL, docs_dir=root / "docs", index_dir=root / "index",
                                   trace_file=root / "t.jsonl", feedback_file=root / "f.jsonl", llm_provider="offline",
                                   embeddings="hashing", rate_limit_per_min=10_000)

    first = TestClient(create_webapp(settings(tmp_path / "s1")))
    assert first.get("/api/status").json()["database"] == "postgres"
    r = first.post("/api/register", json={"email": email(), "password": "long-enough-pw", "name": "Pat"})
    h = {"Authorization": "Bearer " + r.json()["token"]}
    try:
        first.post("/api/documents", headers=h, json={"filename": "faq.txt", "content_b64": b64(
            "Support is open from nine to five on weekdays. Refunds take ten business days.")})
        second = TestClient(create_webapp(settings(tmp_path / "s2")))  # wiped disk, same Postgres
        assert [d["display"] for d in second.get("/api/documents", headers=h).json()] == ["faq.txt"]
        cid = second.post("/api/conversations", headers=h).json()["id"]
        ans = second.post(f"/api/conversations/{cid}/ask", headers=h, json={"question": "How long do refunds take?"}).json()
        assert "ten business days" in ans["message"]["content"]
    finally:
        first.delete("/api/me", headers=h)
