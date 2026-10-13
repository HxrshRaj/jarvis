"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { TaskPanel } from "@/components/TaskPanel";

const PRESETS = ["run the tests", "git status", "search for 'TODO' in the project", "list the files in the project"];

export default function CodeAssistant() {
  const qc = useQueryClient();
  const [dir, setDir] = useState(".");
  const [file, setFile] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["ws", dir], queryFn: () => api.workspaceList(dir) });
  const content = useQuery({ queryKey: ["wsfile", file], enabled: !!file, queryFn: () => api.workspaceFile(file!) });
  const run = useMutation({ mutationFn: (m: string) => api.chat(m), onSuccess: (r) => { setTaskId(r.task_id); qc.invalidateQueries({ queryKey: ["tasks"] }); } });
  const join = (name: string) => (dir === "." ? name : `${dir}/${name}`);
  const up = dir.includes("/") ? dir.slice(0, dir.lastIndexOf("/")) : ".";

  return (
    <main className="grid gap-4 lg:grid-cols-2">
      <section className="panel space-y-3 p-4">
        <h1 className="text-lg font-semibold">Code assistant</h1>
        <p className="muted text-xs">Read-only view of the approved workspace. Secrets, keys and .git are hidden and unreadable. Commands go through the task engine; test runners need your approval.</p>
        <div className="flex flex-wrap gap-2" aria-label="Preset actions">{PRESETS.map((p) => <button key={p} className="btn" disabled={run.isPending} onClick={() => run.mutate(p)}>{p}</button>)}</div>
        <div className="muted text-xs">/{dir === "." ? "" : dir} {dir !== "." && <button className="underline" onClick={() => { setDir(up); setFile(null); }}>up</button>}</div>
        {list.error && <p role="alert" style={{ color: "var(--danger)" }}>{list.error.message}</p>}
        <ul className="space-y-1 text-sm">{list.data?.entries.map((e) => (
          <li key={e.name}><button className="underline-offset-2 hover:underline" onClick={() => (e.is_dir ? (setDir(join(e.name)), setFile(null)) : setFile(join(e.name)))}>{e.is_dir ? "📁" : "📄"} {e.name}</button></li>))}</ul>
        {content.error && <p role="alert" className="text-xs" style={{ color: "var(--danger)" }}>{content.error.message}</p>}
        {content.data && <pre className="max-h-[40vh] overflow-auto rounded-lg border p-2 text-xs" style={{ borderColor: "var(--border)" }}>{content.data.content}{content.data.truncated ? "\n… truncated" : ""}</pre>}
      </section>
      <section className="panel p-4">{taskId ? <TaskPanel taskId={taskId} /> : <p className="muted text-sm">Run a preset to see the plan, approvals and verified output here.</p>}</section>
    </main>
  );
}
