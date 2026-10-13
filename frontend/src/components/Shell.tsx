"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken, setToken } from "@/lib/api";
import { AuthPanel } from "./AuthPanel";

const LIVE = [
  { href: "/", label: "Command Center" },
  { href: "/tasks", label: "Tasks & Workflows" },
  { href: "/tools", label: "Tools & Permissions" },
  { href: "/audit", label: "Security & Audit" },
];
// Honest roadmap: these pages are NOT built yet and are deliberately not linked.
export const PLANNED = ["Knowledge Base", "Code Assistant", "Document Workspace", "Memory", "Model Settings", "Evaluation"];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [authed, setAuthed] = useState<boolean | null>(null);
  useEffect(() => setAuthed(!!getToken()), []);

  if (authed === null) return null;
  if (!authed) return <AuthPanel onDone={() => setAuthed(true)} />;
  return (
    <div className="mx-auto max-w-7xl px-4 py-4 md:px-6">
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <span className="text-lg font-semibold tracking-[0.3em]" style={{ color: "var(--cyan)" }}>JARVIS</span>
        <nav aria-label="Main" className="flex flex-wrap gap-1">
          {LIVE.map((l) => (
            <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined}
              className="btn" style={path === l.href ? { background: "rgba(34,211,238,.15)" } : undefined}>{l.label}</Link>
          ))}
        </nav>
        <button className="btn ml-auto" onClick={() => { setToken(null); setAuthed(false); }}>Sign out</button>
      </header>
      {children}
    </div>
  );
}
