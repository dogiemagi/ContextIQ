"""Entry point for hosts configured with `gunicorn app:app` (e.g. an existing Render service).

TrustRAG is an ASGI (FastAPI) app, so gunicorn must use an ASGI worker. The accompanying
`gunicorn.conf.py` selects it automatically - no change to the host's start command is needed.
The simplest start command, and the one render.yaml uses, is:   python -m trustrag.webapp
"""
from trustrag.webapp import create_webapp

app = create_webapp()
