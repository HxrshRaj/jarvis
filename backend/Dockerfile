FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Code lives at /srv/backend so app.config.ROOT resolves to /srv (ml artifacts: /srv/backend/ml/artifacts)
WORKDIR /srv/backend
COPY pyproject.toml ./
# Install runtime deps only (torch is a training-time extra and is intentionally not installed here).
RUN mkdir app ml && touch app/__init__.py ml/__init__.py && pip install -e . && rm -rf app ml
# pytest lets the approved `pytest` tool run stdlib-only workspace projects inside the container
RUN pip install pytest
COPY . .
RUN useradd --create-home --uid 10001 jarvis && mkdir /workspace && chown jarvis /workspace
USER jarvis
ENV JARVIS_WORKSPACE_ROOT=/workspace
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health')"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
