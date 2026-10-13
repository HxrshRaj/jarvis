# Memory & RAG

## Separation of state
Conversation history (`messages`) ≠ long-term memory (`memories`) ≠ documents (`documents`/`document_chunks`) ≠ temporary task
state. Deleting a conversation never deletes memories, and chatting never creates memories: only an explicit save does.

## Memory
- API: `GET/POST /memories`, `PATCH/DELETE /memories/{id}`, `GET /memories-export`, `POST /memories/search`, `GET/PUT /settings/memory`.
- From chat: "remember that …" plans a `save_memory` step that **requires approval**.
- Secret-shaped content (passwords, API keys, tokens, private keys, SSN/card shapes) is refused at plan time, in the API and in the tool.
- Disable switch: when off, saving is refused (409), search returns nothing, existing items stay visible/deletable.
- Retrieval is the same hybrid ranker as documents, scoped to the user. Known miss in the eval suite: "do I have any food
  allergies" does not retrieve "I am allergic to peanuts" (a semantic gap the hashed embedder cannot bridge).

## Documents
- Upload PDF/TXT/MD/CSV/LOG/RST (≤5 MB). Text is extracted with `pypdf` (scanned PDFs need OCR: not implemented), chunked
  (~800 chars, paragraph-aware, overlap), embedded, stored. Duplicates (same SHA-256) are refused per user. Ingestion is
  synchronous (fast for this size) and recorded as `status`/`error`.
- Re-index re-chunks stored text (page numbers are only known at upload). Delete removes chunks.
- Search = **BM25 (lexical) + hashed n-gram embeddings (semantic-ish), fused with reciprocal-rank fusion.** The embedding is
  deterministic and offline; it is *not* a neural embedding, and vectors are JSON arrays ranked in Python, **not pgvector**.
  A neural embedder/pgvector would plug in at `services/retrieval.py`.

## Answers with citations (LangGraph, `app/agents/rag_graph.py`)
`gate → draft → verify → (retry once) → extractive fallback`
- No retrieved evidence → says so, **never calls the model**, never answers from general knowledge.
- Real provider: draft with numbered sources; `verify_citations` requires at least one `[n]` and every `n` to exist; invalid →
  one retry with feedback → extractive excerpts. `NOT_IN_SOURCES` is honoured.
- No provider: verbatim excerpts with citations, labelled "not a generated answer".
- Evidence vs. general knowledge is separated: the answer node only sees retrieved passages.
- Verified limits: citation *validity* is checked, not whether each sentence is entailed by its source.

## Retrieval quality (deterministic eval, tiny corpus — see Evaluation page)
Recall@1/3 and MRR on 14 paraphrased questions over 6 short documents are reported by `POST /api/v1/evals/run`. They are a
regression guard on a toy corpus, not a benchmark.
