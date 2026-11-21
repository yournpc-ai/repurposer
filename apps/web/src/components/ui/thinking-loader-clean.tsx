// components/ui/thinking-loader-clean.tsx
"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** Clean working indicator. The caller supplies the current phase label. */

const RAYS = Array.from({ length: 8 }, (_, i) => i);

/** The current phase comes from the opening or receipt. */
export function ThinkingLoader({ label, className }: { label: string; className?: string }) {
  const [shown, setShown] = useState({ key: 0, text: label });
  const [leaving, setLeaving] = useState<{ key: number; text: string } | null>(null);
  if (label !== shown.text) {
    setLeaving(shown);
    setShown({ key: shown.key + 1, text: label });
  }

  // The text box takes the width of the incoming label, so the pill glides to its new size
  const root = useRef<HTMLSpanElement>(null);
  const box = useRef<HTMLSpanElement>(null);
  const current = useRef<HTMLSpanElement>(null);
  const measured = useRef(false);
  // Width of the label, capped by the room next to the spinner – a label that doesn't fit ends in "…"
  const fit = useRef(() => {});
  fit.current = () => {
    const r = root.current;
    const b = box.current;
    const c = current.current;
    if (!r || !b || !c) return;
    // Layout pixels (offset/scroll/client), so it stays right inside a CSS zoom or transform (+1 covers rounding)
    const full = c.scrollWidth + 1;
    const parent = r.parentElement;
    // Measured with the box at the label's full width – a parent that wraps around the pill grows with it, so only a
    // container that's really too narrow cuts the label. Without a transition, so the pill still glides from where it was.
    const was = { width: b.style.width, transition: b.style.transition };
    b.style.transition = "none";
    b.style.width = `${full}px`;
    const pad = parent ? getComputedStyle(parent) : null;
    const inner = parent && pad ? parent.clientWidth - parseFloat(pad.paddingLeft) - parseFloat(pad.paddingRight) : 0;
    const room = parent ? Math.floor(inner - (r.offsetWidth - b.offsetWidth)) : full;
    b.style.width = was.width;
    b.getBoundingClientRect();
    b.style.transition = was.transition;
    const cut = room > 0 && full > room;
    r.toggleAttribute("data-cut", cut);
    b.style.width = `${cut ? room : full}px`;
  };
  useLayoutEffect(() => {
    const b = box.current;
    if (!b) return;
    if (!measured.current) b.style.transition = "none";
    fit.current();
    if (!measured.current) {
      b.getBoundingClientRect();
      b.style.transition = "";
      measured.current = true;
    }
  }, [shown.key]);
  // A container that narrows or widens gets the label fitted again
  useEffect(() => {
    const parent = root.current?.parentElement;
    if (!parent || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => fit.current());
    ro.observe(parent);
    return () => ro.disconnect();
  }, []);

  return (
    <span
      ref={root}
      className={["ui-tlc", className].filter(Boolean).join(" ")}
      data-size="sm"
      data-variant="plain"
      role="status"
      aria-live="polite"
    >
      {/* React 19 hoists this into <head> once, no matter how many loaders render */}
      <style href="ui-thinking-loader-clean" precedence="default">
        {css}
      </style>

      <span className="ui-tlc__icon" aria-hidden="true">
        <svg className="ui-tlc__spinner" viewBox="0 0 16 16">
          {RAYS.map((i) => (
            <line
              key={i}
              x1="8"
              y1="1.75"
              x2="8"
              y2="4.75"
              transform={`rotate(${i * 45} 8 8)`}
              style={{ animationDelay: `${(i - 8) * 100}ms` }}
            />
          ))}
        </svg>
      </span>

      <span ref={box} className="ui-tlc__text">
        {leaving && (
          <span
            key={leaving.key}
            className="ui-tlc__label ui-tlc__label--out"
            aria-hidden="true"
            dir="auto"
            onAnimationEnd={() => setLeaving(null)}
          >
            {leaving.text}
          </span>
        )}
        <span
          key={shown.key}
          ref={current}
          className={["ui-tlc__label", shown.key > 0 && "ui-tlc__label--in", "ui-tlc__shine"].filter(Boolean).join(" ")}
          data-text={shown.text}
          title={shown.text}
          dir="auto"
        >
          {shown.text}
        </span>
      </span>
    </span>
  );
}

const css = /* css */ `
.ui-tlc {
  --ui-tlc-ink: var(--aui-ink, rgba(0, 0, 0, 0.88));
  --ui-tlc-text: var(--aui-muted, rgba(0, 0, 0, 0.61));
  --ui-tlc-accent: rgba(0, 96, 226, 0.765);
  --ui-tlc-bg: var(--aui-surface, #ffffff);
  --ui-tlc-shadow: var(--aui-shadow-card, 0 0 0 0.5px rgba(0, 0, 0, 0.06), 0 1px 1px -1px rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.05));
  --ui-tlc-shine: rgba(255, 255, 255, 0.82);
  --ui-tlc-ease: var(--aui-ease, cubic-bezier(0.22, 1, 0.36, 1));
  --ui-tlc-h: 32px;
  --ui-tlc-font: 13px;
  --ui-tlc-lh: 20px;
  --ui-tlc-icon: 16px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  box-sizing: border-box;
  height: var(--ui-tlc-h);
  padding: 0 10px 0 8px;
  border-radius: calc(var(--aui-radius, 7px) + 1px);
  background: var(--ui-tlc-bg);
  box-shadow: var(--ui-tlc-shadow);
  color: var(--ui-tlc-text);
  font-family: var(--aui-font, "Inter", "InterVariable", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif);
  font-size: var(--ui-tlc-font);
  font-weight: 500;
  line-height: var(--ui-tlc-lh);
  letter-spacing: -0.003em;
  max-width: 100%;
  vertical-align: middle;
  -webkit-font-smoothing: antialiased;
}
.ui-tlc[data-size="sm"] {
  --ui-tlc-h: 26px;
  --ui-tlc-font: 12px;
  --ui-tlc-lh: 16px;
  --ui-tlc-icon: 14px;
  gap: 5px;
  padding: 0 8px 0 6px;
  border-radius: calc(var(--aui-radius, 7px) - 1px);
}
.ui-tlc[data-variant="plain"] {
  height: auto;
  padding: 0;
  background: none;
  box-shadow: none;
}
.ui-tlc__icon {
  position: relative;
  flex: none;
  width: var(--ui-tlc-icon);
  height: var(--ui-tlc-icon);
}
.ui-tlc__icon svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
  transition: opacity 240ms ease, transform 420ms var(--ui-tlc-ease);
}
.ui-tlc__spinner line {
  stroke: var(--ui-tlc-accent);
  stroke-width: 1.1;
  stroke-linecap: round;
  opacity: 0.2;
  animation: ui-tlc-ray 800ms linear infinite;
}
.ui-tlc__text {
  position: relative;
  display: block;
  min-width: 0;
  height: var(--ui-tlc-lh);
  overflow: hidden;
  transition: width 460ms var(--ui-tlc-ease);
}
.ui-tlc__label {
  position: absolute;
  top: 0;
  left: 0;
  line-height: var(--ui-tlc-lh);
  white-space: nowrap;
}
.ui-tlc[data-cut] .ui-tlc__label {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ui-tlc__label--in {
  animation: ui-tlc-in 460ms var(--ui-tlc-ease) both;
}
.ui-tlc__label--out {
  animation: ui-tlc-out 320ms var(--ui-tlc-ease) both;
}
.ui-tlc__shine::after {
  content: attr(data-text);
  content: attr(data-text) / "";
  position: absolute;
  inset: 0;
  white-space: nowrap;
  color: transparent;
  background: linear-gradient(90deg, transparent 38%, var(--ui-tlc-shine) 50%, transparent 62%) 100% 0 / 300% 100% no-repeat;
  -webkit-background-clip: text;
  background-clip: text;
  animation: ui-tlc-sweep 1.6s linear infinite;
  pointer-events: none;
}

@keyframes ui-tlc-ray {
  0% { opacity: 1; }
  100% { opacity: 0.2; }
}
@keyframes ui-tlc-in {
  from { opacity: 0; transform: translateY(70%); filter: blur(3px); }
  to { opacity: 1; transform: none; filter: none; }
}
@keyframes ui-tlc-out {
  from { opacity: 1; transform: none; filter: none; }
  to { opacity: 0; transform: translateY(-70%); filter: blur(3px); }
}
@keyframes ui-tlc-sweep {
  from { background-position: 100% 0; }
  to { background-position: 0% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .ui-tlc *,
  .ui-tlc *::after {
    animation-duration: 1ms !important;
    animation-delay: 0ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
  .ui-tlc__spinner line { opacity: 0.6; }
  .ui-tlc__shine::after { display: none; }
}
:where(.dark, [data-theme="dark"]) .ui-tlc {
  --ui-tlc-ink: var(--aui-ink, rgba(255, 255, 255, 0.9));
  --ui-tlc-text: var(--aui-muted, rgba(255, 255, 255, 0.62));
  --ui-tlc-accent: var(--aui-blue, #4fb0fe);
  --ui-tlc-bg: var(--aui-surface, #1c1c1e);
  --ui-tlc-shadow: var(--aui-shadow-card, 0 0 0 0.5px rgba(255, 255, 255, 0.1), 0 1px 2px rgba(0, 0, 0, 0.4));
  --ui-tlc-shine: #ffffff;
}
`;
