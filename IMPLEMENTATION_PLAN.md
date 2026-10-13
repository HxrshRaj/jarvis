# JARVIS — Implementation Plan & Status

Author/owner: Harsh Raj. Independent project; not affiliated with Marvel or Disney.
Legend: ✅ done, run and tested · 🟡 partial / not verified live · ⬜ not built. Nothing is marked ✅ unless it was executed.

Architecture, flows, state ownership and scaling paths: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Phase status

| # | Phase | Status | Evidence / notes |
|---|---|---|---|
| 1 | Inspect & plan | ✅ | this plan; environment inspected (Python 3.11, Node 24, Docker 29) |
| 2 | Foundation | ✅ | FastAPI, SQLAlchemy 2, Alembic (drift test), auth, Next.js, Docker Compose on Postgres verified |
| 3 | Command center | ✅ | 11 pages, orb, timeline, live task panel, status/privacy panel, theme toggle, mobile layout checked by e2e (no horizontal overflow) |
| 4 | Task engine | ✅ | states, approval, cancel, bounded retry, idempotency, restart recovery, SSE, audit; concurrency & duplicate-execution tests |
| 5 | GenAI integration | 🟡 | provider interface + OpenAI-compatible chat/vision/STT/TTS adapter, LLM planning with validated fallback, usage tracking — **scripted-fake tested only; no streaming, no native tool-calling** |
| 6 | Agentic workflows | 🟡 | LangGraph used for the bounded RAG answer workflow (gate/draft/verify/retry/fallback). Planner, verifier and synthesizer are deterministic engine components; other "agents" are tools, not separate graphs |
| 7 | Memory & RAG | ✅ (🟡 retrieval quality) | memory CRUD/export/disable/secret refusal; PDF/text ingestion; hybrid retrieval; citations; isolation. Embeddings are hashed n-grams, not neural/pgvector |
| 8 | Voice | 🟡 | push-to-talk, permission states, STT/TTS provider interfaces, browser TTS fallback — **live STT/TTS untested**; no wake word |
| 9 | Vision & code tools | 🟡 | screenshot upload analysis (provider-gated, validated, not stored); workspace browser + sandboxed command runner. No screen capture, no browser automation |
| 10 | ML & deep learning | ✅ | dataset + leakage tests, rules vs sklearn vs PyTorch, reproducible, results documented honestly (torch < sklearn) |
| 11 | Evaluation & hardening | ✅ (🟡 scope) | deterministic eval suite stored per run; rate limits; metrics; structured logs. No OpenTelemetry/Redis; live-LLM evals not run |
| 12 | Final verification | 🟡 | backend, frontend, e2e, Docker verified locally; **GitHub Actions not yet run** |

## Definition-of-done checklist
- [x] Command center functional; [x] task progress/history persist; [x] results verified before success is reported
- [x] user-controlled memory; [x] RAG with evidence-linked (extractive or verified-LLM) answers
- [x] tool execution respects explicit permissions; [x] critical security tests pass
- [x] ML and PyTorch experiments run with real, documented results
- [x] Docker setup documented **and verified**; [x] no real credentials committed
- [ ] configured LLM provider supports real conversations — **implemented, not verified live**
- [ ] voice input/spoken output "work when configured" — **implemented, not verified live**
- [ ] screenshot analysis "works when a vision provider is configured" — **implemented, not verified live**
- [ ] CI passes — **workflow written, not yet run**

## Not built (from the original brief)
Redis/Celery, pgvector, MLflow, OpenTelemetry, browser automation, desktop/screen capture, wake word, data charts, OCR,
file-writing tools, UI-based provider configuration, provider-configuration/model-version/sessions tables (versions live in
artifact metadata and eval configs; tokens are stateless), dependency audit in CI, container-sandboxed command runner.

## Suggested next steps
1. Run against a real provider (chat, document Q&A, vision, STT/TTS) and fix integration issues; add streaming.
2. Push and watch the CI workflow; fix any environment differences.
3. Containerised command runner; HttpOnly-cookie sessions; Redis-backed limiter/claims.
4. Neural embeddings + pgvector; a larger, non-synthetic router dataset; use the SSE endpoint in the UI.
