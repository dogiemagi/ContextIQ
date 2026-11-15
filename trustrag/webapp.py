"""The complete web application: accounts, private workspaces, uploads, chat, insights.

Run:  python -m trustrag.webapp        ->  http://localhost:8000
"""
from __future__ import annotations

import base64
import binascii
import shutil
import time
from collections import defaultdict, deque
from html import escape as html_escape
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import ROOT, Settings, get_settings
from .db import AuthError, Database
from .extract import ExtractError, extract_text
from .service import safe_filename
from .workspaces import WorkspaceManager

WEB_DIR = ROOT / "web"
NO_DOCS_MSG = "You haven't added any documents yet. Upload a PDF or text file (or load the sample documents) and ask again."


class Credentials(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)
    name: str = Field(default="", max_length=60)


class UploadBody(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_b64: str = Field(min_length=4)


class AskBody(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class RateBody(BaseModel):
    message_id: str
    trace_id: str = ""
    rating: int = Field(ge=-1, le=1)


def display_name(source: str) -> str:
    return source[:-3] if source.lower().endswith(".pdf.md") else source


def create_webapp(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    db = Database(s.database_url or s.db_path)
    ws = WorkspaceManager(settings=s, db=db)
    app = FastAPI(title=s.app_name, version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
    ask_log: dict[str, deque] = defaultdict(deque)

    from .llm import get_llm as _get_llm

    shared_llm = _get_llm(s.llm_provider, s.anthropic_model, s.openai_model, s.ollama_model, s.groq_model)
    if hasattr(shared_llm, "warmup"):
        shared_llm.warmup()  # local model: load into memory now, not on the first question

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if not request.url.path.startswith("/api/docs"):
            resp.headers["Content-Security-Policy"] = (
                "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:")
        return resp

    def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
        user = db.user_for_token(token)
        if not user:
            raise HTTPException(401, "Please sign in.")
        user["_token"] = token
        return user

    # ------------------------------------------------------------------ public
    @app.api_route("/api/status", methods=["GET", "HEAD"])  # HEAD too: hosting health checks often use it
    def status() -> dict:
        return {"app": s.app_name, "version": __version__, "llm": shared_llm.name, "model": shared_llm.model,
                "fluent": shared_llm.is_real, "registration": s.allow_registration, "database": db.backend}

    @app.post("/api/register")
    def register(body: Credentials) -> dict:
        if not s.allow_registration:
            raise HTTPException(403, "Registration is disabled.")
        try:
            user = db.register(body.email, body.password, body.name)
        except AuthError as e:
            raise HTTPException(400, str(e)) from None
        return {"token": db.create_session(user["id"]), "user": user}

    @app.post("/api/login")
    def login(body: Credentials) -> dict:
        try:
            user = db.login(body.email, body.password)
        except AuthError as e:
            raise HTTPException(401, str(e)) from None
        return {"token": db.create_session(user["id"]), "user": user}

    # ------------------------------------------------------------------ account
    @app.get("/api/me")
    def me(user: dict = Depends(current_user)) -> dict:
        return {"id": user["id"], "email": user["email"], "name": user["name"]}

    @app.post("/api/logout")
    def logout(user: dict = Depends(current_user)) -> dict:
        db.end_session(user["_token"])
        return {"ok": True}

    @app.delete("/api/me")
    def delete_account(user: dict = Depends(current_user)) -> dict:
        db.delete_user(user["id"])
        ws.delete(user["id"])
        return {"ok": True}

    # ------------------------------------------------------------------ documents
    def doc_list(uid: str) -> list[dict]:
        rag = ws.get(uid)
        out = []
        for d in rag.documents():
            f = rag.s.docs_dir / d["source"]
            out.append({"name": d["source"], "display": display_name(d["source"]), "title": d["title"],
                        "chunks": d["chunks"], "quarantined": d["quarantined"],
                        "size": f.stat().st_size if f.exists() else 0})
        return sorted(out, key=lambda x: x["display"].lower())

    @app.get("/api/documents")
    def documents(user: dict = Depends(current_user)) -> list[dict]:
        return doc_list(user["id"])

    @app.post("/api/documents")
    def upload(body: UploadBody, user: dict = Depends(current_user)) -> dict:
        try:
            data = base64.b64decode(body.content_b64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, "Upload was corrupted. Please try again.") from None
        try:
            text, pages = extract_text(body.filename, data)
        except ExtractError as e:
            raise HTTPException(400, str(e)) from None
        rag = ws.get(user["id"])
        if len(rag.documents()) >= 25:
            raise HTTPException(400, "Document limit reached (25). Delete one first.")
        saved = safe_filename(body.filename if body.filename.lower().endswith((".md", ".txt")) else body.filename + ".md")
        db.save_document(user["id"], saved, text)  # database first: it is the source of truth
        report = rag.add_document(saved, text)
        bad = [q for q in report.quarantined if q["source"] == saved]
        return {"name": display_name(saved), "pages": pages, "documents": report.documents,
                "chunks": report.chunks, "quarantined": len(bad),
                "warning": ("Part of this file looked like hidden instructions aimed at the AI "
                            "(prompt injection), so it was excluded from answers.") if bad else ""}

    @app.post("/api/documents/sample")
    def load_sample(user: dict = Depends(current_user)) -> dict:
        rag = ws.get(user["id"])
        rag.s.docs_dir.mkdir(parents=True, exist_ok=True)
        for f in ws.sample_docs_dir().glob("*.md"):
            shutil.copy(f, rag.s.docs_dir / f.name)
            db.save_document(user["id"], f.name, f.read_text(encoding="utf-8"))
        rep = rag.ingest_dir(rag.s.docs_dir)
        return {"documents": rep.documents, "chunks": rep.chunks, "quarantined": len(rep.quarantined)}

    @app.delete("/api/documents/{name}")
    def delete_doc(name: str, user: dict = Depends(current_user)) -> dict:
        if not ws.get(user["id"]).remove_document(name):
            raise HTTPException(404, "Document not found.")
        db.delete_document(user["id"], Path(name).name)
        return {"ok": True}

    # ------------------------------------------------------------------ conversations
    @app.get("/api/conversations")
    def conversations(user: dict = Depends(current_user)) -> list[dict]:
        return db.conversations(user["id"])

    @app.post("/api/conversations")
    def new_conversation(user: dict = Depends(current_user)) -> dict:
        return db.new_conversation(user["id"])

    def owned(cid: str, user: dict) -> None:
        if not db.owns(user["id"], cid):
            raise HTTPException(404, "Conversation not found.")

    @app.get("/api/conversations/{cid}")
    def get_conversation(cid: str, user: dict = Depends(current_user)) -> list[dict]:
        owned(cid, user)
        return db.messages(cid)

    @app.delete("/api/conversations/{cid}")
    def delete_conversation(cid: str, user: dict = Depends(current_user)) -> dict:
        owned(cid, user)
        db.delete_conversation(cid)
        return {"ok": True}

    @app.post("/api/conversations/{cid}/ask")
    def ask(cid: str, body: AskBody, user: dict = Depends(current_user)) -> dict:
        owned(cid, user)
        now, window = time.time(), ask_log[user["id"]]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= max(10, s.rate_limit_per_min):
            raise HTTPException(429, "You're asking too fast - please wait a moment.")
        window.append(now)

        rag = ws.get(user["id"])
        past = db.messages(cid)
        history = [{"role": m["role"], "content": m["content"], "blocked": m["meta"].get("blocked")} for m in past][-8:]
        user_msg = db.add_message(cid, "user", body.question)
        if not past:
            db.rename_conversation(cid, body.question.strip()[:60])

        if not rag.store.chunks:
            meta: dict[str, Any] = {"abstained": True, "flags": ["no_documents"], "citations": []}
            answer = NO_DOCS_MSG
        else:
            res = rag.ask(body.question, history=history)
            answer = res.answer
            meta = {k: v for k, v in res.to_dict().items() if k not in {"answer", "input_tokens", "output_tokens"}}
            for c in meta.get("citations", []):
                c["display"] = display_name(c["source"])
        msg_id = db.add_message(cid, "assistant", answer, meta)
        return {"user_message_id": user_msg, "message": {"id": msg_id, "role": "assistant", "content": answer, "meta": meta}}

    @app.post("/api/feedback")
    def feedback(body: RateBody, user: dict = Depends(current_user)) -> dict:
        if not db.rate_message(user["id"], body.message_id, body.rating):
            raise HTTPException(404, "Message not found.")
        if body.trace_id and ws.get(user["id"]).traces.get(body.trace_id):
            ws.get(user["id"]).feedback(body.trace_id, body.rating or 0)
        return {"ok": True}

    # ------------------------------------------------------------------ insights
    @app.get("/api/insights")
    def insights(user: dict = Depends(current_user)) -> dict:
        rag = ws.get(user["id"])
        docs = doc_list(user["id"])
        return {"usage": db.stats(user["id"]), "documents": len(docs), "chunks": sum(d["chunks"] for d in docs),
                "quarantined": sum(d["quarantined"] for d in docs), "performance": rag.traces.summary(),
                "recent": [{"id": t["id"], "question": t["question"][:80], "latency_ms": t["latency_ms"],
                            "spans": [{"name": sp["name"], "ms": sp["duration_ms"]} for sp in t["spans"]],
                            "outcome": {k: t["outcome"].get(k) for k in ("blocked", "abstained", "cached")}}
                           for t in rag.traces.recent(8)]}

    # ------------------------------------------------------------------ frontend
    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def index() -> HTMLResponse:
        # The page title and logo text come from APP_NAME (HTML-escaped), so renaming needs no code change.
        page = (WEB_DIR / "index.html").read_text(encoding="utf-8").replace("__APP_NAME__", html_escape(s.app_name))
        return HTMLResponse(page, headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


def __getattr__(name: str):  # lazy `app` so importing the module never touches disk
    if name == "app":
        globals()["app"] = create_webapp()
        return globals()["app"]
    raise AttributeError(name)


def resolve_host() -> str:
    """HOST if set; otherwise bind publicly when a hosting platform provides PORT (Render, Heroku...),
    and stay on localhost for normal local runs."""
    import os

    return os.getenv("HOST") or ("0.0.0.0" if os.getenv("PORT") else "127.0.0.1")


def main() -> None:
    import os
    import threading
    import webbrowser

    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    if os.getenv("NO_BROWSER") != "1" and not os.getenv("PORT"):  # never try to open a browser on a server
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run("trustrag.webapp:app", host=resolve_host(), port=port)


if __name__ == "__main__":
    main()
