"""Compatibility entry point: lets hosts configured with `gunicorn app:app` run TrustRAG as well.

TrustRAG is an ASGI (FastAPI) application; a2wsgi presents it to gunicorn as WSGI. The preferred,
simpler start command is:   python -m trustrag.webapp
"""
from a2wsgi import ASGIMiddleware

from trustrag.webapp import create_webapp

app = ASGIMiddleware(create_webapp())
