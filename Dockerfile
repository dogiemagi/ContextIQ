FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY trustrag ./trustrag
COPY web ./web
COPY ui ./ui
COPY data/docs ./data/docs
COPY eval ./eval
RUN useradd -m app && mkdir -p /app/data && chown -R app /app
USER app
ENV HOST=0.0.0.0 NO_BROWSER=1
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/status')" || exit 1
CMD ["python", "-m", "trustrag.webapp"]
