# Security & privacy notes

Honest scope: this is a single-user/local-first application with real security controls, **not** a hardened multi-tenant
service and not security-certified.

## Controls implemented (and tested)
| Area | Control | Tests |
|---|---|---|
| Authn | scrypt password hashing; HMAC-signed expiring bearer tokens; tampered/expired tokens rejected | `test_auth_and_access.py` |
| Authz | every resource row carries `user_id`; foreign IDs return 404; tasks, conversations, memories, documents, chunks, audit isolated | `test_auth_and_access.py`, `test_knowledge.py` |
| LLM is untrusted | plan validated (typed args + allowlist) before storage; approvals enforced by the engine; classifier label cannot change approval | `test_planner_and_registry.py`, `test_task_engine.py`, `test_ml.py` |
| Prompt injection | file/document/image text never becomes plan steps; RAG answers must cite valid sources else fall back; retrieved text is fenced and marked as data | `test_task_engine.py`, `test_knowledge.py` |
| Filesystem | all paths resolved and confined to `JARVIS_WORKSPACE_ROOT` (incl. symlinks); `.env*`, keys, `.ssh`, `.git`, DB files refused | `test_sandbox.py` |
| Commands | argv allowlist (`git status/diff/log`, `pytest`, `npm test`), no shell, flag denylist, safe-arg regex, scrubbed env (no inherited secrets), timeout, cancel kills the process, output capped | `test_sandbox.py`, `test_task_engine.py` |
| Approvals | commands that execute project code and memory writes pause until the user approves; reject never executes | `test_task_engine.py`, `test_knowledge.py`, e2e |
| Uploads | size caps, magic-byte checks (PDF/image), extension allowlist, UTF-8/binary checks, encrypted PDFs refused, filename sanitised | `test_knowledge.py` |
| Memory | refuses passwords/keys/tokens/SSN/card-shaped strings (also not echoed to the audit log); can be disabled; export and delete | `test_knowledge.py` |
| Secrets | provider keys only from environment; never stored/returned (`/settings/provider` shows `api_key_configured`) | `test_knowledge.py` |
| Abuse | per-token rate limit; strict per-IP auth limit; CORS allowlist (no credentials); safe 500s; `nosniff`, `no-referrer` | `test_evals_and_infra.py` |
| Audit | logins, plans, approvals, tool executions, memory/document/vision/voice events | `test_task_engine.py` |
| Privacy | vision images are never stored (metadata-only audit); microphone is only opened while push-to-talk is held and released afterwards; no continuous listening, no wake word | `test_knowledge.py`, `VoiceControls.test.tsx` |

## Known gaps (please read)
- **Approved test runners execute project code as your OS user.** There is no container/VM sandbox, CPU/memory/network limits,
  or filesystem jail beyond path confinement of the *tools*. Only approve commands for projects you trust. A containerised runner
  is the recommended next step.
- The session token is stored in browser `localStorage` (XSS-readable). A same-site `HttpOnly` cookie + CSRF protection would be stronger.
- Tokens are stateless (no server-side revocation list); rotate `JARVIS_SECRET_KEY` to invalidate all sessions.
- Rate limiting is per process (in-memory). Behind multiple workers use Redis.
- `/metrics` is unauthenticated: expose it only on a trusted network.
- The sklearn artifact is a pickle (`joblib`): never load artifacts you did not train. The torch checkpoint loads with `weights_only=True`.
- Screen capture, browser automation and desktop control are **not implemented**, so there is nothing to misuse there.
- Dependency auditing (`npm audit`, `pip-audit`) is not wired into CI yet.
- Retention: conversations/documents/memories are user-deletable; tasks and audit rows are retained (no automatic expiry).
