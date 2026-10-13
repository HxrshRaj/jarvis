"use client";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

const MAX = 5 * 1024 * 1024;
const TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];

export function LookAtThis({ available }: { available: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("What error is shown here?");
  const [localError, setLocalError] = useState<string | null>(null);
  const m = useMutation({ mutationFn: () => api.lookAtThis(file!, question) });

  function pick(f: File | undefined) {
    setLocalError(null); m.reset();
    if (!f) return setFile(null);
    if (!TYPES.includes(f.type)) return setLocalError("Use a PNG, JPEG, GIF or WebP image.");
    if (f.size > MAX) return setLocalError("Image must be 5 MB or smaller.");
    setFile(f);
  }

  return (
    <section className="panel space-y-2 p-4 text-sm" aria-label="Look at this">
      <h2 className="text-sm font-semibold">Look at This</h2>
      <p className="muted text-xs">Upload a screenshot yourself; it is sent to your configured vision model and is not stored. JARVIS never watches your screen.</p>
      {!available && <p className="text-xs" style={{ color: "var(--amber)" }}>No vision model configured (set JARVIS_LLM_VISION_MODEL).</p>}
      <label className="block text-xs">Image
        <input className="input mt-1" type="file" accept={TYPES.join(",")} onChange={(e) => pick(e.target.files?.[0])} /></label>
      <label className="block text-xs">Question
        <input className="input mt-1" value={question} maxLength={1000} onChange={(e) => setQuestion(e.target.value)} /></label>
      <button className="btn btn-primary" disabled={!file || !question.trim() || m.isPending} onClick={() => m.mutate()}>{m.isPending ? "Analysing…" : "Analyse image"}</button>
      {(localError || m.error) && <p role="alert" className="text-xs" style={{ color: "var(--danger)" }}>{localError ?? (m.error as Error).message}</p>}
      {m.data && <div className="rounded-lg border p-2 text-xs whitespace-pre-wrap" style={{ borderColor: "var(--border)" }}>{m.data.answer}<p className="muted mt-1">{m.data.note}</p></div>}
    </section>
  );
}
