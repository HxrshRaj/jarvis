"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

export default function KnowledgePage() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const docs = useQuery({ queryKey: ["documents"], queryFn: api.documents });
  const upload = useMutation({ mutationFn: (f: File) => api.uploadDocument(f), onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }) });
  const del = useMutation({ mutationFn: (id: string) => api.deleteDocument(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }) });
  const search = useMutation({ mutationFn: (q: string) => api.searchDocuments(q) });

  return (
    <main className="grid gap-4 lg:grid-cols-2">
      <section className="panel space-y-3 p-4">
        <h1 className="text-lg font-semibold">Personal knowledge base</h1>
        <p className="muted text-xs">PDF, TXT, MD, CSV, LOG or RST up to 5 MB. Documents are private to your account and are indexed with BM25 + hashed n-gram embeddings (lexical-leaning; not neural embeddings).</p>
        <label className="block text-sm">Upload a document
          <input className="input mt-1" type="file" accept=".pdf,.txt,.md,.markdown,.csv,.log,.rst" disabled={upload.isPending}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} /></label>
        {upload.isPending && <p className="muted text-sm">Uploading and indexing…</p>}
        {upload.error && <p role="alert" className="text-sm" style={{ color: "var(--danger)" }}>{upload.error.message}</p>}
        <ul className="space-y-1.5">
          {docs.data?.items.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 rounded-lg border p-2 text-sm" style={{ borderColor: "var(--border)" }}>
              <span className="truncate">{d.filename}<span className="muted block text-xs">{d.status} · {d.n_chunks} chunks · {(d.size_bytes / 1024).toFixed(1)} KB</span></span>
              <button className="btn" disabled={del.isPending} onClick={() => { if (confirm(`Delete ${d.filename} and its index?`)) del.mutate(d.id); }}>Delete</button>
            </li>))}
          {docs.data?.items.length === 0 && <li className="muted text-sm">No documents yet.</li>}
        </ul>
      </section>
      <section className="panel space-y-3 p-4">
        <h2 className="text-sm font-semibold">Search with citations</h2>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (query.trim().length > 1) search.mutate(query.trim()); }}>
          <label className="sr-only" htmlFor="kq">Search query</label>
          <input id="kq" className="input" placeholder="Ask your documents…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button className="btn btn-primary" disabled={search.isPending}>Search</button>
        </form>
        <p className="muted text-xs">For a written answer with verified citations, ask in the Command Center: “search my documents for …”.</p>
        {search.error && <p role="alert" className="text-sm" style={{ color: "var(--danger)" }}>{search.error.message}</p>}
        {search.data && search.data.hits.length === 0 && <p className="text-sm">Nothing relevant found in your documents.</p>}
        <ol className="space-y-2">{search.data?.hits.map((h, i) => (
          <li key={h.chunk_id} className="rounded-lg border p-2 text-sm" style={{ borderColor: "var(--border)" }}>
            <b>[{i + 1}] {h.filename}</b>{h.page ? ` · p.${h.page}` : ""} <span className="muted text-xs">· chunk {h.chunk_index}</span>
            <p className="mt-1 whitespace-pre-wrap text-xs">{h.text}</p></li>))}</ol>
      </section>
    </main>
  );
}
