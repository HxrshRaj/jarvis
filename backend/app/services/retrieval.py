"""Local retrieval primitives: hashing embeddings, chunking, BM25 and reciprocal-rank fusion.

Embeddings here are *feature-hashed bag-of-ngrams* (deterministic, offline, no model download). They capture
lexical overlap/near-matches, NOT deep semantics. The `Embedder` seam is where a neural embedding provider or
pgvector would plug in later.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

DIM = 384
SEM_GATE = 0.15  # min cosine to return a hit with zero lexical overlap (0.10 was tried: it degraded RAG ranking)
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "is", "are", "was", "it", "for", "on", "with", "as", "that",
         "this", "by", "be", "at", "from", "what", "which", "who", "how", "do", "does", "my", "me", "i"}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def _stem(t: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(t) > len(suf) + 2 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def embed(text: str) -> list[float]:
    """Signed feature hashing over stemmed unigrams, bigrams and character trigrams, L2-normalised."""
    toks = [_stem(t) for t in tokenize(text)]
    feats: Counter[str] = Counter()
    for t in toks:
        feats["u:" + t] += 1.0
        if len(t) >= 6:
            feats["p:" + t[:5]] += 0.6  # shared prefix links inflections like allergies/allergic
        padded = f"#{t}#"
        for i in range(len(padded) - 2):
            feats["c:" + padded[i : i + 3]] += 0.3
    for a, b in zip(toks, toks[1:]):
        feats[f"b:{a}_{b}"] += 0.7
    vec = [0.0] * DIM
    for f, w in feats.items():
        h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
        vec[h % DIM] += w if (h >> 40) & 1 else -w
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def chunk_text(text: str, target: int = 800, overlap: int = 120) -> list[str]:
    """Paragraph-aware chunking with character overlap. Never returns empty chunks."""
    text = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > target:  # hard-split oversized paragraphs on whitespace
            cut = p.rfind(" ", 0, target)
            cut = cut if cut > target // 2 else target
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:cut].strip())
            p = p[max(cut - overlap, 1):].strip()  # overlap keeps context across the cut
        if len(cur) + len(p) + 2 <= target:
            cur = f"{cur}\n\n{p}".strip()
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c]


@dataclass
class Candidate:
    id: str
    text: str
    embedding: list[float]


def bm25_scores(query: str, docs: list[Candidate], k1: float = 1.5, b: float = 0.75) -> dict[str, float]:
    q = [_stem(t) for t in tokenize(query)]
    toks = {d.id: [_stem(t) for t in tokenize(d.text)] for d in docs}
    n = len(docs) or 1
    avg = (sum(len(t) for t in toks.values()) / n) or 1.0
    df = Counter()
    for t in toks.values():
        df.update(set(t))
    out: dict[str, float] = {}
    for d in docs:
        tf = Counter(toks[d.id])
        s = 0.0
        for term in set(q):
            if tf[term]:
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                s += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(toks[d.id]) / avg))
        out[d.id] = s
    return out


@dataclass
class Hit:
    id: str
    score: float
    lexical: float
    semantic: float


def hybrid_search(query: str, docs: list[Candidate], k: int = 5, min_lexical: float = 0.0) -> list[Hit]:
    """Reciprocal-rank fusion of BM25 and hashed-embedding cosine. Requires some lexical *or* semantic signal."""
    if not docs or not tokenize(query):
        return []
    lex = bm25_scores(query, docs)
    qv = embed(query)
    sem = {d.id: cosine(qv, d.embedding) for d in docs}
    r_lex = {i: r for r, i in enumerate(sorted(lex, key=lex.get, reverse=True), 1)}
    r_sem = {i: r for r, i in enumerate(sorted(sem, key=sem.get, reverse=True), 1)}
    hits = []
    for d in docs:
        if lex[d.id] <= min_lexical and sem[d.id] < SEM_GATE:  # no evidence either way: don't return noise
            continue
        rrf = 1 / (60 + r_lex[d.id]) + 1 / (60 + r_sem[d.id])
        hits.append(Hit(d.id, rrf, lex[d.id], sem[d.id]))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]
