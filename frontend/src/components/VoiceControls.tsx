"use client";
import { useVoice, type VoiceState } from "@/lib/voice";

const LABEL: Record<VoiceState, string> = {
  idle: "Hold to talk", requesting: "Waiting for microphone permission…", recording: "Recording — release to send",
  processing: "Transcribing…", denied: "Microphone blocked", unsupported: "Voice not supported", unavailable: "Voice unavailable", error: "Voice error — try again",
};

export function VoiceControls(props: {
  canTranscribe: boolean; onTranscript: (t: string) => void;
  speech: { muted: boolean; volume: number; auto: boolean }; setSpeech: (p: Partial<{ muted: boolean; volume: number; auto: boolean }>) => void;
  speaking: boolean; stopSpeaking: () => void;
}) {
  const v = useVoice({ canTranscribe: props.canTranscribe, onTranscript: props.onTranscript });
  const rec = v.state === "recording";
  const keyHandlers = {
    onKeyDown: (e: React.KeyboardEvent) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); v.start(); } },
    onKeyUp: (e: React.KeyboardEvent) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); v.stop(); } },
    onBlur: () => { if (rec) v.cancel(); },
  };
  return (
    <section aria-label="Voice controls" className="flex w-full flex-wrap items-center justify-center gap-3 text-sm">
      <button type="button" className={`btn ${rec ? "btn-primary" : ""}`} aria-pressed={rec} aria-describedby="voice-status"
        disabled={v.state === "processing" || v.state === "requesting"}
        onPointerDown={() => v.start()} onPointerUp={() => v.stop()} onPointerLeave={() => { if (rec) v.stop(); }} {...keyHandlers}>
        {rec ? "● Recording" : "🎙 Push to talk"}
      </button>
      {rec && <button type="button" className="btn" onClick={v.cancel}>Cancel</button>}
      <span id="voice-status" role="status" className="muted text-xs">{LABEL[v.state]}{v.message ? ` — ${v.message}` : ""}</span>
      <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={props.speech.auto} onChange={(e) => props.setSpeech({ auto: e.target.checked })} /> Speak responses</label>
      <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={props.speech.muted} onChange={(e) => props.setSpeech({ muted: e.target.checked })} /> Mute</label>
      <label className="flex items-center gap-1 text-xs">Volume
        <input type="range" min={0} max={1} step={0.05} value={props.speech.volume} aria-label="Volume" onChange={(e) => props.setSpeech({ volume: Number(e.target.value) })} /></label>
      {props.speaking && <button type="button" className="btn" onClick={props.stopSpeaking}>Stop speaking</button>}
    </section>
  );
}
