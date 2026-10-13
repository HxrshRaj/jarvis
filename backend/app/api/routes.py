from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db, session_factory
from app.models import (
    TERMINAL, AuditEvent, Conversation, Message, StepStatus, Task, TaskStatus, TaskStep, User,
)
from app.schemas import (
    AuditOut, ChatIn, ChatOut, ConversationDetail, ConversationOut, Creds, Page, TaskListItem,
    TaskOut, TokenOut, UserOut,
)
from app.security import create_token, hash_password, verify_password
from app.services.engine import MAX_STEP_ATTEMPTS, audit, engine
from app.tools.registry import get_registry

router = APIRouter(prefix="/api/v1")


# ---- auth --------------------------------------------------------------------------------------
@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: Creds, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    audit(db, user.id, "auth.register", user.id)
    db.commit()
    return TokenOut(access_token=create_token(user.id))


@router.post("/auth/login", response_model=TokenOut)
def login(body: Creds, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    ok = bool(user) and verify_password(body.password, user.password_hash)
    audit(db, user.id if user else None, "auth.login", "", "ok" if ok else "denied")
    db.commit()
    if not ok:
        raise HTTPException(401, "Invalid email or password")
    return TokenOut(access_token=create_token(user.id))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, email=user.email)


# ---- helpers -----------------------------------------------------------------------------------
def _own_task(db: Session, user: User, task_id: str) -> Task:
    t = db.get(Task, task_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Task not found")  # 404, not 403: don't reveal existence
    return t


# ---- chat / conversations ----------------------------------------------------------------------
@router.post("/chat", response_model=ChatOut, status_code=202)
def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.idempotency_key:
        existing = db.scalar(select(Task).where(Task.user_id == user.id, Task.idempotency_key == body.idempotency_key))
        if existing:
            return ChatOut(conversation_id=existing.conversation_id or "", task_id=existing.id)
    if body.conversation_id:
        conv = db.get(Conversation, body.conversation_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(404, "Conversation not found")
    else:
        conv = Conversation(user_id=user.id, title=body.message[:60])
        db.add(conv)
        db.flush()
    db.add(Message(conversation_id=conv.id, role="user", content=body.message))
    task = Task(user_id=user.id, conversation_id=conv.id, request=body.message, idempotency_key=body.idempotency_key)
    db.add(task)
    db.flush()
    audit(db, user.id, "task.created", task.id)
    try:
        db.commit()
    except IntegrityError:  # concurrent duplicate submission with the same idempotency key
        db.rollback()
        existing = db.scalar(select(Task).where(Task.user_id == user.id, Task.idempotency_key == body.idempotency_key))
        if existing:
            return ChatOut(conversation_id=existing.conversation_id or "", task_id=existing.id)
        raise
    engine.submit(task.id)
    return ChatOut(conversation_id=conv.id, task_id=task.id)


@router.get("/conversations", response_model=Page)
def conversations(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Conversation).where(Conversation.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Conversation.created_at.desc()).limit(limit).offset(offset)).all()
    return Page(items=[ConversationOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def conversation(conv_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    return conv


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    db.delete(conv)
    audit(db, user.id, "conversation.delete", conv_id)
    db.commit()


# ---- tasks -------------------------------------------------------------------------------------
@router.get("/tasks", response_model=Page)
def list_tasks(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), status: str | None = None,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Task).where(Task.user_id == user.id)
    if status:
        q = q.where(Task.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Task.created_at.desc()).limit(limit).offset(offset)).all()
    return Page(items=[TaskListItem.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _own_task(db, user, task_id)


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own_task(db, user, task_id)
    if t.status in TERMINAL:
        raise HTTPException(409, f"Task already {t.status}")
    t.status = TaskStatus.CANCELLED.value
    t.error = "cancelled by user"
    for s in t.steps:
        if s.status in (StepStatus.PENDING.value, StepStatus.AWAITING_APPROVAL.value):
            s.status = StepStatus.SKIPPED.value
    audit(db, user.id, "task.cancel", t.id)
    db.commit()
    engine.cancel(t.id)
    return t


@router.post("/tasks/{task_id}/retry", response_model=TaskOut)
def retry_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _own_task(db, user, task_id)
    if t.status not in (TaskStatus.FAILED.value, TaskStatus.PARTIAL.value):
        raise HTTPException(409, "Only failed or partially completed tasks can be retried")
    if engine.is_active(t.id):
        raise HTTPException(409, "Task is still running")
    resettable = [s for s in t.steps if s.status == StepStatus.FAILED.value]
    if any(s.attempts >= MAX_STEP_ATTEMPTS for s in resettable) or not resettable:
        raise HTTPException(409, "Nothing left to retry (attempt limit reached or no failed steps)")
    for s in resettable:
        s.status, s.error, s.output = StepStatus.PENDING.value, None, None
    t.status, t.error, t.summary = TaskStatus.PENDING.value, None, None
    audit(db, user.id, "task.retry", t.id)
    db.commit()
    engine.submit(t.id)
    return t


def _decide(task_id: str, step_id: str, approve: bool, user: User, db: Session):
    t = _own_task(db, user, task_id)
    step = db.get(TaskStep, step_id)
    if step is None or step.task_id != t.id:
        raise HTTPException(404, "Step not found")
    if t.status != TaskStatus.AWAITING_APPROVAL.value or step.status != StepStatus.AWAITING_APPROVAL.value:
        raise HTTPException(409, "Step is not awaiting approval")
    if approve:
        step.approved, step.status = True, StepStatus.PENDING.value
    else:
        step.status, step.error = StepStatus.REJECTED.value, "declined by user"
    t.status = TaskStatus.PENDING.value
    audit(db, user.id, "step.approve" if approve else "step.reject", step.id, tool=step.tool, args=step.args)
    db.commit()
    engine.submit(t.id)
    return t


@router.post("/tasks/{task_id}/steps/{step_id}/approve", response_model=TaskOut)
def approve_step(task_id: str, step_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _decide(task_id, step_id, True, user, db)


@router.post("/tasks/{task_id}/steps/{step_id}/reject", response_model=TaskOut)
def reject_step(task_id: str, step_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _decide(task_id, step_id, False, user, db)


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str, user: User = Depends(current_user)):
    """SSE of full task snapshots. Snapshot-based, so reconnecting clients simply receive current state."""
    with session_factory()() as db:
        _own_task(db, user, task_id)

    def snapshot() -> str:
        with session_factory()() as db:
            t = db.get(Task, task_id)
            if t is None:
                return ""
            return TaskOut.model_validate(t).model_dump_json()

    async def gen():
        last = None
        for _ in range(1200):  # ~10 minutes max per connection; clients reconnect
            snap = await asyncio.to_thread(snapshot)
            if not snap:
                return
            if snap != last:
                last = snap
                yield f"data: {snap}\n\n"
                if json.loads(snap)["status"] in TERMINAL:
                    return
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


# ---- tools / audit -----------------------------------------------------------------------------
@router.get("/tools")
def list_tools(_: User = Depends(current_user)):
    return [t.describe() for t in get_registry().all()]


@router.get("/audit", response_model=Page)
def audit_log(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(AuditEvent).where(AuditEvent.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)).all()
    return Page(items=[AuditOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)
