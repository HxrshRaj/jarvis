"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function ToolsPage() {
  const q = useQuery({ queryKey: ["tools"], queryFn: api.tools });
  return (
    <main className="panel p-4">
      <h1 className="mb-1 text-lg font-semibold">Tools &amp; permissions</h1>
      <p className="muted mb-3 text-sm">Every tool call is validated and policy-checked by the task engine, never by the model. Tools marked “approval” always pause for your decision.</p>
      {q.error && <p role="alert" style={{ color: "var(--danger)" }}>{q.error.message}</p>}
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="muted text-xs uppercase"><tr><th className="p-2">Tool</th><th>Permissions</th><th>Risk</th><th>Timeout</th><th>Status</th></tr></thead>
        <tbody>{q.data?.map((t) => (
          <tr key={t.name} className="border-t" style={{ borderColor: "var(--border)" }}>
            <td className="p-2"><b>{t.name}</b><div className="muted text-xs">{t.description}</div></td>
            <td>{t.permissions.join(", ") || "none"}</td>
            <td>{t.risk}{t.permissions.includes("workspace.execute") ? " · approval for test runners" : t.requires_approval ? " · approval" : ""}</td>
            <td>{t.timeout}s</td><td>{t.available ? "available" : "unavailable"}</td>
          </tr>))}</tbody></table></div>
    </main>
  );
}
