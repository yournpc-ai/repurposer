import React from "react";
import { cueProgress, easeInOutCubic, easeOutCubic, lerp } from "./math";

export interface CursorCue {
  x: number; y: number;
  click_at_s: number;
  start_x?: number | null; start_y?: number | null;
}

export function VirtualCursor({ cue, tSec, scaleUnit, accent }: {
  cue: CursorCue; tSec: number; scaleUnit: number; accent: string;
}): React.JSX.Element | null {
  const travelSec = Math.min(0.85, cue.click_at_s);
  const start = cue.click_at_s - travelSec;
  if (tSec < start) return null;
  const t = easeInOutCubic(cueProgress(tSec, start, travelSec));
  // A quadratic Bezier with a horizontal departure and vertical arrival.
  const x = lerp(lerp(cue.start_x ?? 0.08, cue.x, t), cue.x, t);
  const y0 = cue.start_y ?? 0.88;
  const y = lerp(y0, lerp(y0, cue.y, t), t);
  const elapsed = tSec - cue.click_at_s;
  const press = elapsed < 0 ? cueProgress(tSec, cue.click_at_s - 0.1, 0.1) : 1 - easeOutCubic(elapsed / 0.18);
  return (
    <div style={{ position: "absolute", left: `${100*x}%`, top: `${100*y}%`, width: 0, height: 0, zIndex: 4, pointerEvents: "none" }}>
      {[0, 0.09].map(delay => {
        const p = cueProgress(elapsed, delay, 0.4);
        const size = lerp(6, 66, easeOutCubic(p)) * scaleUnit;
        return elapsed >= delay && p < 1 && <span key={delay} style={{
          position: "absolute", width: size, height: size, borderRadius: "50%",
          transform: "translate(-50%, -50%)", opacity: (1 - p) * 0.8, border: `2px solid ${accent}`,
        }} />;
      })}
      <svg width={28 * scaleUnit} height={34 * scaleUnit} viewBox="0 0 28 34" style={{
        display: "block", overflow: "visible", transformOrigin: "0 0", transform: `scale(${1 - press * 0.16})`,
        filter: "drop-shadow(0 2px 2px rgba(0,0,0,.38))",
      }}>
        <path d="M0 0 L23 15 L12 17 L8 28 Z" fill="#F8FAFC" stroke="#172330" strokeWidth="1.5" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}
