# Local development, Docker and deployment

## Local (no Docker)
```bash
cd backend && python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]" --extra-index-url https://download.pytorch.org/whl/cpu
python -m uvicorn app.main:app --port 8000          # SQLite file backend/jarvis.db, tables auto-created
cd frontend && npm install && npm run dev            # http://localhost:3000
```
Tools may only touch `JARVIS_WORKSPACE_ROOT` (default `./workspace`, which contains a tiny sample project).

## Docker Compose (Postgres + backend + frontend) — verified
```bash
cp .env.example .env     # set POSTGRES_PASSWORD and JARVIS_SECRET_KEY (required; compose refuses to start without them)
docker compose up -d --build
```
- The backend container runs `alembic upgrade head` then uvicorn, as a non-root user; `./workspace` is mounted at `/workspace`.
- Postgres is **not** published to the host. UI: http://localhost:3000, API: http://localhost:8000 (docs at `/docs`).
- `NEXT_PUBLIC_API_URL` is baked in at build time (compose passes `http://localhost:8000`); change the build arg to deploy elsewhere.
- The image includes pytest so approved test runs work for stdlib-only workspace projects; projects with their own dependencies
  need those installed in the image.
- Stack verified in development by building all images, starting from an empty database, running the API smoke script and the Playwright suite.

## Running the tests
```bash
cd backend && python -m pytest -q                      # unit/integration (mocked providers)
cd frontend && npm run lint && npm test && npm run build
cd frontend && npx playwright install chromium         # once (or E2E_CHANNEL=chrome to reuse installed Chrome)
cd frontend && npx playwright test                      # needs the stack running (docker compose up or dev servers)
python -m app.services.evals                            # deterministic evaluation suite
```

## Deploying beyond localhost (checklist, not a certification)
1. Set a long random `JARVIS_SECRET_KEY`; set `JARVIS_CORS_ORIGINS` to your exact UI origin(s).
2. Terminate TLS in front of both services; do not expose `/metrics`.
3. Use managed Postgres; run `alembic upgrade head` as a release step.
4. Treat approved commands as host code execution: run the backend in a container/VM with no secrets and a read-only project mount.
5. Single backend replica unless you first move the rate limiter and task claiming off in-process state (see ARCHITECTURE.md).
6. Nothing in this repository publishes or deploys itself; no cloud resources are created.
