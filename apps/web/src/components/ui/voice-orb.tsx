// components/ui/voice-orb.tsx
"use client";

import { useEffect, useRef, type CSSProperties } from "react";

/*
 * Voice Orb – the face of a voice assistant: a sphere made of dots that shows what the AI is doing, in one
 * self-contained file. No images, no libraries – a few hundred points drawn on a canvas.
 *   · idle       the sphere turns slowly and breathes
 *   · listening  dots jump outward with the input level, like a surface catching sound
 *   · thinking   the sphere collapses into a fast spinning ring with a light running around it
 *   · speaking   waves travel from pole to pole with the output level
 * The states melt into each other instead of switching, and the dots give way to the pointer.
 * Pass `level` (0–1) from your audio to drive it for real; without it the orb moves on its own.
 * Pure monochrome Studio default: warm graphite resting dots & obsidian active dots in light mode;
 * soft silver resting dots & glowing ivory-white active dots in dark mode.
 */

export type VoiceOrbState = "idle" | "listening" | "thinking" | "speaking";

export type VoiceOrbProps = {
  state?: VoiceOrbState;
  /** Input or output loudness from 0 to 1 – without it the orb fakes a natural level */
  level?: number;
  /** Edge length in px */
  size?: number;
  /** Number of dots – more is denser and costs a little more */
  dots?: number;
  /** Color the moving dots take on – any CSS color. Defaults to pure monochrome Studio ink */
  accent?: string;
  /** The line under the orb; false hides it, an object replaces single texts */
  label?: boolean | Partial<Record<VoiceOrbState, string>>;
  /** Dots give way to the pointer */
  interactive?: boolean;
  /** Makes the orb a button, e.g. to start and stop auditioning */
  onPress?: () => void;
  className?: string;
  style?: CSSProperties;
};

const LABELS: Record<VoiceOrbState, string> = {
  idle: "Tap to audition",
  listening: "Listening",
  thinking: "Loading",
  speaking: "Speaking",
};
const STATES: VoiceOrbState[] = ["idle", "listening", "thinking", "speaking"];
/** Turning speed per state, in radians per second */
const SPIN: Record<VoiceOrbState, number> = {
  idle: 0.16,
  listening: 0.3,
  thinking: 1.9,
  speaking: 0.42,
};

const clamp = (n: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, n));
const reduced = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** "rgb(…)" / "#rrggbb" → [r, g, b], read through the browser so every CSS color works */
function toRgb(color: string, probe: HTMLElement): [number, number, number] {
  probe.style.color = color;
  const m = getComputedStyle(probe).color.match(/[\d.]+/g);
  return m ? [Number(m[0]), Number(m[1]), Number(m[2])] : [23, 23, 23];
}

export function VoiceOrb({
  state = "idle",
  level,
  size = 220,
  dots = 520,
  accent,
  label = true,
  interactive = true,
  onPress,
  className,
  style,
}: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // The loop reads these, so changing a prop never restarts the animation
  const live = useRef({ state, level, interactive });
  live.current = { state, level, interactive };
  /** Draws one frame – used when motion is reduced and nothing runs on its own */
  const redraw = useRef<() => void>(() => {});

  useEffect(() => {
    const canvas = canvasRef.current;
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas?.getContext("2d") ?? null;
    } catch {
      ctx = null;
    }
    if (!canvas || !ctx) return;

    // Points spread evenly over a sphere (Fibonacci lattice)
    const count = Math.max(60, Math.round(dots));
    const points = new Float32Array(count * 3);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < count; i++) {
      const y = 1 - (i / (count - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      points[i * 3] = Math.cos(golden * i) * r;
      points[i * 3 + 1] = y;
      points[i * 3 + 2] = Math.sin(golden * i) * r;
    }

    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);

    // Colors come from CSS, so themes and the accent prop just work (pure monochrome fallback)
    const probe = document.createElement("span");
    probe.style.display = "none";
    canvas.parentElement?.appendChild(probe);
    let ink: [number, number, number] = [110, 110, 115];
    let tint: [number, number, number] = [23, 23, 23];
    const readColors = () => {
      const cs = getComputedStyle(canvas);
      ink = toRgb(cs.color || "#6e6e73", probe);
      tint = toRgb(
        cs.getPropertyValue("--ui-vo-accent").trim() || cs.color || "#171717",
        probe,
      );
    };
    readColors();

    const weight: Record<VoiceOrbState, number> = {
      idle: 0,
      listening: 0,
      thinking: 0,
      speaking: 0,
    };
    weight[live.current.state] = 1;
    let angle = 0;
    let shownLevel = 0;
    const pointer = { x: 0, y: 0, on: false, strength: 0 };
    let last = performance.now();
    let frame = 0;
    let frames = 0;
    let visible = true;
    const still = reduced();

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = now / 1000;
      const cur = live.current;
      if (++frames % 30 === 0) readColors();

      // States melt into each other
      let spin = 0;
      for (const s of STATES) {
        weight[s] += ((s === cur.state ? 1 : 0) - weight[s]) * Math.min(1, dt * 5);
        spin += weight[s] * SPIN[s];
      }
      angle += spin * dt;

      // Loudness: the real one, or a made-up one that feels like speech
      const fake =
        cur.state === "listening"
          ? clamp(
              0.35 +
                0.35 * Math.sin(t * 2.1) * Math.sin(t * 5.3) +
                0.3 * Math.sin(t * 9.7 + 1) * Math.sin(t * 0.9),
            )
          : clamp(
              0.3 +
                0.7 *
                  Math.abs(Math.sin(t * 4.1)) *
                  (0.5 + 0.5 * Math.sin(t * 1.3 + 2)),
            );
      // A level that isn't a number (NaN before the first audio frame) falls back to the fake one instead of freezing the orb
      const target =
        cur.level !== undefined && Number.isFinite(cur.level)
          ? clamp(cur.level)
          : fake;
      shownLevel += (target - shownLevel) * Math.min(1, dt * 12);
      pointer.strength +=
        ((pointer.on && cur.interactive ? 1 : 0) - pointer.strength) *
        Math.min(1, dt * 8);

      const w = size;
      const c = w / 2;
      const R = w * 0.34;
      const tilt = 0.32 + weight.thinking * 0.55;
      const sinT = Math.sin(tilt);
      const cosT = Math.cos(tilt);
      const sinA = Math.sin(angle);
      const cosA = Math.cos(angle);
      const reach = w * 0.2;
      const base = Math.max(0.95, w / 160);

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, w);

      // A soft monochrome halo behind the orb that follows the level
      const glow =
        (weight.listening + weight.speaking) * shownLevel * 0.16 +
        weight.thinking * 0.06;
      if (glow > 0.004) {
        const g = ctx.createRadialGradient(c, c, R * 0.2, c, c, R * 1.55);
        g.addColorStop(0, `rgba(${tint[0]}, ${tint[1]}, ${tint[2]}, ${glow})`);
        g.addColorStop(1, `rgba(${tint[0]}, ${tint[1]}, ${tint[2]}, 0)`);
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, w, w);
      }

      for (let i = 0; i < count; i++) {
        const bx = points[i * 3];
        const by = points[i * 3 + 1];
        const bz = points[i * 3 + 2];

        // How far this dot leaves the surface
        const noise =
          (Math.sin(bx * 3.1 + t * 2.3) +
            Math.sin(by * 4.3 - t * 1.7) +
            Math.sin(bz * 5.2 + t * 2.9)) /
          3;
        const breathe = weight.idle * 0.022 * Math.sin(t * 1.3 + by * 2);
        const hear =
          weight.listening * shownLevel * 0.3 * Math.max(0, noise) ** 1.4;
        const speak =
          weight.speaking * shownLevel * 0.13 * Math.sin(by * 7.5 - t * 7);
        const out = breathe + hear + speak;
        let x = bx * (1 + out);
        let y = by * (1 + out);
        let z = bz * (1 + out);

        // Thinking: the sphere collapses into a ring
        let scan = 0;
        // Dots near the poles have no place on the ring – they fade out while it forms
        let keep = 1;
        if (weight.thinking > 0.001) {
          const len = Math.hypot(bx, bz) || 1;
          const wobble = 1 + 0.035 * Math.sin(t * 3 + i * 0.7);
          const k = weight.thinking;
          x += ((bx / len) * wobble - x) * k;
          y += (by * 0.2 - y) * k;
          keep = 1 - k * (1 - clamp((Math.hypot(bx, bz) - 0.25) * 2.2));
          z += ((bz / len) * wobble - z) * k;
          // A light runs around the ring
          const a = Math.atan2(bz, bx) + angle;
          scan = k * Math.max(0, Math.cos(a - t * 2.2)) ** 6;
        }

        // Turn around the vertical axis, then tip the whole thing towards the viewer
        const rx = x * cosA + z * sinA;
        const rz = -x * sinA + z * cosA;
        const ry = y * cosT - rz * sinT;
        const depth = y * sinT + rz * cosT;

        const persp = 3.4 / (3.4 - depth);
        let sx = c + rx * R * persp;
        let sy = c + ry * R * persp;

        // Dots give way to the pointer
        if (pointer.strength > 0.01) {
          const dx = sx - pointer.x;
          const dy = sy - pointer.y;
          const d = Math.hypot(dx, dy) || 1;
          if (d < reach) {
            const push = (1 - d / reach) ** 2 * w * 0.07 * pointer.strength;
            sx += (dx / d) * push;
            sy += (dy / d) * push;
          }
        }

        const front = (depth + 1.3) / 2.6;
        const active = clamp(Math.abs(hear + speak) * 9 + scan);
        const radius = base * (0.55 + 0.75 * front) * persp * (1 + active * 0.5);
        const alpha = clamp(0.14 + 0.86 * front ** 1.6 + active * 0.3) * keep;
        if (alpha < 0.01) continue;
        const r = Math.round(ink[0] + (tint[0] - ink[0]) * active);
        const g = Math.round(ink[1] + (tint[1] - ink[1]) * active);
        const b = Math.round(ink[2] + (tint[2] - ink[2]) * active);
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(sx, sy, radius, 0, Math.PI * 2);
        ctx.fill();
      }

      if (!still && visible) frame = requestAnimationFrame(draw);
    };

    // Reduced motion: no loop – one still frame per state, with the state fully applied
    redraw.current = () => {
      if (!still) return;
      for (const s of STATES) weight[s] = s === live.current.state ? 1 : 0;
      shownLevel = live.current.level ?? 0.6;
      last = performance.now();
      draw(last);
    };

    // Only run while the orb is on screen and the tab is in front
    const start = () => {
      cancelAnimationFrame(frame);
      last = performance.now();
      frame = requestAnimationFrame(draw);
    };
    const io =
      typeof IntersectionObserver !== "undefined"
        ? new IntersectionObserver(([entry]) => {
            visible = entry.isIntersecting && !document.hidden;
            if (visible) start();
          })
        : null;
    io?.observe(canvas);
    const onVisibility = () => {
      visible = !document.hidden;
      if (visible) start();
    };
    document.addEventListener("visibilitychange", onVisibility);
    start();

    const move = (e: PointerEvent) => {
      const box = canvas.getBoundingClientRect();
      // The box may be scaled by a zoom or transform on a parent
      const k = size / (box.width || size);
      pointer.x = (e.clientX - box.left) * k;
      pointer.y = (e.clientY - box.top) * k;
      pointer.on = e.pointerType === "mouse";
    };
    const leave = () => (pointer.on = false);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerleave", leave);

    return () => {
      cancelAnimationFrame(frame);
      io?.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerleave", leave);
      probe.remove();
    };
  }, [size, dots]);

  useEffect(() => redraw.current(), [state, level]);

  const text =
    label === false
      ? null
      : { ...LABELS, ...(typeof label === "object" ? label : {}) }[state];
  const vars = {
    ...style,
    ["--ui-vo-size" as string]: `${size}px`,
    ...(accent ? { ["--ui-vo-accent" as string]: accent } : {}),
  };
  const body = (
    <>
      <canvas ref={canvasRef} className="ui-vo__canvas" aria-hidden="true" />
      {text !== null && (
        <span className="ui-vo__label" aria-live="polite">
          <span key={state}>
            {text}
            {state !== "idle" && (
              <span className="ui-vo__dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            )}
          </span>
        </span>
      )}
    </>
  );

  return (
    <>
      <style href="ui-voice-orb" precedence="default">
        {css}
      </style>
      {onPress ? (
        <button
          type="button"
          className={["ui-vo", className].filter(Boolean).join(" ")}
          data-state={state}
          style={vars}
          aria-label={text ? undefined : `Voice audition: ${LABELS[state]}`}
          onClick={onPress}
        >
          {body}
        </button>
      ) : (
        <div
          className={["ui-vo", className].filter(Boolean).join(" ")}
          data-state={state}
          style={vars}
          role="img"
          aria-label={`Voice audition: ${text ?? LABELS[state]}`}
        >
          {body}
        </div>
      )}
    </>
  );
}

const css = /* css */ `
.ui-vo {
  --ui-vo-ink: var(--aui-muted, #6e6e73);
  --ui-vo-muted: var(--aui-muted, #71717a);
  --ui-vo-accent: var(--aui-ink, #171717);
  --ui-vo-focus: rgba(23, 23, 23, 0.24);
  display: inline-grid;
  justify-items: center;
  gap: 2px;
  margin: 0;
  padding: 0;
  border: 0;
  background: none;
  font-family: var(--aui-font, "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif);
  color: var(--ui-vo-ink);
  -webkit-font-smoothing: antialiased;
  -webkit-tap-highlight-color: transparent;
}
button.ui-vo { border-radius: 9999px; cursor: pointer; }
button.ui-vo:focus-visible { outline: 2px solid var(--ui-vo-focus); outline-offset: 4px; }
.ui-vo__canvas { display: block; width: var(--ui-vo-size); height: var(--ui-vo-size); color: var(--ui-vo-ink); transition: transform 500ms cubic-bezier(0.32, 0.72, 0.24, 1); }
button.ui-vo:active .ui-vo__canvas { transform: scale(0.97); }

/* Never wider than the orb – a long label ends in … */
.ui-vo__label { max-width: max(var(--ui-vo-size), 120px); height: 20px; overflow: hidden; font-size: 13px; font-weight: 500; line-height: 20px; color: var(--ui-vo-muted); white-space: nowrap; }
.ui-vo__label > span { max-width: 100%; display: inline-flex; align-items: baseline; gap: 1px; animation: ui-vo-in 360ms cubic-bezier(0.32, 0.72, 0.24, 1) both; }
.ui-vo[data-state="listening"] .ui-vo__label, .ui-vo[data-state="speaking"] .ui-vo__label { color: var(--ui-vo-accent); }
.ui-vo__dots { display: inline-flex; gap: 2px; margin-left: 2px; }
.ui-vo__dots i { width: 2.5px; height: 2.5px; border-radius: 50%; background: currentColor; animation: ui-vo-blink 1.2s ease-in-out infinite; }
.ui-vo__dots i:nth-child(2) { animation-delay: 0.16s; }
.ui-vo__dots i:nth-child(3) { animation-delay: 0.32s; }

@keyframes ui-vo-in { from { opacity: 0; transform: translateY(5px); filter: blur(3px); } }
@keyframes ui-vo-blink { 0%, 100% { opacity: 0.25; } 40% { opacity: 1; } }

@media (prefers-reduced-motion: reduce) {
  .ui-vo *, .ui-vo *::before, .ui-vo *::after { animation: none !important; transition: none !important; }
}

/* Dark mode: follows a .dark class or data-theme="dark" on any ancestor, e.g. <html> */
:where(.dark, [data-theme="dark"]) .ui-vo {
  --ui-vo-ink: #8e8e93;
  --ui-vo-muted: #9a9aa0;
  --ui-vo-accent: #ffffff;
  --ui-vo-focus: rgba(255, 255, 255, 0.3);
}
`;
