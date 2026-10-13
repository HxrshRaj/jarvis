# JARVIS — Personal AI Operating System

An independent, in-progress personal assistant that turns natural-language requests into **bounded, permission-checked,
verified task workflows**. Inspired by the idea of a fictional assistant; not an official Marvel/Iron Man product.
Author and owner: Harsh Raj.

> **Status: early checkpoint.** The task engine, tool sandbox, auth, audit trail and a 4-page command center work and are
> tested. Memory, RAG, voice, vision, LangGraph agents and the ML/PyTorch experiments are **not built yet** — see
> [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for an honest per-phase status.

## What works today
- Register/sign in (scrypt password hashing, signed expiring tokens, per-user resource isolation).
- Submit a request → router label → bounded plan → approval gate → sandboxed execution → deterministic verification → report.
- Tools: `list_directory`, `read_file`, `search_files`, `calculate_statistics`, `task_history`, `run_command`
  (allowlist: `git status|diff|log`, `pytest`, `npm test`). Test runners require your approval before anything executes.
- Cancel (kills a running process), bounded retry (3 attempts/step), idempotent submission, resume after restart, SSE progress.
- Audit log of logins, plans, approvals, tool executions and cancellations.
- Optional real LLM planning/answers through any OpenAI-compatible endpoint. **Without a provider JARVIS runs in offline
  mode: it executes tool tasks but says plainly that it cannot answer open-ended questions.**

## Quick start (no Docker, no paid services)
Requires Python 3.11+ and Node 20+.

```bash
# backend  (http://localhost:8000, docs at /docs)
cd backend
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
python -m uvicorn app.main:app --port 8000

# frontend (http://localhost:3000)
cd frontend && npm install && npm run dev
```
Open http://localhost:3000, create an account, and try "run the tests" against the sample project in `workspace/`.
Tools can only touch `JARVIS_WORKSPACE_ROOT` (default `./workspace`).

## Enabling a language model
Copy `.env.example` to `backend/.env`, set `JARVIS_LLM_PROVIDER=openai_compat`, `JARVIS_LLM_API_KEY`, and optionally
`JARVIS_LLM_BASE_URL` / `JARVIS_LLM_MODEL` (works with OpenAI, Ollama, LM Studio, vLLM). Keys are read from the
environment only, never stored in the database or returned by the API. *This adapter has not yet been tested against a live provider.*

## Tests
```bash
cd backend && .venv/Scripts/python -m pytest -q      # 70 passed, 1 skipped (symlink test on Windows)
cd frontend && npm run lint && npm test && npm run build
```
Deterministic tests only; no live LLM calls. Covered: auth, access isolation, path/command sandbox, planner validation,
prompt-injection and malicious-plan handling, approval/reject/cancel/retry, idempotency, concurrency, recovery, SSE, rate limit.

## Security model (summary)
The LLM never executes anything. The engine validates plans (typed schemas + command allowlist), forces approvals,
confines file access to the workspace, refuses secrets (`.env`, keys, `.ssh`, `.git`), runs commands without a shell in a
scrubbed environment with timeouts, and audits every action. Known limits: commands run as your OS user (no container
sandbox yet — approved test runners execute project code); rate limiting is in-process; the browser stores the session
token in `localStorage`; no microphone/screen/browser access exists yet.

## Known limitations
Docker/Compose files and PostgreSQL support are **not yet written/verified**; no Alembic migrations (tables are created
at startup); polling is used by the UI although an SSE endpoint exists; the 8 remaining UI pages, voice, vision, memory,
RAG, agents and ML work are unimplemented.
