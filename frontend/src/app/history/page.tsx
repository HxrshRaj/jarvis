"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

export default function HistoryPage() {
  const qc = useQueryClient();
  const [sel, setSel] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["conversations"], queryFn: () => api.conversations() });
  const detail = useQuery({ queryKey: ["conversation", sel, "history"], enabled: !!sel, queryFn: () => api.conversation(sel!) });
  const del = useMutation({ mutationFn: (id: string) => api.deleteConversation(id), onSuccess: () => { setSel(null); qc.invalidateQueries({ queryKey: ["conversations"] }); } });
  return (
    <main className="grid gap-4 lg:grid-cols-2">
      <section className="panel p-4">
        <h1 className="mb-1 text-lg font-semibold">Conversation history</h1>
        <p className="muted mb-3 text-xs">Conversation history is separate from long-term memory: deleting a conversation never touches saved memories.</p>
        {list.error && <p role="alert" style={{ color: "var(--danger)" }}>{list.error.message}</p>}
        <ul className="space-y-1.5">
          {list.data?.items.map((c) => (
            <li key={c.id}><button className="w-full rounded-lg border p-2 text-left text-sm" style={{ borderColor: "var(--border)" }} onClick={() => setSel(c.id)}>
              <span className="block truncate">{c.title}</span><span className="muted text-xs">{new Date(c.created_at).toLocaleString()}</span></button></li>
          ))}
          {list.data?.items.length === 0 && <li className="muted text-sm">No conversations yet.</li>}
        </ul>
      </section>
      <section className="panel p-4" aria-label="Messages">
        {!sel && <p className="muted text-sm">Select a conversation.</p>}
        {detail.data && <>
          <div className="mb-2 flex justify-between"><h2 className="truncate text-sm font-semibold">{detail.data.title}</h2>
            <button className="btn" disabled={del.isPending} onClick={() => { if (confirm("Delete this conversation? Task history is kept.")) del.mutate(sel!); }}>Delete</button></div>
          <ul className="space-y-2">{detail.data.messages.map((m) => (
            <li key={m.id} className="text-sm"><b className="muted text-xs uppercase">{m.role}</b><div className="whitespace-pre-wrap">{m.content}</div></li>))}</ul>
        </>}
      </section>
    </main>
  );
}
