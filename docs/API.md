# API

Interactive OpenAPI docs: `http://localhost:8000/docs` (schema at `/openapi.json`). All routes are under `/api/v1` and (except
`/auth/*`, `/health*`, `/metrics`) need `Authorization: Bearer <token>`. Errors: `{"detail": "..."}`; unknown or foreign resources return 404.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Chat/tasks | `POST /chat` (202; `idempotency_key` supported), `GET /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/cancel`, `POST /tasks/{id}/retry`, `POST /tasks/{id}/steps/{sid}/approve|reject`, `GET /tasks/{id}/events` (SSE snapshots) |
| Conversations | `GET /conversations`, `GET|DELETE /conversations/{id}` |
| Tools/audit | `GET /tools`, `GET /audit` |
| Memory | `GET|POST /memories`, `PATCH|DELETE /memories/{id}`, `POST /memories/search`, `GET /memories-export`, `GET|PUT /settings/memory` |
| Documents | `POST /documents` (multipart), `GET /documents`, `GET /documents/{id}/text`, `DELETE /documents/{id}`, `POST /documents/{id}/reindex`, `POST /documents/search` |
| Vision | `POST /vision/analyze` (multipart `image`, `question`) |
| Voice | `POST /voice/transcribe` (multipart `audio`), `POST /voice/speak` |
| Workspace | `GET /workspace/list`, `GET /workspace/file` (same sandbox as tools) |
| Settings/usage | `GET /capabilities`, `GET /settings/provider`, `GET /usage` |
| Evaluation | `POST /evals/run`, `GET /evals`, `GET /ml/report` |
| Ops (no prefix) | `GET /health`, `GET /health/ready`, `GET /metrics` |

Task states: `pending`, `awaiting_approval`, `running`, `succeeded`, `failed`, `cancelled`, `partially_completed`.
Step states: `pending`, `awaiting_approval`, `running`, `succeeded`, `failed`, `rejected`, `skipped`.
The UI polls `GET /tasks/{id}` every 0.7 s while a task is active; the SSE endpoint is implemented and tested but not yet used by the UI.
