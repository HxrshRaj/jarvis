"""Memory, documents (RAG), vision, voice, workspace browsing, usage and capability endpoints."""
from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import get_settings
from app.db import get_db
from app.llm.providers import LLMError, ProviderUnavailable, get_provider
from app.models import Document, LLMUsage, Memory, User
from app.schemas import Page
from app.services import knowledge
from app.services.engine import audit
from app.tools.registry import ToolError
from app.tools.sandbox import SENSITIVE_DIRS, resolve_in_workspace

router = APIRouter(prefix="/api/v1")


def _k(e: knowledge.KnowledgeError):
    return HTTPException(e.status, str(e))


# ---- memory ---------------------------------------------------------------------------------------
class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    kind: str = "fact"


class MemoryPatch(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    kind: str | None = None


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    content: str
    created_at: str | None = None


def _mem(m: Memory) -> dict:
    return {"id": m.id, "kind": m.kind, "content": m.content, "created_at": m.created_at.isoformat(), "updated_at": m.updated_at.isoformat()}


class MemorySettings(BaseModel):
    enabled: bool


@router.get("/settings/memory")
def get_memory_settings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"enabled": knowledge.memory_enabled(db, user.id)}


@router.put("/settings/memory")
def put_memory_settings(body: MemorySettings, user: User = Depends(current_user), db: Session = Depends(get_db)):
    knowledge.set_memory_enabled(db, user.id, body.enabled)
    audit(db, user.id, "memory.toggle", "", enabled=body.enabled)
    db.commit()
    return {"enabled": body.enabled}


@router.get("/memories", response_model=Page)
def list_memories(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), kind: str | None = None,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Memory).where(Memory.user_id == user.id)
    if kind:
        q = q.where(Memory.kind == kind)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Memory.created_at.desc()).limit(limit).offset(offset)).all()
    return Page(items=[_mem(m) for m in rows], total=total, limit=limit, offset=offset)


@router.post("/memories", status_code=201)
def create_memory(body: MemoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        m = knowledge.save_memory(db, user.id, body.content, body.kind)
    except knowledge.KnowledgeError as e:
        audit(db, user.id, "memory.save", "", "denied", reason=str(e)[:80])
        db.commit()
        raise _k(e) from None
    audit(db, user.id, "memory.save", m.id, kind=m.kind)
    db.commit()
    return _mem(m)


def _own_memory(db: Session, user: User, mem_id: str) -> Memory:
    m = db.get(Memory, mem_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(404, "Memory not found")
    return m


@router.patch("/memories/{mem_id}")
def edit_memory(mem_id: str, body: MemoryPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own_memory(db, user, mem_id)
    if body.content is not None:
        if knowledge.contains_secret(body.content):
            raise HTTPException(422, "This looks like a secret or sensitive identifier; it was not saved.")
        m.content, m.embedding = body.content.strip(), knowledge.embed(body.content)
    if body.kind is not None:
        if body.kind not in knowledge.MEMORY_KINDS:
            raise HTTPException(422, "invalid kind")
        m.kind = body.kind
    audit(db, user.id, "memory.edit", m.id)
    db.commit()
    return _mem(m)


@router.delete("/memories/{mem_id}", status_code=204)
def delete_memory(mem_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own_memory(db, user, mem_id)
    db.delete(m)
    audit(db, user.id, "memory.delete", mem_id)
    db.commit()


@router.get("/memories-export")
def export_memories(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at)).all()
    audit(db, user.id, "memory.export", "", count=len(rows))
    db.commit()
    return {"memories": [_mem(m) for m in rows]}


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    k: int = Field(default=5, ge=1, le=20)


@router.post("/memories/search")
def search_memories(body: SearchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"results": [{**_mem(m), "score": s} for m, s in knowledge.search_memories(db, user.id, body.query, body.k)]}


# ---- documents ------------------------------------------------------------------------------------
def _doc(d: Document) -> dict:
    return {"id": d.id, "filename": d.filename, "mime": d.mime, "size_bytes": d.size_bytes, "status": d.status,
            "error": d.error, "n_chunks": d.n_chunks, "created_at": d.created_at.isoformat()}


@router.post("/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = await file.read(knowledge.MAX_UPLOAD_BYTES + 1)
    try:
        d = knowledge.ingest_document(db, user.id, file.filename or "document", data)
    except knowledge.KnowledgeError as e:
        db.rollback()
        audit(db, user.id, "document.upload", file.filename or "", "denied", reason=str(e)[:100])
        db.commit()
        raise _k(e) from None
    audit(db, user.id, "document.upload", d.id, filename=d.filename, chunks=d.n_chunks)
    db.commit()
    return _doc(d)


@router.get("/documents", response_model=Page)
def list_documents(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Document).where(Document.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Document.created_at.desc()).limit(limit).offset(offset)).all()
    return Page(items=[_doc(d) for d in rows], total=total, limit=limit, offset=offset)


def _own_doc(db: Session, user: User, doc_id: str) -> Document:
    d = db.get(Document, doc_id)
    if d is None or d.user_id != user.id:
        raise HTTPException(404, "Document not found")
    return d


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _own_doc(db, user, doc_id)
    db.delete(d)
    audit(db, user.id, "document.delete", doc_id)
    db.commit()


@router.post("/documents/{doc_id}/reindex")
def reindex(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _own_doc(db, user, doc_id)
    knowledge.reindex_document(db, d)
    audit(db, user.id, "document.reindex", doc_id)
    db.commit()
    return _doc(d)


@router.post("/documents/search")
def search_docs(body: SearchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"hits": knowledge.search_documents(db, user.id, body.query, body.k)}


# ---- vision ("Look at This") ------------------------------------------------------------------------
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _image_mime(b: bytes) -> str | None:
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if b.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if b[:4] == b"GIF8":
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/vision/analyze")
async def analyze_image(image: UploadFile = File(...), question: str = Form("Describe what is shown and note any errors."),
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Explicit-upload only. The image is sent to the configured provider and is never stored."""
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "image exceeds 5 MB")
    mime = _image_mime(data)
    if mime is None:
        raise HTTPException(422, "unsupported image type (PNG, JPEG, GIF or WebP only)")
    if not 1 <= len(question) <= 1000:
        raise HTTPException(422, "question must be 1-1000 characters")
    provider = get_provider()
    from app.llm.providers import usage_context

    usage_context.set({"user_id": user.id, "purpose": "vision"})
    try:
        answer = provider.describe_image(data, mime, question)
    except ProviderUnavailable as e:
        raise HTTPException(503, str(e)) from None
    except LLMError as e:
        audit(db, user.id, "vision.analyze", "", "error", error=str(e)[:100])
        db.commit()
        raise HTTPException(502, str(e)) from None
    audit(db, user.id, "vision.analyze", "", bytes=len(data), mime=mime)  # metadata only, never the image
    db.commit()
    return {"answer": answer, "stored": False, "note": "Answer is model-generated from the image; verify important details."}


# ---- voice ----------------------------------------------------------------------------------------
MAX_AUDIO_BYTES = 10 * 1024 * 1024


@router.post("/voice/transcribe")
async def transcribe(audio: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Push-to-talk upload. Only called when the user explicitly records; audio is not stored."""
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "audio exceeds 10 MB")
    ctype = (audio.content_type or "").split(";")[0]
    if not data or not (ctype.startswith("audio/") or ctype == "video/webm"):
        raise HTTPException(422, "expected a non-empty audio recording")
    from app.llm.providers import usage_context

    usage_context.set({"user_id": user.id, "purpose": "stt"})
    try:
        text = get_provider().transcribe(data, audio.filename or "speech.webm", ctype)
    except ProviderUnavailable as e:
        raise HTTPException(503, str(e)) from None
    except LLMError as e:
        raise HTTPException(502, str(e)) from None
    audit(db, user.id, "voice.transcribe", "", bytes=len(data))
    db.commit()
    return {"text": text}


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/voice/speak")
def speak(body: SpeakIn, user: User = Depends(current_user)):
    try:
        audio, ctype = get_provider().speak(body.text)
    except ProviderUnavailable as e:
        raise HTTPException(503, str(e)) from None
    except LLMError as e:
        raise HTTPException(502, str(e)) from None
    return Response(audio, media_type=ctype)


# ---- capabilities / provider view / usage -----------------------------------------------------------
@router.get("/capabilities")
def capabilities(_: User = Depends(current_user)):
    p, s = get_provider(), get_settings()
    return {
        "llm": p.is_real, "vision": bool(p.supports_vision), "speech_to_text": bool(p.is_real and getattr(p, "stt_model", "")),
        "text_to_speech": bool(p.is_real and getattr(p, "tts_model", "")), "router": s.router,
        "browser_tts_fallback": True,  # the UI can use the browser's local speechSynthesis
    }


@router.get("/settings/provider")
def provider_view(_: User = Depends(current_user)):
    """Read-only. Secrets are never returned; configuration lives in environment variables."""
    s = get_settings()
    host = urlparse(s.llm_base_url).netloc if s.llm_provider == "openai_compat" else None
    return {"provider": s.llm_provider, "endpoint_host": host, "model": s.llm_model if s.llm_provider != "mock" else None,
            "vision_model": s.llm_vision_model or None, "stt_model": s.llm_stt_model or None,
            "tts_model": s.llm_tts_model or None, "api_key_configured": bool(s.llm_api_key),
            "how_to_change": "Set JARVIS_LLM_* environment variables and restart the backend."}


@router.get("/usage")
def usage(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings()
    rows = db.execute(select(LLMUsage.provider, LLMUsage.model, LLMUsage.purpose, func.count(), func.sum(LLMUsage.prompt_tokens),
                             func.sum(LLMUsage.completion_tokens)).where(LLMUsage.user_id == user.id)
                      .group_by(LLMUsage.provider, LLMUsage.model, LLMUsage.purpose)).all()
    priced = s.price_prompt_per_mtok > 0 or s.price_completion_per_mtok > 0
    out = []
    for prov, model, purpose, calls, pt, ct in rows:
        pt, ct = int(pt or 0), int(ct or 0)
        est = (pt * s.price_prompt_per_mtok + ct * s.price_completion_per_mtok) / 1e6 if priced else None
        out.append({"provider": prov, "model": model, "purpose": purpose, "calls": calls, "prompt_tokens": pt,
                    "completion_tokens": ct, "estimated_cost_usd": est})
    return {"usage": out, "note": "Token counts are reported by the provider (measured). Cost is an ESTIMATE from configured "
                                  "pricing" + ("" if priced else "; pricing is not configured so no estimate is shown") + "."}


# ---- workspace browsing (same sandbox as the tools) ----------------------------------------------------
@router.get("/workspace/list")
def workspace_list(path: str = ".", _: User = Depends(current_user)):
    s = get_settings()
    try:
        target = resolve_in_workspace(s.workspace_root, path)
    except ToolError as e:
        raise HTTPException(403, str(e)) from None
    if not target.is_dir():
        raise HTTPException(404, "not a directory")
    items = [{"name": p.name, "is_dir": p.is_dir(), "size": None if p.is_dir() else p.stat().st_size}
             for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())) if p.name.lower() not in SENSITIVE_DIRS]
    return {"path": path, "entries": items[:300]}


@router.get("/workspace/file")
def workspace_file(path: str, _: User = Depends(current_user)):
    s = get_settings()
    try:
        target = resolve_in_workspace(s.workspace_root, path)
    except ToolError as e:
        raise HTTPException(403, str(e)) from None
    if not target.is_file():
        raise HTTPException(404, "file not found")
    raw = target.read_bytes()[: s.max_file_bytes + 1]
    if b"\x00" in raw[:1024]:
        raise HTTPException(415, "binary files are not supported")
    return {"path": path, "content": raw[: s.max_file_bytes].decode("utf-8", errors="replace"), "truncated": len(raw) > s.max_file_bytes}


# ---- evaluations ----------------------------------------------------------------------------------------
@router.post("/evals/run")
def run_evals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Runs the deterministic suite (no network, no LLM). Results are stored and listed under /evals."""
    from app.services import evals

    out = evals.run_and_store(db)
    audit(db, user.id, "eval.run", out["id"])
    db.commit()
    return out


@router.get("/evals")
def list_evals(limit: int = Query(10, ge=1, le=50), _: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.models import EvalRun

    rows = db.scalars(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit)).all()
    return {"runs": [{"id": r.id, "name": r.name, "created_at": r.created_at.isoformat(), "config": r.config, "results": r.results}
                     for r in rows]}


@router.get("/ml/report")
def ml_report(_: User = Depends(current_user)):
    """The committed output of `python -m ml.train` (router experiment)."""
    import json as _json

    from app.ml.router import ARTIFACT_DIR

    path = ARTIFACT_DIR.parent / "reports" / "results.json"
    if not path.exists():
        raise HTTPException(404, "No ML report found. Run `python -m ml.train` in backend/.")
    return _json.loads(path.read_text(encoding="utf-8"))


@router.get("/documents/{doc_id}/text")
def document_text(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Extracted text (what the indexer saw). Capped so a huge document cannot flood the browser."""
    d = _own_doc(db, user, doc_id)
    text = d.raw_text or ""
    return {**_doc(d), "text": text[:50_000], "truncated": len(text) > 50_000}
