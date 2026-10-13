"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const yn = (v: boolean) => (v ? "available" : "not configured");

export default function SettingsPage() {
  const p = useQuery({ queryKey: ["provider"], queryFn: api.provider });
  const caps = useQuery({ queryKey: ["caps"], queryFn: api.capabilities });
  const usage = useQuery({ queryKey: ["usage"], queryFn: api.usage });
  return (
    <main className="grid gap-4 lg:grid-cols-2">
      <section className="panel space-y-2 p-4 text-sm">
        <h1 className="text-lg font-semibold">Model &amp; provider settings</h1>
        {p.error && <p role="alert" style={{ color: "var(--danger)" }}>{p.error.message}</p>}
        {p.data && <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="muted">Provider</dt><dd>{p.data.provider}{p.data.provider === "mock" ? " (offline mode — no AI model)" : ""}</dd>
          <dt className="muted">Endpoint host</dt><dd>{p.data.endpoint_host ?? "—"}</dd>
          <dt className="muted">Chat model</dt><dd>{p.data.model ?? "—"}</dd>
          <dt className="muted">Vision model</dt><dd>{p.data.vision_model ?? "—"}</dd>
          <dt className="muted">Speech-to-text</dt><dd>{p.data.stt_model ?? "—"}</dd>
          <dt className="muted">Text-to-speech</dt><dd>{p.data.tts_model ?? "—"}</dd>
          <dt className="muted">API key</dt><dd>{p.data.api_key_configured ? "configured (never shown)" : "not set"}</dd>
        </dl>}
        <p className="muted text-xs">{p.data?.how_to_change} Keys live only in backend environment variables; this page cannot change them.</p>
        <h2 className="pt-2 text-sm font-semibold">Capabilities</h2>
        {caps.data && <ul className="muted text-xs"><li>Language model: {yn(caps.data.llm)}</li><li>Vision: {yn(caps.data.vision)}</li><li>Speech-to-text: {yn(caps.data.speech_to_text)}</li>
          <li>Text-to-speech: {caps.data.text_to_speech ? "backend" : "browser-local fallback"}</li><li>Router: {caps.data.router}</li></ul>}
      </section>
      <section className="panel space-y-2 p-4 text-sm">
        <h2 className="text-sm font-semibold">Provider usage</h2>
        {usage.data?.usage.length === 0 && <p className="muted text-xs">No provider calls recorded yet.</p>}
        <table className="w-full text-left text-xs"><thead className="muted"><tr><th>Model</th><th>Purpose</th><th>Calls</th><th>Tokens in/out</th><th>Est. cost</th></tr></thead>
          <tbody>{usage.data?.usage.map((u, i) => (<tr key={i}><td>{u.model}</td><td>{u.purpose}</td><td>{u.calls}</td><td>{u.prompt_tokens}/{u.completion_tokens}</td>
            <td>{u.estimated_cost_usd === null ? "n/a" : `$${u.estimated_cost_usd.toFixed(4)}`}</td></tr>))}</tbody></table>
        <p className="muted text-xs">{usage.data?.note}</p>
      </section>
    </main>
  );
}
