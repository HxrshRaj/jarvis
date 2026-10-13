# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| UI says "Cannot reach the JARVIS backend" | Backend not running or wrong `NEXT_PUBLIC_API_URL`. Check `curl localhost:8000/health`. |
| Signed out unexpectedly | Token expired (12 h), or `JARVIS_SECRET_KEY` changed, or the database was reset. Sign in again. |
| `429 Rate limit exceeded` | Auth endpoints allow 20/min per IP; other API calls 600/min per token. Wait a minute. |
| Docker: "set POSTGRES_PASSWORD in .env" | Create `.env` from `.env.example`; both required values must be set. |
| Docker: port already in use | Change the host port mapping in `docker-compose.yml` (only 3000 and 8000 are published). |
| "pytest: No module named pytest" in task output | The workspace project needs its dependencies in the backend environment/image. |
| Task stuck in `awaiting_approval` | By design: approve or decline the step in the task panel. |
| "No language-model provider is configured" | Offline mode. See PROVIDERS.md. |
| Voice: "No speech-to-text provider" | Set `JARVIS_LLM_STT_MODEL`; the mic is never opened until a provider exists. |
| Voice: "Microphone access was denied" | Allow the microphone for the site in browser settings. |
| Document upload rejected | Check type (PDF/TXT/MD/CSV/LOG/RST), size ≤5 MB, UTF-8 text, not an encrypted/scanned PDF, not a duplicate. |
| Memory not saved | Secret-like content is refused, or memory is disabled in Memory → Persistent memory. |
| `alembic` errors on an existing Postgres DB created by an older version | Tables created outside Alembic: drop the schema in dev, or `alembic stamp 0001` if it matches. |
| Vitest "Timeout waiting for worker" on OneDrive paths | The config already uses the `threads` pool; retry or move the repo outside OneDrive. |
| Next build picks the wrong workspace root | `next.config.mjs` pins `outputFileTracingRoot`; remove stray lockfiles in parent directories. |
