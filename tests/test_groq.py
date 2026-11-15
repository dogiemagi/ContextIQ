"""Groq provider tested against a local fake of Groq's OpenAI-compatible endpoint (no network, no key)."""
import importlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from trustrag.config import get_settings
from trustrag.llm import GroqLLM, OfflineLLM, get_llm
from trustrag.service import TrustRAG
import dataclasses


class FakeGroq:
    """Tiny HTTP server that records requests and replays scripted responses."""

    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                       "ua": self.headers.get("User-Agent"), "body": body})
                code, payload, headers = outer.responses.pop(0) if outer.responses else (500, {"error": "no script"}, {})
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}/openai/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


def ok(text):
    return 200, {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 11, "completion_tokens": 5}}, {}


@pytest.fixture()
def fake():
    made = []

    def make(responses):
        f = FakeGroq(responses)
        made.append(f)
        return f

    yield make
    for f in made:
        f.close()


def test_request_shape_and_parsing_for_gpt_oss(fake):
    f = fake([ok("You have 30 days. [S1]")])
    r = GroqLLM("openai/gpt-oss-20b", api_key="k-test", base_url=f.url).complete("sys", "hello", max_tokens=600)
    assert r.text == "You have 30 days. [S1]" and (r.input_tokens, r.output_tokens) == (11, 5)
    req = f.requests[0]
    assert req["path"].endswith("/chat/completions") and req["auth"] == "Bearer k-test" and req["ua"].startswith("TrustRAG")
    b = req["body"]
    assert b["model"] == "openai/gpt-oss-20b" and b["reasoning_effort"] == "low" and b["max_completion_tokens"] >= 2000
    assert [m["role"] for m in b["messages"]] == ["system", "user"] and "max_tokens" not in b


def test_non_reasoning_models_use_plain_max_tokens(fake):
    f = fake([ok("hi")])
    GroqLLM("llama-3.3-70b-versatile", api_key="k", base_url=f.url).complete("s", "p", max_tokens=300)
    b = f.requests[0]["body"]
    assert b["max_tokens"] == 300 and "reasoning_effort" not in b and "max_completion_tokens" not in b


def test_retries_once_on_rate_limit(fake):
    f = fake([(429, {"error": "slow down"}, {"retry-after": "0"}), ok("second try worked")])
    assert GroqLLM("m", api_key="k", base_url=f.url).complete("s", "p").text == "second try worked"
    assert len(f.requests) == 2


@pytest.mark.parametrize("script,needle", [([(401, {"error": "bad key"}, {})], "HTTP 401"),
                                           ([(200, {"choices": [{"message": {"content": ""}}]}, {})], "empty")])
def test_errors_raise_clearly(fake, script, needle):
    f = fake(script)
    with pytest.raises(RuntimeError, match=needle):
        GroqLLM("m", api_key="k", base_url=f.url).complete("s", "p")


def test_missing_key_raises():
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        GroqLLM("m", api_key="", base_url="http://127.0.0.1:1").complete("s", "p")


def test_provider_autodetect_prefers_groq_when_key_present(monkeypatch):
    for k in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    s = get_settings()
    assert s.llm_provider == "groq" and s.groq_model == "openai/gpt-oss-20b"
    assert isinstance(get_llm(s.llm_provider, s.anthropic_model, s.openai_model, s.ollama_model, s.groq_model), GroqLLM)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert get_settings().llm_provider == "anthropic"  # explicit paid keys still win


def test_chat_survives_a_broken_model_by_quoting_the_documents(rag, fake):
    f = fake([(500, {"error": "boom"}, {})])
    s = dataclasses.replace(rag.s, llm_provider="groq")
    svc = TrustRAG(s, auto_ingest=False)
    svc.llm = svc.agent.llm = GroqLLM("openai/gpt-oss-20b", api_key="k", base_url=f.url)
    r = svc.ask("What is the price of the Pro plan?", use_cache=False)
    assert "$99" in r.answer and "model_unavailable_used_extractive" in r.flags and not r.abstained


def test_gunicorn_entrypoint_is_a_real_asgi_app_with_head_support(tmp_path, monkeypatch):
    """`gunicorn app:app` (the old ContextIQ start command) must load an ASGI app, answering GET *and* HEAD."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TRUSTRAG_DATA", str(tmp_path))
    monkeypatch.setenv("TRUSTRAG_DB", str(tmp_path / "app.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    sys.modules.pop("app", None)
    entry = importlib.import_module("app").app
    c = TestClient(entry)
    assert c.get("/api/status").json()["app"] == get_settings().app_name and c.get("/").status_code == 200
    # Hosting health checks (Render) probe with HEAD: it must be 200, not 405 and not a hang.
    assert c.head("/").status_code == 200 and c.head("/api/status").status_code == 200
    sys.modules.pop("app", None)


def test_gunicorn_config_selects_the_asgi_worker():
    import runpy
    from pathlib import Path

    conf = runpy.run_path(str(Path(__file__).resolve().parent.parent / "gunicorn.conf.py"))
    assert conf["worker_class"] == "uvicorn_worker.UvicornWorker" and conf["workers"] == 1 and conf["timeout"] >= 120
    reqs = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
    assert "uvicorn-worker" in reqs and "gunicorn" in reqs
