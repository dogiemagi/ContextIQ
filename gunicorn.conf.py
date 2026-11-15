# Picked up automatically by gunicorn when it starts in this folder (`gunicorn app:app ...`).
# Command-line flags such as --bind still override these values.
worker_class = "uvicorn_worker.UvicornWorker"  # ASGI worker (package: uvicorn-worker) for the FastAPI app
workers = 1       # login-attempt counters and caches live in memory, so keep a single process
timeout = 120     # slow hosted/local models can take a while to answer
graceful_timeout = 30
keepalive = 5
