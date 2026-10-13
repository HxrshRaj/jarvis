"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken, setToken } from "@/lib/api";
import { AuthPanel } from "./AuthPanel";

export const NAV = [
  { href: "/", label: "Command Center" },
  { href: "/history", label: "Conversations" },
  { href: "/tasks", label: "Tasks" },
  { href: "/knowledge", label: "Knowledge Base" },
  { href: "/documents", label: "Documents" },
  { href: "/code", label: "Code Assistant" },
  { href: "/memory", label: "Memory" },
  { href: "/tools", label: "Tools & Permissions" },
  { href: "/settings", label: "Models & Providers" },
  { href: "/evals", label: "Evaluation" },
  { href: "/audit", label: "Security & Audit" },
];

function useTheme() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    try { const t = localStorage.getItem("jarvis.theme"); if (t === "light" || t === "dark") setTheme(t); } catch { /* storage unavailable */ }
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("jarvis.theme", theme); } catch { /* storage unavailable */ }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))] as const;
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [theme, toggle] = useTheme();
  useEffect(() => setAuthed(!!getToken()), []);

  if (authed === null) return null;
  if (!authed) return <AuthPanel onDone={() => setAuthed(true)} />;
  return (
    <div className="mx-auto max-w-7xl px-4 py-4 md:px-6">
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <span className="text-lg font-semibold tracking-[0.3em]" style={{ color: "var(--cyan)" }}>JARVIS</span>
        <div className="ml-auto flex gap-2">
          <button className="btn" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>{theme === "dark" ? "☀ Light" : "🌙 Dark"}</button>
          <button className="btn" onClick={() => { setToken(null); setAuthed(false); }}>Sign out</button>
        </div>
        <nav aria-label="Main" className="flex w-full flex-wrap gap-1">
          {NAV.map((l) => (
            <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined}
              className="btn" style={path === l.href ? { background: "rgba(34,211,238,.15)" } : undefined}>{l.label}</Link>
          ))}
        </nav>
      </header>
      {children}
    </div>
  );
}
