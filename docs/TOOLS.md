# Tools & permissions

Tools live in `backend/app/tools/`. Each `ToolSpec` declares: name, description, input schema (pydantic), output schema,
permission tags, risk, timeout, retry count, an optional `needs_approval(args)` rule, an optional plan-time `precheck(args)`,
availability, and audit behaviour. The registry is visible in the UI (**Tools & Permissions**) and at `GET /api/v1/tools`.

| Tool | Permissions | Approval | Notes |
|---|---|---|---|
| `list_directory` | workspace.read | no | sensitive dirs hidden |
| `read_file` | workspace.read | no | ≤256 KB, text only, sensitive files refused |
| `search_files` | workspace.read | no | substring search, skips `.git`, `node_modules`, `.venv` |
| `calculate_statistics` | — | no | deterministic (`statistics` module) |
| `analyze_csv` | workspace.read | no | pandas per-column stats, ≤100k rows |
| `task_history` | history.read | no | caller's own tasks only |
| `search_documents` | documents.read | no | hybrid BM25 + hashed embeddings, caller's documents only |
| `search_memory` | memory.read | no | empty when memory disabled |
| `save_memory` | memory.write | **yes** | refuses secrets at plan time and again at execution |
| `run_command` | workspace.execute | **conditional** | `git status/diff/log` run directly; `pytest` and `npm test` require approval |

Not implemented: browser automation, desktop control, package installation, file writes. Adding a tool that writes files
or installs dependencies should use `risk="medium"` (always approval) and a `precheck`.

Allowlisted commands (`backend/app/tools/sandbox.py`): `git status|diff|log`, `python -m pytest`, `pytest`, `npm test`.
Denied flags include `-c`, `-p`, `--rootdir`, `--exec`, `--output`, `--git-dir`; arguments must match a safe regex, contain no `..`,
and not be absolute paths.
