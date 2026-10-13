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


# ---- search_documents / search_memory / save_memory --------------------------------------------------


class DocSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    k: int = Field(default=5, ge=1, le=10)


class DocHit(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    page: int | None
    score: float
    lexical: float
    semantic: float
    text: str


class DocSearchOut(BaseModel):
    query: str
    hits: list[DocHit]


def search_documents_tool(args: DocSearchIn, ctx: ToolContext) -> dict:
    from app.services import knowledge

    with ctx.db() as db:
        return {"query": args.query, "hits": knowledge.search_documents(db, ctx.user_id, args.query, args.k)}


class MemSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    k: int = Field(default=5, ge=1, le=10)


class MemItem(BaseModel):
    id: str
    kind: str
    content: str
    score: float


class MemSearchOut(BaseModel):
    memories: list[MemItem]
    memory_enabled: bool


def search_memory_tool(args: MemSearchIn, ctx: ToolContext) -> dict:
    from app.services import knowledge

    with ctx.db() as db:
        found = knowledge.search_memories(db, ctx.user_id, args.query, args.k)
        return {"memories": [{"id": m.id, "kind": m.kind, "content": m.content, "score": round(sc, 5)} for m, sc in found],
                "memory_enabled": knowledge.memory_enabled(db, ctx.user_id)}


class SaveMemIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    kind: str = "fact"


class SaveMemOut(BaseModel):
    id: str
    kind: str
    content: str


def save_memory_tool(args: SaveMemIn, ctx: ToolContext) -> dict:
    from app.services import knowledge

    with ctx.db() as db:
        try:
            m = knowledge.save_memory(db, ctx.user_id, args.content, args.kind)
        except knowledge.KnowledgeError as e:
            raise ToolError(str(e)) from None
        db.commit()
        return {"id": m.id, "kind": m.kind, "content": m.content}


def _save_memory_precheck(args: SaveMemIn) -> None:
    from app.services import knowledge

    if knowledge.contains_secret(args.content):
        raise ToolError("refusing to store what looks like a secret or sensitive identifier")


# ---- analyze_csv ----------------------------------------------------------------------------------------


class CsvIn(BaseModel):
    path: str


class ColumnStats(BaseModel):
    column: str
    count: int
    mean: float
    stdev: float | None
    minimum: float
    maximum: float
    missing: int


class CsvOut(BaseModel):
    path: str
    rows: int
    columns: list[str]
    numeric: list[ColumnStats]
    non_numeric: list[str]


def analyze_csv(args: CsvIn, ctx: ToolContext) -> dict:
    import pandas as pd

    target = resolve_in_workspace(ctx.workspace, args.path)
    if not target.is_file() or target.suffix.lower() != ".csv":
        raise ToolError("expected an existing .csv file")
    if target.stat().st_size > ctx.max_file_bytes * 8:
        raise ToolError("CSV is too large for in-process analysis")
    try:
        df = pd.read_csv(target, nrows=100_000)
    except Exception as e:
        raise ToolError(f"could not parse CSV ({type(e).__name__})") from None
    numeric, other = [], []
    for col in df.columns:
        series = pd.to_numeric(df[col], errors="coerce")
        if series.notna().sum() >= max(1, int(0.8 * df[col].notna().sum())) and df[col].notna().any():
            s = series.dropna()
            numeric.append({"column": str(col), "count": int(s.count()), "mean": float(s.mean()),
                            "stdev": float(s.std()) if len(s) > 1 else None, "minimum": float(s.min()),
                            "maximum": float(s.max()), "missing": int(df[col].isna().sum())})
        else:
            other.append(str(col))
    return {"path": args.path, "rows": int(len(df)), "columns": [str(c) for c in df.columns],
            "numeric": numeric, "non_numeric": other}


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
    reg.register(ToolSpec("search_documents", "Hybrid (BM25 + embedding) search over the user's uploaded documents.",
                          DocSearchIn, DocSearchOut, search_documents_tool, permissions=["documents.read"]))
    reg.register(ToolSpec("search_memory", "Search the user's saved memories (empty if memory is disabled).",
                          MemSearchIn, MemSearchOut, search_memory_tool, permissions=["memory.read"]))
    reg.register(ToolSpec("save_memory", "Save a user-approved memory (preference, project note or fact). Secrets are refused.",
                          SaveMemIn, SaveMemOut, save_memory_tool, permissions=["memory.write"], risk="medium",
                          precheck=_save_memory_precheck))
    reg.register(ToolSpec("analyze_csv", "Compute per-column statistics for a CSV file in the workspace (pandas).",
                          CsvIn, CsvOut, analyze_csv, permissions=["workspace.read"], timeout=60))
