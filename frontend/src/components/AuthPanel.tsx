"use client";
import { useState } from "react";
import { api, setToken } from "@/lib/api";

export function AuthPanel({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const { access_token } = await api.auth(mode, email, password);
      setToken(access_token);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally { setBusy(false); }
  }

  return (
    <main className="mx-auto mt-24 max-w-sm px-4">
      <form onSubmit={submit} className="panel space-y-4 p-6" aria-label="Sign in">
        <h1 className="text-2xl font-semibold tracking-[0.3em]" style={{ color: "var(--cyan)" }}>JARVIS</h1>
        <p className="muted text-sm">{mode === "login" ? "Sign in to your local workspace." : "Create a local account (password ≥ 10 characters)."}</p>
        <label className="block text-sm">Email
          <input className="input mt-1" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <label className="block text-sm">Password
          <input className="input mt-1" type="password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
        </label>
        {error && <p role="alert" className="text-sm" style={{ color: "var(--danger)" }}>{error}</p>}
        <button className="btn btn-primary w-full" disabled={busy}>{busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="muted w-full text-sm underline" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
        </button>
      </form>
    </main>
  );
}
