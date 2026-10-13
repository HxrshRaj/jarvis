"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

const pct = (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(0)}%` : "n/a");

export default function EvalsPage() {
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: ["evals"], queryFn: api.evals });
  const ml = useQuery({ queryKey: ["mlreport"], queryFn: api.mlReport });
  const run = useMutation({ mutationFn: api.runEvals, onSuccess: () => qc.invalidateQueries({ queryKey: ["evals"] }) });
  const latest = runs.data?.runs[0];
  const r = latest?.results as Record<string, Record<string, unknown>> | undefined;
  const rows: [string, string][] = r ? [
    ["Routing accuracy (rules → hybrid)", `${pct(r.routing.rules_accuracy)} → ${pct(r.routing.hybrid_accuracy)}`],
    ["Tool selection / arguments", `${pct(r.tool_selection.selection_accuracy)} / ${pct(r.tool_selection.argument_accuracy)}`],
    ["Permission enforcement", pct(r.permission_enforcement.enforcement_accuracy)],
    ["RAG recall@1 / recall@3 / MRR", `${pct(r.rag_retrieval.recall_at_1)} / ${pct(r.rag_retrieval.recall_at_3)} / ${String(r.rag_retrieval.mrr)}`],
    ["Memory top-1 relevance", pct(r.memory_relevance.top1_accuracy)],
    ["Citation validator", pct(r.citations_and_termination.citation_validator_accuracy)],
    ["Planner provider-failure fallback", `${String(r.provider_failure_planning.fell_back_safely)}/${String(r.provider_failure_planning.cases)}`],
  ] : [];
  const failures = r ? [r.tool_selection, r.rag_retrieval, r.memory_relevance, r.permission_enforcement].flatMap((x) => (x.failures as unknown[]) ?? []) : [];
  const d = ml.data as Record<string, any> | undefined; // eslint-disable-line @typescript-eslint/no-explicit-any

  return (
    <main className="grid gap-4 lg:grid-cols-2">
      <section className="panel space-y-2 p-4 text-sm">
        <div className="flex items-center justify-between"><h1 className="text-lg font-semibold">Evaluation &amp; diagnostics</h1>
          <button className="btn btn-primary" disabled={run.isPending} onClick={() => run.mutate()}>{run.isPending ? "Running…" : "Run deterministic suite"}</button></div>
        <p className="muted text-xs">Deterministic checks only (no network, no LLM). Each run stores its config and prompt versions. Live-model evaluations are not run here.</p>
        {run.error && <p role="alert" style={{ color: "var(--danger)" }}>{run.error.message}</p>}
        {!latest && <p className="muted">No runs yet.</p>}
        {latest && <>
          <p className="muted text-xs">Run {latest.id.slice(0, 8)} · {latest.created_at && new Date(latest.created_at).toLocaleString()} · eval v{String(latest.config.eval_version)}</p>
          <table className="w-full text-left text-xs"><tbody>{rows.map(([k, v]) => <tr key={k} className="border-t" style={{ borderColor: "var(--border)" }}><td className="py-1">{k}</td><td className="font-semibold">{v}</td></tr>)}</tbody></table>
          {failures.length > 0 && <details><summary className="cursor-pointer text-xs" style={{ color: "var(--amber)" }}>{failures.length} known failure(s)</summary>
            <pre className="max-h-48 overflow-auto text-xs">{JSON.stringify(failures, null, 2)}</pre></details>}
        </>}
      </section>
      <section className="panel space-y-2 p-4 text-sm">
        <h2 className="text-sm font-semibold">Router experiment (scikit-learn &amp; PyTorch)</h2>
        {ml.error && <p className="muted text-xs">{ml.error.message}</p>}
        {d && <>
          <p className="muted text-xs">Synthetic dataset: {d.dataset.train} train / {d.dataset.val} val / {d.dataset.test} held-out / {d.dataset.natural_test} hand-written. Numbers are macro-F1.</p>
          <table className="w-full text-left text-xs"><thead className="muted"><tr><th>Model</th><th>Held-out templates</th><th>Hand-written</th></tr></thead><tbody>
            <tr><td>Rules baseline</td><td>{d.rules.test.macro_f1}</td><td>{d.rules.natural_test.macro_f1}</td></tr>
            <tr><td>scikit-learn</td><td>{d.sklearn.test.macro_f1}</td><td>{d.sklearn.natural_test.macro_f1}</td></tr>
            <tr><td>PyTorch (5 seeds)</td><td>{d.torch.test_macro_f1.mean}±{d.torch.test_macro_f1.std}</td><td>{d.torch.natural_macro_f1.mean}±{d.torch.natural_macro_f1.std}</td></tr>
            <tr><td>Hybrid (model, rules fallback)</td><td>{d.hybrid.test.macro_f1}</td><td>{d.hybrid.natural_test.macro_f1}</td></tr></tbody></table>
          <p className="muted text-xs">Grouped CV: rules {d.rules.grouped_cv_macro_f1.mean} vs scikit-learn {d.sklearn.grouped_cv_macro_f1.mean}. The held-out column is noisy (about 16 templates). The classifier never authorises actions; it only labels routes.</p>
        </>}
      </section>
    </main>
  );
}
