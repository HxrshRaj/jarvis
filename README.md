# JARVIS — Personal AI Operating System

An independent personal-assistant project that turns natural-language requests into **bounded, permission-checked, verified
task workflows**, with memory, document RAG, voice, screenshot understanding and a small ML/deep-learning routing experiment.
It is inspired by the idea of a fictional assistant and is **not** an official Marvel/Iron Man product.
Author and owner: Harsh Raj.

> **Status: first substantial release, with documented gaps.** Everything listed under "What works" was run and tested.
> Features that need a paid/live model provider are implemented behind provider interfaces and tested with scripted fakes;
> they have **not** been exercised against a live provider. See [Known limitations](#known-limitations).

## What works
- **Command center UI** (dark by default, light theme toggle, responsive) with 11 pages: Command Center, Conversations, Tasks,
  Knowledge Base, Documents, Code Assistant, Memory, Tools & Permissions, Models & Providers, Evaluation, Security & Audit.
- **Task engine**: route → bounded plan → validation → approval gate → sandboxed execution → deterministic verification → report.
  States: pending / awaiting approval / running / succeeded / failed / cancelled / partially completed. Cancel (kills running
  processes), bounded retries, idempotent submission, resume after restart, audit trail. A non-zero command exit is never
  reported as plain success.
- **Tools** (typed, permissioned, audited): list/read/search files, statistics, CSV analysis, task history, document search,
  memory search/save, allowlisted command runner (`git status|diff|log` direct; `pytest`/`npm test` need approval).
- **Memory**: explicit saves only, secret refusal, edit/delete/export, global disable switch, separate from chat history.
- **Document RAG**: PDF/text ingestion, chunking, hybrid BM25 + hashed-embedding retrieval, per-user isolation, delete/re-index,
  and a **bounded LangGraph** workflow that verifies citations and says so when evidence is missing.
- **Voice**: push-to-talk (explicit mic permission states, released after each recording), speech-to-text and text-to-speech via
  provider interfaces, browser-local TTS fallback, mute/volume/stop. No continuous listening, no wake word.
- **Look at This**: explicit screenshot upload → configured vision model; validated, not stored, uncertainty caveat shown.
- **ML/DL**: labeled router dataset (synthetic, leakage-controlled), rules baseline vs scikit-learn vs PyTorch, real measured
  results — the PyTorch model did **not** beat the classical baseline ([docs/ML.md](docs/ML.md)).
- **Evaluation harness** (deterministic, versioned, stored) and **observability**: structured logs, `/metrics`, provider usage
  with measured tokens and optional estimated cost.
- **Ops**: Alembic migrations (drift-tested), Docker Compose (Postgres + backend + frontend) verified, GitHub Actions workflow.

## Quick start
Requires Python 3.11+ and Node 20+ (or just Docker).

```bash
# A) Docker (Postgres + migrations + UI)
cp .env.example .env        # set POSTGRES_PASSWORD and JARVIS_SECRET_KEY
docker compose up -d --build   # UI http://localhost:3000, API http://localhost:8000/docs

# B) Local, no Docker (SQLite)
cd backend && python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]" --extra-index-url https://download.pytorch.org/whl/cpu
python -m uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev
```
Create an account in the UI and try "run the tests" against the sample project in `workspace/`. Tools can only touch
`JARVIS_WORKSPACE_ROOT`. Without an LLM provider JARVIS runs in **offline mode** and says so; add a provider in
[docs/PROVIDERS.md](docs/PROVIDERS.md).

## Tests and results (this checkout)
| Suite | Command | Result |
|---|---|---|
| Backend (mocked providers) | `cd backend && python -m pytest -q` | 139 passed on Linux; 138 passed + 1 skipped (symlink test) on Windows |
| Frontend unit/component | `cd frontend && npm run lint && npm test` | 21 passed, `tsc` clean |
| Frontend build | `npm run build` | passes |
| End-to-end (Playwright, real Docker stack on Postgres) | `E2E_CHANNEL=chrome npx playwright test` | 7 passed |
| Deterministic evals | `python -m app.services.evals` | see Evaluation page; 1 known failure kept visible |
| ML experiment | `python -m ml.train` | see [docs/ML.md](docs/ML.md) |

The GitHub Actions workflow (`.github/workflows/ci.yml`) mirrors these commands but **has not been run yet** (no push has
triggered it at the time of writing). Mocked-provider tests are not integration tests of any real provider.

## Documentation
[Architecture](docs/ARCHITECTURE.md) · [Security & privacy](docs/SECURITY.md) · [Tools & permissions](docs/TOOLS.md) ·
[Memory & RAG](docs/RAG_MEMORY.md) · [ML & deep learning](docs/ML.md) · [Providers & voice/vision](docs/PROVIDERS.md) ·
[API](docs/API.md) · [Deployment & Docker](docs/DEPLOYMENT.md) · [Troubleshooting](docs/TROUBLESHOOTING.md) ·
[Implementation plan & status](IMPLEMENTATION_PLAN.md)

## Known limitations
- **No live-provider verification.** The OpenAI-compatible adapter (chat, vision, STT, TTS) is covered by scripted fakes only.
  No streaming and no native function-calling (plans are validated JSON).
- **Approved test runners execute project code as the host user**; there is no container/VM sandbox or resource limits yet.
- Retrieval uses hashed n-gram embeddings + BM25 stored as JSON — **not neural embeddings and not pgvector**. Memory search misses
  some paraphrases (one known case in the eval suite).
- **Not implemented:** Redis/Celery (in-process worker pool instead), pgvector, MLflow, OpenTelemetry, browser automation,
  screen capture/desktop control, wake-word, charts in data analysis, OCR for scanned PDFs, file-writing tools, provider
  configuration from the UI (read-only; use environment variables), a dedicated "sessions" table (tokens are stateless).
- Other LangGraph agents from the original brief (Coding, Data Analyst, Research, Memory as separate graph nodes) are realised as
  deterministic tools plus the engine; only the RAG answer workflow is a LangGraph graph.
- The UI polls for task progress (an SSE endpoint exists and is tested but unused by the UI).
- Session token is kept in `localStorage`; rate limiting is in-process; `/metrics` is unauthenticated.
- The router dataset is synthetic; ML numbers are indicative only and the PyTorch model underperforms the classical baseline.
- No license file is included; add one deliberately before sharing the code.
