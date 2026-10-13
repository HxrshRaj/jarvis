"use client";
import { motion } from "framer-motion";

export type OrbState = "idle" | "working" | "waiting" | "error";
const COLORS: Record<OrbState, string> = { idle: "#22d3ee", working: "#3b82f6", waiting: "#f5b342", error: "#f87171" };
const LABEL: Record<OrbState, string> = { idle: "Idle", working: "Working", waiting: "Needs your approval", error: "Last task failed" };

export function Orb({ state }: { state: OrbState }) {
  const c = COLORS[state];
  const fast = state === "working";
  return (
    <div role="status" aria-label={`Assistant status: ${LABEL[state]}`} className="flex flex-col items-center gap-2">
      <div className="relative h-28 w-28">
        {[0, 1].map((i) => (
          <motion.span key={i} className="absolute inset-0 rounded-full border" style={{ borderColor: c }}
            animate={{ scale: [1, 1.5], opacity: [0.5, 0] }}
            transition={{ duration: fast ? 1.2 : 2.8, repeat: Infinity, delay: i * (fast ? 0.6 : 1.4), ease: "easeOut" }} />
        ))}
        <motion.div className="absolute inset-3 rounded-full"
          style={{ background: `radial-gradient(circle at 35% 30%, #fff9, ${c} 40%, #0b1220 100%)`, boxShadow: `0 0 36px ${c}55` }}
          animate={{ scale: fast ? [1, 1.07, 1] : [1, 1.03, 1] }}
          transition={{ duration: fast ? 0.9 : 3, repeat: Infinity }} />
      </div>
      <span className="muted text-xs tracking-widest uppercase">{LABEL[state]}</span>
    </div>
  );
}
