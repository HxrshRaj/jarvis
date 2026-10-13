"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export type VoiceState = "idle" | "requesting" | "recording" | "processing" | "denied" | "unsupported" | "unavailable" | "error";

/**
 * Push-to-talk recording. Audio is captured ONLY between start() and stop(), is uploaded ONLY to the user's own
 * backend /voice/transcribe on stop(), and the microphone track is released immediately afterwards.
 */
export function useVoice(opts: { canTranscribe: boolean; onTranscript: (text: string) => void }) {
  const [state, setState] = useState<VoiceState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const discard = useRef(false);
  const starting = useRef(false);

  const release = useCallback(() => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    rec.current = null;
  }, []);
  useEffect(() => release, [release]);

  const start = useCallback(async () => {
    if (starting.current || rec.current) return;
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setState("unsupported"); setMessage("This browser does not support microphone recording."); return;
    }
    if (!opts.canTranscribe) {
      setState("unavailable"); setMessage("No speech-to-text provider is configured on the backend (set JARVIS_LLM_STT_MODEL)."); return;
    }
    starting.current = true;
    setState("requesting"); setMessage(null);
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      starting.current = false;
      setState("denied"); setMessage("Microphone access was denied. Allow it in your browser's site settings to use voice."); return;
    }
    chunks.current = []; discard.current = false;
    const r = new MediaRecorder(stream.current);
    r.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data); };
    r.onstop = async () => {
      const blob = new Blob(chunks.current, { type: r.mimeType || "audio/webm" });
      release();
      if (discard.current || blob.size === 0) { setState("idle"); return; }
      setState("processing");
      try {
        const { text } = await api.transcribe(blob);
        setState("idle");
        if (text.trim()) opts.onTranscript(text.trim()); else setMessage("I didn't catch any speech.");
      } catch (e) {
        setState("error"); setMessage(e instanceof Error ? e.message : "Transcription failed");
      }
    };
    rec.current = r;
    starting.current = false;
    r.start();
    setState("recording");
  }, [opts, release]);

  const stop = useCallback(() => { if (rec.current && rec.current.state !== "inactive") rec.current.stop(); }, []);
  const cancel = useCallback(() => { discard.current = true; stop(); if (!rec.current) { release(); setState("idle"); } }, [stop, release]);
  return { state, message, start, stop, cancel };
}

const PREF_KEY = "jarvis.speech";
type Prefs = { muted: boolean; volume: number; auto: boolean };
const DEFAULT_PREFS: Prefs = { muted: false, volume: 0.8, auto: false };

function loadPrefs(): Prefs {
  try { return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(PREF_KEY) ?? "{}") }; } catch { return DEFAULT_PREFS; }
}

/** Spoken responses: backend TTS when configured, otherwise the browser's local speechSynthesis (no upload). */
export function useSpeech(backendTts: boolean) {
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);
  const [speaking, setSpeaking] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  useEffect(() => setPrefs(loadPrefs()), []);
  const update = (p: Partial<Prefs>) => setPrefs((cur) => {
    const next = { ...cur, ...p };
    try { localStorage.setItem(PREF_KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
    return next;
  });

  const stop = useCallback(() => {
    audio.current?.pause(); audio.current = null;
    if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
    setSpeaking(false);
  }, []);

  const speak = useCallback(async (text: string) => {
    if (prefs.muted || !text.trim()) return;
    stop();
    const clipped = text.slice(0, 1500);
    setSpeaking(true);
    try {
      if (backendTts) {
        const url = URL.createObjectURL(await api.speak(clipped));
        const a = new Audio(url);
        a.volume = prefs.volume;
        a.onended = () => { URL.revokeObjectURL(url); setSpeaking(false); };
        audio.current = a;
        await a.play();
        return;
      }
    } catch { /* fall through to local synthesis */ }
    if (typeof speechSynthesis !== "undefined") {
      const u = new SpeechSynthesisUtterance(clipped);
      u.volume = prefs.volume;
      u.onend = () => setSpeaking(false);
      u.onerror = () => setSpeaking(false);
      speechSynthesis.speak(u);
    } else setSpeaking(false);
  }, [prefs.muted, prefs.volume, backendTts, stop]);

  useEffect(() => stop, [stop]);
  return { prefs, update, speak, stop, speaking };
}
