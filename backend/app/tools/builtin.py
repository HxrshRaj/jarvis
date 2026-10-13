from __future__ import annotations

import statistics

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.tools.registry import ToolContext, ToolError, ToolRegistry, ToolSpec
from app.tools.sandbox import SENSITIVE_DIRS, resolve_in_workspace, run_allowlisted, validate_command

# ---- list_directory -------------------------------------------------------------------------


class ListDirIn(BaseModel):
    path: str = "."


class DirEntry(BaseModel):
    name: str
    is_dir: bool
    size: int | None = None


class ListDirOut(BaseModel):
    path: str
    entries: list[DirEntry]
    truncated: bool = False


def list_directory(args: ListDirIn, ctx: ToolContext) -> dict:
    target = resolve_in_workspace(ctx.workspace, args.path)
    if not target.is_dir():
        raise ToolError("not a directory")
    entries = []
    for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        if p.name.lower() in SENSITIVE_DIRS:
            continue
        entries.append({"name": p.name, "is_dir": p.is_dir(), "size": None if p.is_dir() else p.stat().st_size})
    return {"path": args.path, "entries": entries[:200], "truncated": len(entries) > 200}


# ---- read_file ------------------------------------------------------------------------------


class ReadFileIn(BaseModel):
    path: str


class ReadFileOut(BaseModel):
    path: str
    content: str
    bytes: int
    truncated: bool


def read_file(args: ReadFileIn, ctx: ToolContext) -> dict:
    target = resolve_in_workspace(ctx.workspace, args.path)
    if not target.is_file():
        raise ToolError("file not found")
    with target.open("rb") as f:
        raw = f.read(ctx.max_file_bytes + 1)
    if b"\x00" in raw[:1024]:
        raise ToolError("binary files are not supported")
    truncated = len(raw) > ctx.max_file_bytes
    raw = raw[: ctx.max_file_bytes]
    return {"path": args.path, "content": raw.decode("utf-8", errors="replace"), "bytes": len(raw), "truncated": truncated}


# ---- search_files ---------------------------------------------------------------------------


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    path: str = "."


class SearchHit(BaseModel):
    file: str
    line: int
    text: str


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]
    files_scanned: int
    truncated: bool = False


def search_files(args: SearchIn, ctx: ToolContext) -> dict:
    base = resolve_in_workspace(ctx.workspace, args.path)
    needle = args.query.lower()
    root = ctx.workspace.resolve()
    hits: list[dict] = []
    scanned = 0
    files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
    for p in files:
        if ctx.cancel.is_set() or len(hits) >= 100 or scanned >= 2000:
            break
        rel = p.relative_to(root)
        if any(part.lower() in SENSITIVE_DIRS | {"node_modules", ".venv", "__pycache__"} for part in rel.parts):
            continue
        try:
            resolve_in_workspace(ctx.workspace, str(rel))
            if p.stat().st_size > ctx.max_file_bytes:
                continue
            text = p.read_text(encoding="utf-8")
        except (ToolError, UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for i, line in enumerate(text.splitlines(), 1):
            if needle in line.lower():
                hits.append({"file": rel.as_posix(), "line": i, "text": line.strip()[:200]})
                if len(hits) >= 100:
                    break
    return {"query": args.query, "hits": hits, "files_scanned": scanned, "truncated": len(hits) >= 100}


# ---- calculate_statistics -------------------------------------------------------------------


class StatsIn(BaseModel):
    values: list[float] = Field(min_length=1, max_length=10_000)


class StatsOut(BaseModel):
    count: int
    mean: float
    median: float
    minimum: float
    maximum: float
    stdev: float | None


def calculate_statistics(args: StatsIn, ctx: ToolContext) -> dict:
    v = args.values
    return {
        "count": len(v),
        "mean": statistics.fmean(v),
        "median": statistics.median(v),
        "minimum": min(v),
        "maximum": max(v),
        "stdev": statistics.stdev(v) if len(v) > 1 else None,
    }


# ---- task_history ---------------------------------------------------------------------------


class HistoryIn(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


class HistoryItem(BaseModel):
    id: str
    request: str
    status: str
    created_at: str


class HistoryOut(BaseModel):
    tasks: list[HistoryItem]


def task_history(args: HistoryIn, ctx: ToolContext) -> dict:
    from app.models import Task

    with ctx.db() as db:
        rows = db.scalars(
            select(Task).where(Task.user_id == ctx.user_id).order_by(Task.created_at.desc()).limit(args.limit)
        ).all()
        return {
            "tasks": [
                {"id": t.id, "request": t.request[:200], "status": t.status, "created_at": t.created_at.isoformat()}
                for t in rows
            ]
        }


# ---- run_command ----------------------------------------------------------------------------


class RunCommandIn(BaseModel):
    argv: list[str] = Field(min_length=1, max_length=12)


class RunCommandOut(BaseModel):
    command: list[str]
    exit_code: int | None
    output: str
    truncated: bool
    timed_out: bool
    cancelled: bool
    duration_seconds: float


def run_command(args: RunCommandIn, ctx: ToolContext) -> dict:
    return run_allowlisted(args.argv, ctx.workspace, ctx.command_timeout, ctx.cancel, ctx.max_output_chars)


def _command_needs_approval(args: RunCommandIn) -> bool:
    try:
        return validate_command(args.argv)
    except ToolError:
        return True  # invalid commands are rejected at plan time anyway


def register_builtin(reg: ToolRegistry) -> None:
    reg.register(ToolSpec("list_directory", "List files in a directory of the approved workspace.",
                          ListDirIn, ListDirOut, list_directory, permissions=["workspace.read"]))
    reg.register(ToolSpec("read_file", "Read a text file from the approved workspace (size-limited).",
                          ReadFileIn, ReadFileOut, read_file, permissions=["workspace.read"]))
    reg.register(ToolSpec("search_files", "Case-insensitive text search across workspace files.",
                          SearchIn, SearchOut, search_files, permissions=["workspace.read"], timeout=60))
    reg.register(ToolSpec("calculate_statistics", "Deterministic descriptive statistics for a list of numbers.",
                          StatsIn, StatsOut, calculate_statistics))
    reg.register(ToolSpec("task_history", "Retrieve the user's most recent tasks.",
                          HistoryIn, HistoryOut, task_history, permissions=["history.read"]))
    reg.register(ToolSpec("run_command",
                          "Run an allowlisted command (git status/diff/log, pytest, npm test) in the workspace. "
                          "Test runners execute project code and therefore require approval.",
                          RunCommandIn, RunCommandOut, run_command, permissions=["workspace.execute"],
                          risk="low", timeout=120, needs_approval=_command_needs_approval,
                          precheck=lambda a: validate_command(a.argv)))
