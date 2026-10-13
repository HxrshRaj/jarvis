"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api, TERMINAL } from "@/lib/api";
import { Orb, type OrbState } from "@/components/Orb";
import { StatusBadge, TaskPanel, useTask } from "@/components/TaskPanel";
import { PLANNED } from "@/components/Shell";

const QUICK = ["list the files in the project", "run the tests", "what is the mean of 4, 8, 15, 16, 23, 42", "show my recent tasks"];

export default function CommandCenter() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [conv, setConv] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const task = useTask(taskId).data;
  const active = !!task && !TERMINAL.includes(task.status);

  const send = useMutation({
    mutationFn: (m: string) => api.chat(m, conv ?? undefined),
    onSuccess: (r) => { setConv(r.conversation_id); setTaskId(r.task_id); setText(""); qc.invalidateQueries({ queryKey: ["tasks"] }); },
  });
  const messages = useQuery({
    queryKey: ["conversation", conv, task?.status], enabled: !!conv, queryFn: () => api.conversation(conv!),
  });
  const recent = useQuery({ queryKey: ["tasks", "recent"], queryFn: () => api.tasks(6), refetchInterval: 4000 });
  const ready = useQuery({ queryKey: ["ready"], queryFn: api.ready, refetchInterval: 15000 });
  const tools = useQuery({ queryKey: ["tools"], queryFn: api.tools });

  const orb: OrbState = task?.status === "awaiting_approval" ? "waiting" : active || send.isPending ? "working" : task?.status === "failed" ? "error" : "idle";

  return (
    <main className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <div className="space-y-4">
        <section className="panel flex flex-col items-center gap-4 p-6">
          <Orb state={orb} />
          <form className="flex w-full gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send.mutate(text.trim()); }}>
            <label className="sr-only" htmlFor="cmd">Command</label>
            <input id="cmd" className="input" placeholder="Ask JARVIS or give it a task…" value={text} maxLength={8000} onChange={(e) => setText(e.target.value)} />
            <button className="btn btn-primary" disabled={send.isPending || !text.trim()}>Send</button>
          </form>
          {send.error && <p role="alert" className="text-sm" style={{ color: "var(--danger)" }}>{send.error.message}</p>}
          <div className="flex flex-wrap justify-center gap-2" aria-label="Quick actions">
            {QUICK.map((q) => <button key={q} className="btn" disabled={send.isPending} onClick={() => send.mutate(q)}>{q}</button>)}
          </div>
          <p className="muted text-xs">Voice input: not implemented yet (planned, push-to-talk first).</p>
        </section>

        <section className="panel p-4" aria-label="Conversation">
          <h2 className="mb-2 text-sm font-semibold">Conversation</h2>
          {!messages.data?.messages.length && <p className="muted text-sm">Nothing yet. Try a quick action above.</p>}
          <ul className="space-y-3">
            {messages.data?.messages.map((m) => (
              <li key={m.id} className={m.role === "user" ? "text-right" : ""}>
                <div className="inline-block max-w-full rounded-xl border px-3 py-2 text-left text-sm whitespace-pre-wrap"
                  style={{ borderColor: "var(--border)", background: m.role === "user" ? "rgba(59,130,246,.15)" : "transparent" }}>{m.content}</div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <aside className="space-y-4">
        <section className="panel p-4" aria-label="Live task">
          <h2 className="mb-2 text-sm font-semibold">Live task</h2>
          {taskId ? <TaskPanel taskId={taskId} /> : <p className="muted text-sm">No active task.</p>}
        </section>

        <section className="panel p-4" aria-label="Recent tasks">
          <div className="mb-2 flex justify-between"><h2 className="text-sm font-semibold">Recent tasks</h2><Link className="muted text-xs underline" href="/tasks">All</Link></div>
          <ul className="space-y-1.5">
            {recent.data?.items.map((t) => (
              <li key={t.id}><button className="flex w-full items-center justify-between gap-2 text-left text-sm" onClick={() => { setTaskId(t.id); }}>
                <span className="truncate">{t.request}</span><StatusBadge status={t.status} /></button></li>
            ))}
            {recent.data?.items.length === 0 && <li className="muted text-sm">No tasks yet.</li>}
          </ul>
        </section>

        <section className="panel space-y-1 p-4 text-sm" aria-label="System status">
          <h2 className="mb-1 text-sm font-semibold">System &amp; privacy</h2>
          <p>Backend: {ready.isError ? <b style={{ color: "var(--danger)" }}>unreachable</b> : ready.data ? <b style={{ color: "var(--ok)" }}>online</b> : "checking…"}</p>
          {ready.data && <>
            <p>Database: {ready.data.database ? "ok" : "down"}</p>
            <p>Language model: {ready.data.llm_is_real ? ready.data.llm_provider : <span style={{ color: "var(--amber)" }}>none configured (offline mode)</span>}</p>
            <p className="muted break-all text-xs">Tool workspace: {ready.data.workspace}</p>
          </>}
          <p className="muted text-xs">Tools: {tools.data?.filter((t) => t.available).length ?? "…"} available · microphone, screen and browser access: off (not implemented)</p>
        </section>

        <section className="panel p-4 text-xs" aria-label="Roadmap">
          <h2 className="mb-1 text-sm font-semibold">Not built yet</h2>
          <p className="muted">{PLANNED.join(" · ")}</p>
        </section>
      </aside>
    </main>
  );
}
