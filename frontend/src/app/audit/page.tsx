"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function AuditPage() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => api.audit(100), refetchInterval: 5000 });
  return (
    <main className="panel p-4">
      <h1 className="mb-1 text-lg font-semibold">Security &amp; audit history</h1>
      <p className="muted mb-3 text-sm">{q.data?.total ?? 0} recorded events (newest first). Tool arguments are logged; file contents and secrets are not.</p>
      {q.error && <p role="alert" style={{ color: "var(--danger)" }}>{q.error.message}</p>}
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="muted text-xs uppercase"><tr><th className="p-2">Time</th><th>Action</th><th>Outcome</th><th>Detail</th></tr></thead>
        <tbody>{q.data?.items.map((e) => (
          <tr key={e.id} className="border-t align-top" style={{ borderColor: "var(--border)" }}>
            <td className="p-2 whitespace-nowrap">{new Date(e.created_at).toLocaleString()}</td><td>{e.action}</td>
            <td style={{ color: e.outcome === "ok" ? "var(--ok)" : "var(--danger)" }}>{e.outcome}</td>
            <td className="muted max-w-md truncate text-xs" title={JSON.stringify(e.detail)}>{JSON.stringify(e.detail)}</td>
          </tr>))}</tbody></table></div>
    </main>
  );
}
