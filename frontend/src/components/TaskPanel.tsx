"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, TERMINAL, type TaskT } from "@/lib/api";

export const STATUS_COLOR: Record<string, string> = {
  succeeded: "var(--ok)", failed: "var(--danger)", cancelled: "var(--muted)",
  partially_completed: "var(--amber)", awaiting_approval: "var(--amber)", running: "var(--cyan)", pending: "var(--muted)",
  rejected: "var(--danger)", skipped: "var(--muted)",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className="rounded-full border px-2 py-0.5 text-xs" style={{ color: STATUS_COLOR[status], borderColor: STATUS_COLOR[status] }}>{status.replace("_", " ")}</span>;
}

export function useTask(id: string | null) {
  return useQuery({
    queryKey: ["task", id], enabled: !!id, queryFn: () => api.task(id!),
    refetchInterval: (q) => (q.state.data && TERMINAL.includes(q.state.data.status) ? false : 700),
  });
}

export function TaskPanel({ taskId }: { taskId: string }) {
  const qc = useQueryClient();
  const { data: task, error } = useTask(taskId);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["task", taskId] }); qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["conversation"] }); };
  const act = useMutation({
    mutationFn: (fn: () => Promise<TaskT>) => fn(), onSuccess: refresh,
  });

  if (error) return <p role="alert" style={{ color: "var(--danger)" }}>{error.message}</p>;
  if (!task) return <p className="muted text-sm">Loading task…</p>;
  const active = !TERMINAL.includes(task.status);
  const verification = task.verification as { checks?: { step: number; tool: string; passed: boolean; reason: string }[]; plan_source?: string; note?: string } | null;

  return (
    <section aria-label="Task execution" className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="truncate text-sm font-medium" title={task.request}>{task.request}</h3>
        <StatusBadge status={task.status} />
      </div>
      <p className="muted text-xs">Route: {task.route} · Plan: {verification?.plan_source ?? "…"}</p>
      {task.steps.length === 0 && !active && <p className="muted text-sm">No tools were used for this request.</p>}
      <ol className="space-y-2">
        {task.steps.map((s) => (
          <li key={s.id} className="rounded-lg border p-2 text-sm" style={{ borderColor: "var(--border)" }}>
            <div className="flex items-center justify-between gap-2">
              <span><b>{s.index + 1}.</b> {s.description} <code className="muted text-xs">({s.tool})</code></span>
              <StatusBadge status={s.status} />
            </div>
            <pre className="muted mt-1 overflow-x-auto text-xs">{JSON.stringify(s.args)}</pre>
            {s.status === "awaiting_approval" && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="text-xs" style={{ color: "var(--amber)" }}>Approval required — this has not run.</span>
                <button className="btn btn-primary" disabled={act.isPending} onClick={() => act.mutate(() => api.decide(task.id, s.id, true))}>Approve</button>
                <button className="btn" disabled={act.isPending} onClick={() => act.mutate(() => api.decide(task.id, s.id, false))}>Decline</button>
              </div>
            )}
            {s.error && <p className="mt-1 text-xs" style={{ color: "var(--danger)" }}>{s.error}</p>}
            {s.output && (
              <details className="mt-1"><summary className="muted cursor-pointer text-xs">Output</summary>
                <pre className="mt-1 max-h-48 overflow-auto text-xs">{JSON.stringify(s.output, null, 2)}</pre></details>
            )}
          </li>
        ))}
      </ol>
      {verification?.checks && (
        <div className="text-xs"><b>Verification</b>
          <ul className="mt-1 space-y-0.5">{verification.checks.map((c) => (
            <li key={c.step} style={{ color: c.passed ? "var(--ok)" : "var(--danger)" }}>{c.passed ? "✓" : "✗"} step {c.step} ({c.tool}): {c.reason}</li>))}</ul></div>
      )}
      {verification?.note && <p className="muted text-xs">{verification.note}</p>}
      {act.error && <p role="alert" className="text-xs" style={{ color: "var(--danger)" }}>{(act.error as Error).message}</p>}
      <div className="flex gap-2">
        {active && <button className="btn" disabled={act.isPending} onClick={() => act.mutate(() => api.cancel(task.id))}>Cancel task</button>}
        {(task.status === "failed" || task.status === "partially_completed") && task.steps.length > 0 && (
          <button className="btn" disabled={act.isPending} onClick={() => act.mutate(() => api.retry(task.id))}>Retry failed steps</button>)}
      </div>
    </section>
  );
}
