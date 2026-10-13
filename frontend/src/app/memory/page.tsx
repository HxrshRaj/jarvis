"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

export default function MemoryPage() {
  const qc = useQueryClient();
  const [content, setContent] = useState("");
  const [kind, setKind] = useState("fact");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["memories"] });
  const mems = useQuery({ queryKey: ["memories"], queryFn: api.memories });
  const setting = useQuery({ queryKey: ["memsetting"], queryFn: api.memorySetting });
  const add = useMutation({ mutationFn: () => api.addMemory(content, kind), onSuccess: () => { setContent(""); refresh(); } });
  const edit = useMutation({ mutationFn: (id: string) => api.editMemory(id, draft), onSuccess: () => { setEditing(null); refresh(); } });
  const del = useMutation({ mutationFn: (id: string) => api.deleteMemory(id), onSuccess: refresh });
  // `pending` flips synchronously in the click handler (instant feedback); the server value takes over once settled.
  const [pending, setPending] = useState<boolean | null>(null);
  const toggle = useMutation({
    mutationFn: (v: boolean) => api.setMemorySetting(v),
    onSettled: async () => { await qc.invalidateQueries({ queryKey: ["memsetting"] }); setPending(null); },
  });
  const exp = useMutation({
    mutationFn: api.exportMemories,
    onSuccess: (d) => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: "jarvis-memories.json" });
      a.click(); URL.revokeObjectURL(url);
    },
  });
  const enabled = pending ?? setting.data?.enabled ?? true;

  return (
    <main className="space-y-4">
      <section className="panel space-y-3 p-4">
        <h1 className="text-lg font-semibold">Memory &amp; preferences</h1>
        <p className="muted text-xs">Only things you choose to save live here. Passwords, API keys, tokens and similar identifiers are refused automatically. Chat history is stored separately and does not become memory.</p>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={enabled} onChange={(e) => { setPending(e.target.checked); toggle.mutate(e.target.checked); }} /> Persistent memory enabled</label>
        {!enabled && <p className="text-xs" style={{ color: "var(--amber)" }}>Memory is off: JARVIS will not save or recall memories. Existing ones stay visible and deletable below.</p>}
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (content.trim()) add.mutate(); }}>
          <label className="sr-only" htmlFor="mem">New memory</label>
          <input id="mem" className="input min-w-0 flex-1" placeholder="e.g. I prefer concise answers" value={content} maxLength={2000} onChange={(e) => setContent(e.target.value)} />
          <select className="input w-auto" aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}>{["fact", "preference", "project", "summary"].map((k) => <option key={k}>{k}</option>)}</select>
          <button className="btn btn-primary" disabled={!enabled || add.isPending || !content.trim()}>Save</button>
        </form>
        {add.error && <p role="alert" className="text-sm" style={{ color: "var(--danger)" }}>{add.error.message}</p>}
      </section>
      <section className="panel p-4" aria-label="Saved memories">
        <div className="mb-2 flex items-center justify-between"><h2 className="text-sm font-semibold">{mems.data?.total ?? 0} saved</h2>
          <button className="btn" disabled={exp.isPending} onClick={() => exp.mutate()}>Export JSON</button></div>
        <ul className="space-y-2">{mems.data?.items.map((m) => (
          <li key={m.id} className="rounded-lg border p-2 text-sm" style={{ borderColor: "var(--border)" }}>
            <span className="muted text-xs uppercase">{m.kind}</span>
            {editing === m.id ? (
              <div className="mt-1 flex gap-2"><input className="input" aria-label="Edit memory" value={draft} onChange={(e) => setDraft(e.target.value)} />
                <button className="btn btn-primary" onClick={() => edit.mutate(m.id)}>Save</button><button className="btn" onClick={() => setEditing(null)}>Cancel</button></div>
            ) : (
              <div className="flex items-start justify-between gap-2"><span className="whitespace-pre-wrap">{m.content}</span>
                <span className="flex shrink-0 gap-1"><button className="btn" onClick={() => { setEditing(m.id); setDraft(m.content); }}>Edit</button>
                  <button className="btn" onClick={() => { if (confirm("Delete this memory?")) del.mutate(m.id); }}>Delete</button></span></div>
            )}
          </li>))}
          {mems.data?.items.length === 0 && <li className="muted text-sm">No memories saved.</li>}</ul>
        {(edit.error || del.error) && <p role="alert" className="mt-2 text-sm" style={{ color: "var(--danger)" }}>{((edit.error ?? del.error) as Error).message}</p>}
      </section>
    </main>
  );
}
