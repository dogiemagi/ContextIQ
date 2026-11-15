# TrustRAG - chat with your own documents

A complete web application: **sign up, upload PDFs, ask questions, get answers with the exact source cited.**
If the answer isn't in your files, it says so instead of guessing. Hidden attacks inside documents are detected and ignored.

## Run it (Windows)

Double-click **`run.bat`**, or:

```bash
pip install -r requirements.txt
python -m trustrag.webapp          # opens http://localhost:8000
```

1. Click **Create account** (stored locally in `data/app.db`).
2. Click **Try it with sample documents** - or drag in your own PDF / TXT / MD files.
3. Ask a question. Click a numbered citation chip to see the exact passage and page.

### Which AI writes the answers?
Auto-detected, in this order - the pill at the top of the app shows which one is active:

| You have | Result |
|---|---|
| `ANTHROPIC_API_KEY` set | Claude writes fluent answers |
| `OPENAI_API_KEY` set | OpenAI writes fluent answers |
| [Ollama](https://ollama.com) running | Free local model (auto-picks an installed chat model, e.g. `qwen2.5:7b`) |
| nothing | "Offline mode": answers are quoted straight from your documents |

If the model ever fails or times out, the app falls back to the quoted answer instead of showing an error.

## What's in the app

| Feature | Details |
|---|---|
| Accounts | Register / sign in / sign out / delete account. PBKDF2-SHA256 salted passwords, hashed session tokens, brute-force lockout |
| Private workspaces | Every user has separate documents, index, cache and traces. Verified by tests: user B can't see or query user A's data |
| Uploads | PDF (page-aware), TXT, MD, up to 15 MB, 25 documents. Scanned/encrypted/corrupt files give a clear message |
| Chat | Saved conversations, follow-up questions that remember context, copy, thumbs up/down |
| Trust | Numbered citations with page + section, confidence meter, "supported by sources" check, "not found" instead of guessing |
| Security shield | Blocks prompt-injection in questions; quarantines poisoned sections in uploaded files; hides personal data (emails, cards, phone, SSN) |
| Insights | Questions asked, response time, cache hits, attacks blocked, per-request timing bars |
| Calculator | Arithmetic questions use a safe calculator tool (no `eval`) |

## Under the hood (the AI engineering)
Hybrid retrieval (dense + BM25 from scratch -> Reciprocal Rank Fusion -> rerank -> MMR), contextual chunk headers, an agent
planner with tools, grounded generation with citations, groundedness scoring, semantic cache, span-level tracing with
token/cost accounting, and an evaluation harness with a CI quality gate.

```
web/        index.html  style.css  app.js            the product UI (no build step)
trustrag/   webapp db workspaces extract             accounts, storage, uploads
            agent retriever bm25 chunking llm        the RAG engine
            guardrails tools cache observability     safety, tools, speed, tracing
            evaluation                               golden-set eval + ablation + quality gate
data/docs/  sample knowledge base (one file is deliberately poisoned)
tests/      47 tests
```

## Deploy: Render (app) + Neon (database)
Locally the app uses a SQLite file. In production it uses **Postgres** whenever `DATABASE_URL` is set. Accounts, chats and
uploaded documents all live in the database; the search index is rebuilt from it on startup, so Render restarts and redeploys
lose nothing.

1. **Neon**: create a project at neon.tech and copy the connection string (`postgresql://...?sslmode=require`).
2. Push this repo to GitHub.
3. **Render**: **New** -> **Blueprint** -> pick the repo (it reads `render.yaml`).
4. When asked for env vars, paste `DATABASE_URL` (the Neon string). Optionally add `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
   and set `LLM_PROVIDER` for fluent answers.
5. Open the `.onrender.com` URL (`/api/status` should say `"database":"postgres"`), create your account, then set
   `ALLOW_REGISTRATION=0` to lock sign-ups.

Free-tier notes: Render sleeps idle instances (first request ~30-60 s) and Neon suspends idle compute (wakes in ~1 s).
Neither deletes data. Tables are created automatically on first start.

Verify the Postgres path yourself against a throwaway database:
```bash
set TEST_DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
python -m pytest tests/test_postgres.py -v
```

## Quality checks

```bash
pip install -r requirements-dev.txt
python -m pytest -q                 # 47 tests: auth, privacy, PDFs, attacks, retrieval, API
python -m trustrag.evaluation       # 23-question eval + retrieval ablation; exit code 1 if quality regresses
```
Offline-mode results on the sample set: hit@4 1.00, MRR 0.97, fact recall 1.00, groundedness 1.00, 3/3 unanswerable
refused, 2/2 attacks blocked, 0 poisoned-answer leaks. (With only 26 chunks all retrieval modes tie; the ablation
becomes informative on a larger corpus.)

## Configuration (`.env.example`)
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_MODEL`, `EMBEDDINGS=st` (real semantic embeddings via sentence-transformers),
`ALLOW_REGISTRATION=0` (lock sign-ups), `PORT`, `HOST`. Docker: `docker compose up --build`.

## Known limits (honest list)
- Scanned PDFs (images only) aren't supported - no OCR.
- A local 7B model on CPU takes ~10-60 s per answer (first one loads the model). The app pre-warms it and shows a live timer.
- Documents are stored as extracted text inside Postgres (fine for personal-sized libraries; use object storage for very large files).
- One web worker is assumed (in-memory login-attempt counters and caches are per process).
- Over plain HTTP: put it behind HTTPS (e.g. Caddy/nginx) before exposing it beyond localhost.

## Interview talking points
- **Why hybrid retrieval?** Dense catches paraphrase, BM25 catches exact tokens like `99.99%`; RRF fuses ranks without calibrating score scales.
- **Indirect prompt injection?** Attack text hidden *in documents*. Uploads are scanned and bad sections quarantined before they can reach the model.
- **Multi-tenancy?** One engine instance per user rooted in its own directory; ownership checked on every conversation/document route.
- **Graceful degradation?** Model failure -> extractive fallback; weak evidence -> abstain; slow local model -> pre-warm + progress feedback.
- **How do you know it works?** Golden-set evaluation + 47 tests, enforced in CI.
