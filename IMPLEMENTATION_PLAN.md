# JARVIS — Implementation Plan & Status

Author/owner: Harsh Raj. Independent project; not affiliated with Marvel or Disney.
Legend: ✅ done and tested · 🟡 partial · ⬜ not started. Nothing is marked done unless it was run and verified.

## Architecture (modular monolith)

```
Next.js UI ──REST/SSE──> FastAPI ──> TaskEngine (thread pool) ──> ToolRegistry ──> sandboxed tools
                           │              │  planner (LLM or rules) → validate → policy → execute → verify
                           │              └─ LLMProvider interface (mock | OpenAI-compatible)
                           └─ SQLAlchemy 2 → SQLite (default) | PostgreSQL
```

Key rules enforced in code, not prompts:
1. The model only *proposes* a plan. Every step is validated against the tool's typed input schema and a static
   `precheck` (command allowlist) before it is stored; invalid plans fall back to a deterministic rule planner.
2. Tools that run project code (pytest, npm test) always pause in `awaiting_approval`; nothing runs until the user approves.
3. Tool outputs are validated against output schemas; task status (`succeeded/failed/partially_completed`) is computed
   from recorded step results, and the summary is built deterministically from them — never from model prose.
4. All paths are confined to `JARVIS_WORKSPACE_ROOT`; secrets/keys/.git are refused; commands use argv (no shell), an
   allowlist, a scrubbed environment, timeouts and cancellation.
5. Everything sensitive writes an audit event.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1 Inspect & plan | repo/env inspection, this plan | ✅ |
| 2 Foundation | FastAPI, SQLAlchemy models, auth (scrypt + HMAC tokens), config, Next.js app | ✅ (SQLite verified; **Postgres, Alembic, Redis not yet exercised**) |
| 3 Command center | orb, command input, timeline, live task panel, recent tasks, tools/audit/tasks pages | 🟡 (4 of 12 pages; voice, theme toggle, mobile polish pending) |
| 4 Task engine | states, approval, cancel, retry (bounded), idempotency, recovery, SSE, audit | ✅ (70 backend tests) |
| 5 GenAI | provider interface + OpenAI-compatible adapter + LLM planner w/ fallback | 🟡 adapter is **untested against a live provider**; no streaming, no native tool-calling yet |
| 6 Agentic workflows (LangGraph) | specialised agents | ⬜ (only planner + deterministic verifier/synthesizer exist) |
| 7 Memory & RAG | pgvector, ingestion, citations | ⬜ |
| 8 Voice | STT/TTS, push-to-talk | ⬜ |
| 9 Vision & code tools | screenshot upload, workspace inspection | 🟡 workspace read/search/run tools done; screenshot analysis ⬜ |
| 10 ML / PyTorch | router dataset, sklearn, torch | 🟡 rule-based baseline router only; no trained model, no results to report |
| 11 Eval & hardening | eval harness, metrics, OTel | ⬜ (rate limiting + structured logs only) |
| 12 Final verification | Docker verified, CI green | ⬜ (Docker files/CI written, **not yet run**) |

## Next steps (in order)
1. Alembic migrations + run the suite against PostgreSQL; verify `docker compose up`.
2. Live-provider integration test, then streaming + native tool-calling.
3. Memory (explicit save/edit/delete/export) and document RAG with citations.
4. Router dataset + sklearn model compared against the rule baseline; then PyTorch experiment.
5. Evaluation harness, voice (push-to-talk), screenshot analysis, LangGraph agents.
