"""Memory + document services. Every query is filtered by user_id (workspace isolation)."""
from __future__ import annotations

import hashlib
import io
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, Memory, UserSettings
from app.services.retrieval import Candidate, chunk_text, embed, hybrid_search

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 300
MAX_CHUNKS = 2000
MEMORY_KINDS = {"preference", "project", "fact", "summary"}


class KnowledgeError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


# ---- secret detection -------------------------------------------------------------------------------
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}", re.I),
    re.compile(r"\b(password|passwd|pwd|secret|api[_ -]?key|access[_ -]?token|token)\b\s*(is|=|:)\s*\S{4,}", re.I),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN shape
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),  # card-number shape
]


def contains_secret(text: str) -> bool:
    return any(p.search(text) for p in _SECRET_PATTERNS)


# ---- memory -----------------------------------------------------------------------------------------
def memory_enabled(db: Session, user_id: str) -> bool:
    s = db.get(UserSettings, user_id)
    return True if s is None else s.memory_enabled


def set_memory_enabled(db: Session, user_id: str, enabled: bool) -> None:
    s = db.get(UserSettings, user_id)
    if s is None:
        db.add(UserSettings(user_id=user_id, memory_enabled=enabled))
    else:
        s.memory_enabled = enabled


def save_memory(db: Session, user_id: str, content: str, kind: str = "fact") -> Memory:
    content = content.strip()
    if kind not in MEMORY_KINDS:
        raise KnowledgeError(f"kind must be one of {sorted(MEMORY_KINDS)}")
    if not content or len(content) > 2000:
        raise KnowledgeError("memory must be 1-2000 characters")
    if contains_secret(content):
        raise KnowledgeError("This looks like a password, key, token or other sensitive identifier; it was not saved.")
    if not memory_enabled(db, user_id):
        raise KnowledgeError("Persistent memory is disabled in your settings.", 409)
    m = Memory(user_id=user_id, kind=kind, content=content, embedding=embed(content))
    db.add(m)
    db.flush()
    return m


def search_memories(db: Session, user_id: str, query: str, k: int = 5) -> list[tuple[Memory, float]]:
    if not memory_enabled(db, user_id):
        return []
    rows = db.scalars(select(Memory).where(Memory.user_id == user_id)).all()
    by_id = {m.id: m for m in rows}
    cands = [Candidate(m.id, m.content, m.embedding or embed(m.content)) for m in rows]
    return [(by_id[h.id], h.score) for h in hybrid_search(query, cands, k)]


# ---- documents --------------------------------------------------------------------------------------
def _extract(filename: str, data: bytes) -> tuple[str, str, list[tuple[int | None, str]]]:
    """Return (mime, full_text, [(page, text)]). Validates content by magic bytes, not just extension."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if data[:5] == b"%PDF-":
        if ext != "pdf":
            raise KnowledgeError("file content is a PDF but the extension is not .pdf")
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise KnowledgeError("encrypted PDFs are not supported")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise KnowledgeError(f"PDF has more than {MAX_PDF_PAGES} pages")
            pages = [(i + 1, (p.extract_text() or "")) for i, p in enumerate(reader.pages)]
        except KnowledgeError:
            raise
        except (PyPdfError, Exception) as e:  # malformed input is expected; never leak internals
            raise KnowledgeError(f"could not read PDF ({type(e).__name__})") from e
        text = "\n\n".join(t for _, t in pages)
        if not text.strip():
            raise KnowledgeError("no extractable text (scanned PDFs need OCR, which is not implemented)")
        return "application/pdf", text, pages
    if ext not in {"txt", "md", "markdown", "csv", "log", "rst"}:
        raise KnowledgeError("supported types: PDF, TXT, MD, CSV, LOG, RST")
    if b"\x00" in data[:4096]:
        raise KnowledgeError("binary content is not supported")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise KnowledgeError("text files must be UTF-8") from None
    if not text.strip():
        raise KnowledgeError("file is empty")
    return "text/plain", text, [(None, text)]


def _index(db: Session, doc: Document, pages: list[tuple[int | None, str]]) -> None:
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    n = 0
    for page, text in pages:
        for c in chunk_text(text):
            if n >= MAX_CHUNKS:
                raise KnowledgeError("document is too large to index")
            db.add(DocumentChunk(document_id=doc.id, user_id=doc.user_id, index=n, page=page, text=c, embedding=embed(c)))
            n += 1
    doc.n_chunks, doc.status, doc.error = n, "indexed", None


def ingest_document(db: Session, user_id: str, filename: str, data: bytes) -> Document:
    if not data:
        raise KnowledgeError("file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise KnowledgeError(f"file exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB", 413)
    safe_name = re.sub(r"[^\w.\- ]", "_", filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])[:200] or "document"
    sha = hashlib.sha256(data).hexdigest()
    if db.scalar(select(Document).where(Document.user_id == user_id, Document.sha256 == sha)):
        raise KnowledgeError("this document is already in your knowledge base", 409)
    mime, text, pages = _extract(safe_name, data)
    doc = Document(user_id=user_id, filename=safe_name, mime=mime, size_bytes=len(data), sha256=sha, raw_text=text)
    db.add(doc)
    db.flush()
    _index(db, doc, pages)
    return doc


def reindex_document(db: Session, doc: Document) -> None:
    # Page numbers are only known at upload time; re-indexing re-chunks the stored text (page=None).
    _index(db, doc, [(None, doc.raw_text or "")])


def search_documents(db: Session, user_id: str, query: str, k: int = 5) -> list[dict]:
    rows = db.execute(
        select(DocumentChunk, Document.filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.user_id == user_id, Document.user_id == user_id, Document.status == "indexed")
    ).all()
    by_id = {c.id: (c, fn) for c, fn in rows}
    cands = [Candidate(c.id, c.text, c.embedding) for c, _ in rows]
    out = []
    for h in hybrid_search(query, cands, k):
        c, fn = by_id[h.id]
        out.append({
            "chunk_id": c.id, "document_id": c.document_id, "filename": fn, "chunk_index": c.index, "page": c.page,
            "score": round(h.score, 5), "lexical": round(h.lexical, 3), "semantic": round(h.semantic, 3),
            "text": c.text[:1200],
        })
    return out
