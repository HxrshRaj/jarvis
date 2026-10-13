"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { StatusBadge, TaskPanel } from "@/components/TaskPanel";

export default function TasksPage() {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["tasks", "page", offset], queryFn: () => api.tasks(15, offset), refetchInterval: 4000 });
  return (
    <main className="grid gap-4 lg:grid-cols-2">
      <section className="panel p-4">
        <h1 className="mb-3 text-lg font-semibold">Tasks &amp; workflows</h1>
        {q.error && <p role="alert" style={{ color: "var(--danger)" }}>{q.error.message}</p>}
        <ul className="space-y-1.5">
          {q.data?.items.map((t) => (
            <li key={t.id}><button className="flex w-full items-center justify-between gap-2 rounded-lg border p-2 text-left text-sm" style={{ borderColor: "var(--border)" }} onClick={() => setSelected(t.id)}>
              <span className="truncate">{t.request}<span className="muted block text-xs">{new Date(t.created_at).toLocaleString()} · {t.route}</span></span><StatusBadge status={t.status} /></button></li>
          ))}
        </ul>
        {q.data?.items.length === 0 && <p className="muted text-sm">No tasks yet.</p>}
        <div className="mt-3 flex items-center gap-2">
          <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 15))}>Previous</button>
          <button className="btn" disabled={!q.data || offset + 15 >= q.data.total} onClick={() => setOffset(offset + 15)}>Next</button>
          <span className="muted text-xs">{q.data?.total ?? 0} total</span>
        </div>
      </section>
      <section className="panel p-4">{selected ? <TaskPanel taskId={selected} /> : <p className="muted text-sm">Select a task to inspect its plan, tool calls, outputs and verification.</p>}</section>
    </main>
  );
}
