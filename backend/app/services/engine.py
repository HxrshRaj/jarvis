"""Task engine: the only component allowed to execute tools.

State machine (task):  pending -> running -> {awaiting_approval <-> running} -> succeeded | failed |
partially_completed | cancelled.  The LLM proposes; this module enforces policy, validates every
input/output against typed schemas, persists every transition and audits every tool execution.
"""
from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.db import session_factory
from app.llm.providers import LLMError, get_provider, usage_context
from app.ml.router import route_request
from app.models import (
    TERMINAL, AuditEvent, Message, StepStatus, Task, TaskStatus, TaskStep,
)
from app.services.planner import PlanError, make_plan
from app.tools.registry import ToolContext, ToolError, TransientToolError, get_registry

log = logging.getLogger("jarvis.engine")
MAX_STEP_ATTEMPTS = 3


def _now() -> datetime:
    return datetime.now(UTC)


def audit(db, user_id, action, resource="", outcome="ok", **detail) -> None:
    db.add(AuditEvent(user_id=user_id, action=action, resource=resource, outcome=outcome, detail=detail))


class TaskEngine:
    def __init__(self, workers: int = 4):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="task")
        self._tool_pool = ThreadPoolExecutor(max_workers=workers * 2, thread_name_prefix="tool")
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._cancels: dict[str, threading.Event] = {}

    # ---- public API --------------------------------------------------------------------
    def submit(self, task_id: str) -> bool:
        """Queue a task. Returns False if it is already being executed (concurrency protection)."""
        with self._lock:
            if task_id in self._active:
                return False
            self._active.add(task_id)
            self._cancels[task_id] = threading.Event()
        self._pool.submit(self._run_guarded, task_id)
        return True

    def cancel(self, task_id: str) -> None:
        with self._lock:
            ev = self._cancels.get(task_id)
        if ev:
            ev.set()

    def is_active(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._active

    def wait_idle(self, timeout: float = 10.0) -> bool:
        import time

        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not self._active:
                return True
            time.sleep(0.02)
        return False

    def recover_interrupted(self) -> int:
        """After a restart, resume tasks that were mid-run."""
        with session_factory()() as db:
            ids = db.scalars(select(Task.id).where(Task.status == TaskStatus.RUNNING.value)).all()
        return sum(self.submit(i) for i in ids)

    # ---- internals ---------------------------------------------------------------------
    def _run_guarded(self, task_id: str) -> None:
        try:
            self._run(task_id)
        except Exception as e:  # last-resort: never leave a task stuck in "running"
            log.exception("task %s crashed", task_id)
            with session_factory()() as db:
                t = db.get(Task, task_id)
                if t and t.status not in TERMINAL:
                    t.status = TaskStatus.FAILED.value
                    t.error = f"internal error: {type(e).__name__}"
                    audit(db, t.user_id, "task.crash", task_id, "error", error=type(e).__name__)
                    db.commit()
        finally:
            with self._lock:
                self._active.discard(task_id)
                self._cancels.pop(task_id, None)

    def _cancelled(self, db, task_id: str, ev: threading.Event) -> bool:
        if ev.is_set():
            return True
        db.expire_all()
        t = db.get(Task, task_id)
        return t is None or t.status == TaskStatus.CANCELLED.value

    def _run(self, task_id: str) -> None:
        settings = get_settings()
        registry = get_registry()
        ev = self._cancels[task_id]
        with session_factory()() as db:
            task = db.get(Task, task_id)
            if task is None or task.status in TERMINAL:
                return
            task.status = TaskStatus.RUNNING.value
            db.commit()
            usage_context.set({"user_id": task.user_id, "purpose": "task"})

            if not task.steps and not (task.verification or {}).get("planned"):
                if not self._plan(db, task, registry):
                    return
            if not task.steps:
                self._direct_answer(db, task)
                return

            ctx = ToolContext(
                user_id=task.user_id, workspace=settings.workspace_root, cancel=ev, db=session_factory(),
                max_file_bytes=settings.max_file_bytes, max_output_chars=settings.max_output_chars,
                command_timeout=settings.command_timeout_seconds,
            )
            for step in task.steps:
                if step.status in (StepStatus.SUCCEEDED.value, StepStatus.REJECTED.value, StepStatus.FAILED.value):
                    continue
                if self._cancelled(db, task_id, ev):
                    return  # cancel() already finalised the task
                spec = registry.get(step.tool)
                if step.requires_approval and not step.approved:
                    step.status = StepStatus.AWAITING_APPROVAL.value
                    task.status = TaskStatus.AWAITING_APPROVAL.value
                    audit(db, task.user_id, "step.approval_requested", step.id, tool=step.tool, args=step.args)
                    db.commit()
                    return  # thread released; approve() resubmits
                self._exec_step(db, task, step, spec, ctx)
            if not self._cancelled(db, task_id, ev):
                self._finalise(db, task)

    def _plan(self, db, task: Task, registry) -> bool:
        provider = get_provider()
        decision = route_request(task.request)
        task.route = decision.route
        try:
            result = make_plan(task.request, registry, provider)
        except PlanError as e:
            task.status = TaskStatus.FAILED.value
            task.error = f"could not build a valid plan: {e}"
            self._assistant_message(db, task, f"I couldn't build a safe plan for that: {e}")
            db.commit()
            return False
        task.success_criteria = result.plan.success_criteria
        for i, ps in enumerate(result.plan.steps):
            spec = registry.get(ps.tool)
            args = spec.input_model.model_validate(ps.args)
            db.add(TaskStep(
                task_id=task.id, index=i, tool=ps.tool, description=ps.description or ps.tool,
                args=args.model_dump(), risk=spec.risk, requires_approval=spec.approval_required(args),
            ))
        task.verification = {"planned": True, "plan_source": result.source, "notes": result.notes,
                              "route": decision.route, "route_source": decision.source}
        audit(db, task.user_id, "task.planned", task.id, steps=len(result.plan.steps), source=result.source)
        db.commit()
        db.refresh(task)
        return True

    def _direct_answer(self, db, task: Task) -> None:
        provider = get_provider()
        try:
            text = provider.complete(
                "You are JARVIS, a concise personal assistant. If you are unsure, say so. Do not claim to have "
                "performed any action or used any tool.", task.request)
            task.status = TaskStatus.SUCCEEDED.value
            task.summary = text
            task.verification = {**(task.verification or {}), "tools_used": [], "all_passed": None,
                                 "note": "Direct model answer. No tools were used and nothing was verified."}
        except LLMError as e:
            task.status = TaskStatus.FAILED.value
            task.error = str(e)
            text = f"The language-model provider failed ({e}). Nothing was done."
            task.summary = text
        self._assistant_message(db, task, text)
        db.commit()

    def _exec_step(self, db, task: Task, step: TaskStep, spec, ctx: ToolContext) -> None:
        step.status = StepStatus.RUNNING.value
        step.started_at = _now()
        db.commit()
        err: str | None = None
        out: dict | None = None
        retries = spec.max_retries if spec else 0
        while True:
            step.attempts += 1
            try:
                if spec is None or not spec.available:
                    raise ToolError("tool unavailable")
                args = spec.input_model.model_validate(step.args)  # re-validate: never trust stored/LLM args
                fut = self._tool_pool.submit(spec.handler, args, ctx)
                try:
                    raw = fut.result(timeout=spec.timeout)
                except FutureTimeout:
                    raise TransientToolError(f"tool timed out after {spec.timeout}s") from None
                out = spec.output_model.model_validate(raw).model_dump()
                if spec.name == "run_command" and (out["timed_out"] or out["cancelled"]):
                    raise ToolError("command timed out" if out["timed_out"] else "command cancelled")
                err = None
                break
            except ValidationError as e:
                err = f"invalid tool arguments/output ({e.error_count()} error(s))"
                break
            except TransientToolError as e:
                err = str(e)
                if step.attempts > retries:
                    break
            except ToolError as e:
                err = str(e)
                break
            except Exception as e:  # tool bug: record type only, don't leak internals
                log.exception("tool %s crashed", step.tool)
                err = f"tool crashed: {type(e).__name__}"
                break
        step.finished_at = _now()
        if err is None:
            step.status, step.output, step.error = StepStatus.SUCCEEDED.value, out, None
        else:
            step.status, step.error = StepStatus.FAILED.value, err
            step.output = out
        audit(db, task.user_id, "tool.execute", f"{task.id}/{step.id}",
              "ok" if err is None else "error", tool=step.tool, attempts=step.attempts, error=err,
              approved=step.approved)
        db.commit()

    def _finalise(self, db, task: Task) -> None:
        db.expire_all()
        task = db.get(Task, task.id)
        if task.status == TaskStatus.CANCELLED.value:
            return
        checks = []
        for s in task.steps:
            ok = s.status == StepStatus.SUCCEEDED.value
            if ok:
                reason = "tool ran and its output matched the declared schema"
                if s.tool == "run_command" and s.output and s.output.get("exit_code") not in (0, None):
                    reason += f"; NOTE: command exited with code {s.output['exit_code']}"
            else:
                reason = s.error or s.status
            checks.append({"step": s.index + 1, "tool": s.tool, "passed": ok, "reason": reason})
        passed = sum(c["passed"] for c in checks)
        if passed == len(checks):
            task.status = TaskStatus.SUCCEEDED.value
        elif passed == 0:
            task.status = TaskStatus.FAILED.value
        else:
            task.status = TaskStatus.PARTIAL.value
        task.verification = {**(task.verification or {}), "checks": checks, "all_passed": passed == len(checks),
                             "tools_used": [s.tool for s in task.steps if s.status == StepStatus.SUCCEEDED.value]}
        task.summary = summarise(task)
        rag = self._rag_answer(task)
        if rag:
            task.verification = {**task.verification, "rag": {k: rag[k] for k in ("mode", "citations", "notes")}}
            task.summary = f"{rag['answer']}\n\n---\n{task.summary}"
        if task.status != TaskStatus.SUCCEEDED.value:
            task.error = "; ".join(f"step {c['step']} ({c['tool']}): {c['reason']}" for c in checks if not c["passed"])
        audit(db, task.user_id, "task.finished", task.id, task.status)
        self._assistant_message(db, task, task.summary)
        db.commit()

    @staticmethod
    def _rag_answer(task: Task) -> dict | None:
        """Run the bounded LangGraph answer workflow when a document search produced the evidence."""
        step = next((s for s in task.steps if s.tool == "search_documents" and s.status == StepStatus.SUCCEEDED.value), None)
        if step is None or not step.output:
            return None
        from app.agents.rag_graph import answer_with_citations

        try:
            return answer_with_citations(task.request, step.output["hits"], get_provider())
        except Exception:  # never let answer synthesis break a task whose tools succeeded
            log.exception("rag answer failed")
            return None

    @staticmethod
    def _assistant_message(db, task: Task, text: str) -> None:
        if task.conversation_id:
            db.add(Message(conversation_id=task.conversation_id, role="assistant", content=text, task_id=task.id))


def _describe(step: TaskStep) -> str:
    o = step.output or {}
    if step.tool == "list_directory":
        return f"{len(o.get('entries', []))} entries in '{o.get('path')}': " + ", ".join(
            e["name"] + ("/" if e["is_dir"] else "") for e in o.get("entries", [])[:15])
    if step.tool == "read_file":
        return f"read {o.get('bytes')} bytes from '{o.get('path')}'" + (" (truncated)" if o.get("truncated") else "")
    if step.tool == "search_files":
        return f"{len(o.get('hits', []))} match(es) for '{o.get('query')}' across {o.get('files_scanned')} files"
    if step.tool == "calculate_statistics":
        return (f"n={o['count']}, mean={o['mean']:.6g}, median={o['median']:.6g}, "
                f"min={o['minimum']:.6g}, max={o['maximum']:.6g}")
    if step.tool == "task_history":
        return f"{len(o.get('tasks', []))} recent task(s)"
    if step.tool == "search_documents":
        return f"{len(o.get('hits', []))} passage(s) found for '{o.get('query')}'"
    if step.tool == "search_memory":
        ms = o.get("memories", [])
        if not o.get("memory_enabled", True):
            return "persistent memory is disabled"
        return f"{len(ms)} memor{'y' if len(ms) == 1 else 'ies'}" + "".join(f"\n  - ({m['kind']}) {m['content']}" for m in ms)
    if step.tool == "save_memory":
        return f"saved {o.get('kind')} memory: {o.get('content')}"
    if step.tool == "analyze_csv":
        cols = "; ".join(f"{c['column']}: mean={c['mean']:.6g}, min={c['minimum']:.6g}, max={c['maximum']:.6g}" for c in o.get("numeric", [])[:8])
        return f"{o.get('rows')} rows, {len(o.get('columns', []))} columns. {cols}"
    if step.tool == "run_command":
        tail = "\n".join((o.get("output") or "").strip().splitlines()[-5:])
        return f"`{' '.join(o['command'])}` exited with code {o['exit_code']} in {o['duration_seconds']}s\n{tail}"
    return json.dumps(o)[:200]


def summarise(task: Task) -> str:
    """Deterministic report built only from recorded tool results — no model-invented claims."""
    lines = [f"Task {task.status.replace('_', ' ')}."]
    failed_cmds = [s for s in task.steps if s.tool == "run_command" and s.status == StepStatus.SUCCEEDED.value
                   and (s.output or {}).get("exit_code") not in (0, None)]
    if failed_cmds:  # the tool ran, but the command itself did not pass: never let the headline imply otherwise
        lines[0] += " WARNING: a command exited with a non-zero status, so the tests/command did NOT pass."
    for s in task.steps:
        if s.status == StepStatus.SUCCEEDED.value:
            lines.append(f"- Step {s.index + 1} ({s.tool}): {_describe(s)}")
        elif s.status == StepStatus.REJECTED.value:
            lines.append(f"- Step {s.index + 1} ({s.tool}): not run — you declined approval.")
        else:
            lines.append(f"- Step {s.index + 1} ({s.tool}): {s.status}{' — ' + s.error if s.error else ''}")
    return "\n".join(lines)


engine = TaskEngine()
