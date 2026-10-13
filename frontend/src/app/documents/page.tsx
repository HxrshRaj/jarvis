"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

export default function DocumentWorkspace() {
  const qc = useQueryClient();
  const [sel, setSel] = useState<string | null>(null);
  const docs = useQuery({ queryKey: ["documents"], queryFn: api.documents });
  const text = useQuery({ queryKey: ["doctext", sel], enabled: !!sel, queryFn: () => api.documentText(sel!) });
  const reindex = useMutation({ mutationFn: (id: string) => api.reindexDocument(id), onSuccess: () => { qc.invalidateQueries({ queryKey: ["documents"] }); qc.invalidateQueries({ queryKey: ["doctext", sel] }); } });
  return (
    <main className="grid gap-4 lg:grid-cols-[1fr_2fr]">
      <section className="panel p-4">
        <h1 className="mb-2 text-lg font-semibold">Document workspace</h1>
        <ul className="space-y-1.5">{docs.data?.items.map((d) => (
          <li key={d.id}><button className="w-full rounded-lg border p-2 text-left text-sm" style={{ borderColor: "var(--border)" }} onClick={() => setSel(d.id)}>
            <span className="block truncate">{d.filename}</span><span className="muted text-xs">{d.status} · {d.n_chunks} chunks</span></button></li>))}
          {docs.data?.items.length === 0 && <li className="muted text-sm">Upload documents in the Knowledge Base first.</li>}</ul>
      </section>
      <section className="panel space-y-2 p-4" aria-label="Extracted text">
        {!sel && <p className="muted text-sm">Select a document to inspect exactly what text was extracted and indexed.</p>}
        {text.error && <p role="alert" style={{ color: "var(--danger)" }}>{text.error.message}</p>}
        {text.data && <>
          <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-sm font-semibold">{text.data.filename}</h2>
            <button className="btn" disabled={reindex.isPending} onClick={() => reindex.mutate(text.data!.id)}>Re-index</button></div>
          <p className="muted text-xs">{text.data.mime} · {text.data.n_chunks} chunks · status {text.data.status}{text.data.truncated ? " · showing first 50,000 characters" : ""}</p>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap text-xs">{text.data.text}</pre>
        </>}
      </section>
    </main>
  );
}
