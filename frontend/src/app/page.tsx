"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, TERMINAL } from "@/lib/api";
import { useSpeech } from "@/lib/voice";
import { LookAtThis } from "@/components/LookAtThis";
import { Orb, type OrbState } from "@/components/Orb";
import { StatusBadge, TaskPanel, useTask } from "@/components/TaskPanel";
import { VoiceControls } from "@/components/VoiceControls";

const QUICK = ["list the files in the project", "run the tests", "what is the mean of 4, 8, 15, 16, 23, 42", "show my recent tasks"];

export default function CommandCenter() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [conv, setConv] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const task = useTask(taskId).data;
  const active = !!task && !TERMINAL.includes(task.status);

  const caps = useQuery({ queryKey: ["caps"], queryFn: api.capabilities });
  const speech = useSpeech(!!caps.data?.text_to_speech);

  const send = useMutation({
    mutationFn: (m: string) => api.chat(m, conv ?? undefined),
    onSuccess: (r) => { setConv(r.conversation_id); setTaskId(r.task_id); setText(""); qc.invalidateQueries({ queryKey: ["tasks"] }); },
  });
  const messages = useQuery({ queryKey: ["conversation", conv, task?.status], enabled: !!conv, queryFn: () => api.conversation(conv!) });
  const recent = useQuery({ queryKey: ["tasks", "recent"], queryFn: () => api.tasks(6), refetchInterval: 4000 });
  const ready = useQuery({ queryKey: ["ready"], queryFn: api.ready, refetchInterval: 15000 });
  const tools = useQuery({ queryKey: ["tools"], queryFn: api.tools });

  // Speak new assistant replies when the user opted in (never speaks history on load).
  const lastSpoken = useRef<string | null>(null);
  useEffect(() => {
    const last = [...(messages.data?.messages ?? [])].reverse().find((m) => m.role === "assistant");
    if (!last) return;
    if (lastSpoken.current === null) { lastSpoken.current = last.id; return; }
    if (last.id !== lastSpoken.current) {
      lastSpoken.current = last.id;
      if (speech.prefs.auto) void speech.speak(last.content.split("\n---\n")[0]);
    }
  }, [messages.data, speech]);

  const orb: OrbState = task?.status === "awaiting_approval" ? "waiting" : active || send.isPending ? "working" : task?.status === "failed" ? "error" : "idle";

  return (
    <main className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <div className="space-y-4">
        <section className="panel flex flex-col items-center gap-4 p-4 md:p-6">
          <Orb state={orb} />
          <form className="flex w-full gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send.mutate(text.trim()); }}>
            <label className="sr-only" htmlFor="cmd">Command</label>
            <input id="cmd" className="input" placeholder="Ask JARVIS or give it a task…" value={text} maxLength={8000} onChange={(e) => setText(e.target.value)} />
            <button className="btn btn-primary" disabled={send.isPending || !text.trim()}>Send</button>
          </form>
          {send.error && <p role="alert" className="text-sm" style={{ color: "var(--danger)" }}>{send.error.message}</p>}
          <VoiceControls canTranscribe={!!caps.data?.speech_to_text} onTranscript={(t) => send.mutate(t)}
            speech={speech.prefs} setSpeech={speech.update} speaking={speech.speaking} stopSpeaking={speech.stop} />
          <div className="flex flex-wrap justify-center gap-2" aria-label="Quick actions">
            {QUICK.map((q) => <button key={q} className="btn" disabled={send.isPending} onClick={() => send.mutate(q)}>{q}</button>)}
          </div>
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
              <li key={t.id}><button className="flex w-full items-center justify-between gap-2 text-left text-sm" onClick={() => setTaskId(t.id)}>
                <span className="truncate">{t.request}</span><StatusBadge status={t.status} /></button></li>
            ))}
            {recent.data?.items.length === 0 && <li className="muted text-sm">No tasks yet.</li>}
          </ul>
        </section>

        <LookAtThis available={!!caps.data?.vision} />

        <section className="panel space-y-1 p-4 text-sm" aria-label="System status">
          <h2 className="mb-1 text-sm font-semibold">System &amp; privacy</h2>
          <p>Backend: {ready.isError ? <b style={{ color: "var(--danger)" }}>unreachable</b> : ready.data ? <b style={{ color: "var(--ok)" }}>online</b> : "checking…"}</p>
          {ready.data && <>
            <p>Database: {ready.data.database ? "ok" : "down"}</p>
            <p>Language model: {ready.data.llm_is_real ? ready.data.llm_provider : <span style={{ color: "var(--amber)" }}>none configured (offline mode)</span>}</p>
            <p className="muted break-all text-xs">Tool workspace: {ready.data.workspace}</p>
          </>}
          <ul className="muted text-xs" aria-label="Capabilities">
            <li>Tools available: {tools.data?.filter((t) => t.available).length ?? "…"}</li>
            <li>Microphone: only while you hold the talk button · Speech-to-text: {caps.data?.speech_to_text ? "on" : "off"} · Text-to-speech: {caps.data?.text_to_speech ? "backend" : "browser-local"}</li>
            <li>Vision: {caps.data?.vision ? "on (explicit upload only)" : "off"} · Screen capture / browser automation: not implemented</li>
          </ul>
        </section>
      </aside>
    </main>
  );
}
