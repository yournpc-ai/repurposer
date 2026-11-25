// components/ui/thinking-state-clean.tsx
"use client";

import { useId, useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { formatElapsed, useNow } from "@/components/chat/workTiming";
import type { StepPlanItem } from "@/lib/workbench";

/*
 * Thinking State (Clean) – the "working…" panel of an AI chat, in a single self-contained file.
 * Clean style: no card, straight on the page. The header row holds a pixel mark, the live timer and
 * the chevron; below it the searches with their sources and the thinking steps appear one after
 * another; at the end a check, and the header turns into "Worked for …".
 * The styles are injected below, so no extra files are needed.
 */

export interface ThinkingTrailStep {
  id: string;
  kind: "web" | "step" | "note" | "error" | "thinking";
  label: string;
  meta?: string;
  chips?: string[];
  status: "running" | "done" | "error";
  /** Optional epoch ms start for an inline ticking timer (e.g. post-tool Thinking Xs). */
  startedAtMs?: number | null;
  detail?: ReactNode;
}

export interface ThinkingStateProps {
  steps: ThinkingTrailStep[];
  live: boolean;
  headerLabel: string;
  startedAtMs?: number | null;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Optional dynamic task checklist from update_steps. */
  stepsPlan?: StepPlanItem[];
  /** Localized count label beside the progress ring, e.g. "3/5 steps". */
  stepsProgressLabel?: string;
  /** Accessible label for the checklist list. */
  stepsAriaLabel?: string;
}

export function ThinkingState({
  steps, live, headerLabel, startedAtMs, open: controlledOpen, defaultOpen = false, onOpenChange,
  stepsPlan, stepsProgressLabel, stepsAriaLabel,
}: ThinkingStateProps) {
  const bodyId = useId();
  const prefersReducedMotion = useReducedMotion();
  const [override, setOverride] = useState({ live, open: defaultOpen });
  if (override.live !== live) setOverride({ live, open: false });
  const open = controlledOpen ?? (override.live === live && override.open);
  const hasPlan = Boolean(stepsPlan && stepsPlan.length > 0);
  const expandable = steps.length > 0 || hasPlan;
  const Header = expandable ? "button" : "div";
  const planTotal = stepsPlan?.length ?? 0;
  const planDone = stepsPlan ? stepsPlan.filter((item) => item.status === "done").length : 0;
  const planHasFailed = stepsPlan ? stepsPlan.some((item) => item.status === "failed") : false;
  const planRatio = planTotal > 0 ? Math.min(1, Math.max(0, planDone / planTotal)) : 0;
  const ringRadius = 5;
  const ringCircumference = 2 * Math.PI * ringRadius;
  const ringOffset = ringCircumference * (1 - planRatio);
  const planTone = planHasFailed ? "error" : planDone === planTotal && planTotal > 0 ? "done" : "active";
  return (
    <div className="ui-thinkc" data-done={!live || undefined}>
      {/* React 19 hoists this into <head> once, no matter how many panels render */}
      <style href="ui-thinking-state-clean" precedence="default">
        {css}
      </style>

      <Header className="ui-thinkc__head" {...(expandable ? {
        type: "button" as const,
        "aria-controls": bodyId,
        "aria-expanded": open,
        onClick: () => {
          if (controlledOpen === undefined) setOverride({ live, open: !open });
          onOpenChange?.(!open);
        },
      } : {})}>
        {/* A 3×3 pixel mark: the squares twinkle while it thinks and settle once it's done */}
        <span className="ui-thinkc__mark" aria-hidden="true">
          {Array.from({ length: 9 }, (_, i) => (
            <i key={i} style={{ animationDelay: `${PIXEL_DELAYS[i]}ms` }} />
          ))}
        </span>
        <span className="ui-thinkc__title" key={live ? "busy" : "done"}>
          <span className={live ? "ui-thinkc__shimmer" : undefined} data-text={headerLabel}>{headerLabel}</span>
          {live && startedAtMs != null && <Elapsed since={startedAtMs} />}
        </span>
        {expandable && <span className="ui-thinkc__chevron" aria-hidden="true">
          <svg viewBox="0 0 16 16">
            <path d="M4.5 6.25 8 9.75l3.5-3.5" />
          </svg>
        </span>}
        {hasPlan && (
          <span className="ui-thinkc__steps-badge" data-tone={planTone}>
            <svg viewBox="0 0 14 14" className="ui-thinkc__ring" aria-hidden="true">
              <circle cx="7" cy="7" r={ringRadius} className="ui-thinkc__ring-track" />
              <circle
                cx="7"
                cy="7"
                r={ringRadius}
                className="ui-thinkc__ring-arc"
                strokeDasharray={ringCircumference}
                strokeDashoffset={ringOffset}
              />
            </svg>
            <span className="ui-thinkc__steps-count">
              {stepsProgressLabel ?? `${planDone}/${planTotal} steps`}
            </span>
          </span>
        )}
      </Header>

      {/* Only the steps fold away – the header row always stays in view */}
      <div className="ui-thinkc__body" id={bodyId} data-open={open} inert={!open} aria-hidden={!open}>
        <div className="ui-thinkc__clip">
          {hasPlan && stepsPlan && (
            <ul
              className="ui-thinkc__plan"
              data-has-trail={steps.length > 0 || undefined}
              aria-label={stepsAriaLabel}
            >
              {stepsPlan.map((planItem, idx) => (
                <motion.li
                  key={`${idx}:${planItem.title}`}
                  layout={prefersReducedMotion ? false : "position"}
                  initial={prefersReducedMotion ? false : { opacity: 0, y: 3 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                  className="ui-thinkc__plan-item"
                  data-status={planItem.status}
                >
                  <span className="ui-thinkc__plan-icon" aria-hidden="true">
                    {planItem.status === "done" ? (
                      <svg viewBox="0 0 16 16" className="ui-thinkc__plan-check">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M5.25 8.1 7.1 10l3.7-3.8" />
                      </svg>
                    ) : planItem.status === "in_progress" ? (
                      <span className="ui-thinkc__plan-pulse" />
                    ) : planItem.status === "failed" ? (
                      <svg viewBox="0 0 16 16" className="ui-thinkc__plan-fail">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M8 5v3.5M8 10.9v.2" />
                      </svg>
                    ) : planItem.status === "skipped" ? (
                      <svg viewBox="0 0 16 16" className="ui-thinkc__plan-skip">
                        <circle cx="8" cy="8" r="6.5" />
                        <path d="M5.5 8h5" />
                      </svg>
                    ) : (
                      <span className="ui-thinkc__plan-pending" />
                    )}
                  </span>
                  <span className="ui-thinkc__plan-title" dir="auto">{planItem.title}</span>
                </motion.li>
              ))}
            </ul>
          )}
          {steps.length > 0 && (
          <ol className="ui-thinkc__list" aria-live="polite">
            {steps.map((step) => {
              const isActive = live && step.status === "running";
              return (
                <li key={step.id} className="ui-thinkc__item" data-kind={step.kind} data-active={isActive || undefined}>
                  <span className="ui-thinkc__node" aria-hidden="true">
                    {step.kind === "note" ? null : step.kind === "web" ? (
                      <svg viewBox="0 0 24 24" className="ui-thinkc__globe">
                        <path d="M22 12A10 10 0 1 0 12 22" />
                        <path d="M20 5.7c-.93.07-2.13.43-2.96 1.5-1.5 1.94-3 2.1-4 1.46-1.5-.97-.24-2.54-2-3.4-1.15-.56-1.31-2.07-.67-3.26" />
                        <path d="M2 11c.76.66 1.83 1.27 3.09 1.27 2.6 0 3.12.5 3.12 2.48s0 1.99.52 3.48c.34.97.46 1.94-.22 2.77" />
                        <path d="m19.9 19.93 2.1 2.07m-.89-4.95a4.05 4.05 0 1 1-8.11 0 4.05 4.05 0 0 1 8.11 0Z" />
                      </svg>
                    ) : (
                      <span className="ui-thinkc__dot" />
                    )}
                  </span>
                  <div className="ui-thinkc__content">
                    <span className={isActive ? "ui-thinkc__label ui-thinkc__shimmer" : "ui-thinkc__label"}
                      data-text={step.label} dir="auto">{step.label}</span>
                    {isActive && step.startedAtMs != null && (
                      <>
                        {" "}
                        <Elapsed since={step.startedAtMs} />
                      </>
                    )}
                    {step.meta && <span className="ui-thinkc__time"> · {step.meta}</span>}
                    {!!step.chips?.length && (
                      <div className="ui-thinkc__sources">
                        {step.chips.map(chip => (
                          <span key={chip} className="ui-thinkc__source" data-count>
                            <span className="ui-thinkc__source-label" dir="auto" title={chip}>{chip}</span>
                          </span>
                        ))}
                      </div>
                    )}
                    {step.detail}
                  </div>
                </li>
              );
            })}
          </ol>
          )}
        </div>
      </div>
    </div>
  );
}

/** Twinkle order of the 3×3 pixel mark – a diagonal wave */
const PIXEL_DELAYS = [0, 120, 240, 120, 240, 360, 240, 360, 480];

function Elapsed({ since }: { since: number }) {
  const now = useNow(true);
  return now == null ? null : <span className="ui-thinkc__time">{formatElapsed(now - since)}</span>;
}

/* ---------- Styles ---------- */

const css = /* css */ `
/* Colors and motion as variables – override them on .ui-thinkc (see Theming in the docs) */
.ui-thinkc {
  --ui-tkc-card: #ffffff;
  --ui-tkc-ink: var(--aui-ink, rgba(0, 0, 0, 0.88));
  --ui-tkc-strong: #000000;
  --ui-tkc-text: var(--aui-muted, rgba(0, 0, 0, 0.61));
  --ui-tkc-muted: var(--aui-muted, rgba(0, 0, 0, 0.45));
  --ui-tkc-faint: rgba(0, 0, 0, 0.27);
  --ui-tkc-icon: var(--aui-muted, rgba(0, 0, 0, 0.447));
  --ui-tkc-line: var(--aui-border, rgba(0, 0, 0, 0.06));
  --ui-tkc-rail: var(--aui-border, rgba(0, 0, 0, 0.08));
  --ui-tkc-fill: rgba(0, 0, 0, 0.06);
  --ui-tkc-wash: var(--aui-subtle, rgba(0, 0, 0, 0.03));
  --ui-tkc-accent: var(--aui-ink, rgba(0, 0, 0, 0.84));
  --ui-tkc-shine: rgba(255, 255, 255, 0.82);
  /* Strokes are shadows: a 0.5px hairline plus a soft lift */
  --ui-tkc-shadow: var(--aui-shadow-card, 0 0 0 0.5px rgba(0, 0, 0, 0.06), 0 1px 1px -1px rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.05));
  --ui-tkc-shadow-pop: 0 0 0 0.5px rgba(0, 0, 0, 0.08), 0 12px 28px -10px rgba(0, 0, 0, 0.16), 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --ui-tkc-ring: 0 0 0 0.5px rgba(0, 0, 0, 0.1);
  --ui-tkc-focus: var(--aui-focus, rgba(0, 0, 0, 0.72));
  --ui-tkc-ease: var(--aui-ease, cubic-bezier(0.22, 1, 0.36, 1));

  position: relative;
  box-sizing: border-box;
  container-type: inline-size;
  width: 100%;
  max-width: 100%;
  /* No card: it sits straight on the page */
  font-family: var(--aui-font, "Inter", "InterVariable", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif);
  font-size: 13px;
  line-height: 20px;
  font-weight: 400;
  color: var(--ui-tkc-ink);
  -webkit-font-smoothing: antialiased;
}
.ui-thinkc *,
.ui-thinkc *::before,
.ui-thinkc *::after {
  box-sizing: border-box;
}
:where(.ui-thinkc) button { margin: 0; padding: 0; border: 0; background: none; font: inherit; color: inherit; cursor: pointer; }
:where(.ui-thinkc) svg { display: block; flex: none; }
.ui-thinkc button:focus-visible,
.ui-thinkc a:focus-visible {
  outline: 2px solid var(--ui-tkc-focus);
  outline-offset: 2px;
}

/* Header row: pixel mark + "Thinking 4s" / "Worked for 18s" + chevron – only as wide as its words, so only they take the hover */
.ui-thinkc__head {
  display: flex;
  width: fit-content;
  align-items: center;
  gap: 10px;
  max-width: 100%;
  height: 36px;
  padding: 0 8px 0 0;
  border-radius: calc(var(--aui-radius, 7px) + 1px);
  text-align: left;
}
.ui-thinkc__mark {
  display: grid;
  grid-template-columns: repeat(3, 3px);
  grid-auto-rows: 3px;
  gap: 1.5px;
  place-content: center;
  width: 16px;
  height: 16px;
}
.ui-thinkc__mark i {
  border-radius: 0.75px;
  background: var(--ui-tkc-accent);
  animation: ui-thinkc-pixel 1.2s ease-in-out infinite both;
}
.ui-thinkc[data-done] .ui-thinkc__mark i {
  animation: ui-thinkc-settle 420ms var(--ui-tkc-ease) both;
}
.ui-thinkc__title {
  display: inline-flex;
  min-width: 0;
  gap: 8px;
  font-weight: 500;
  white-space: nowrap;
  color: var(--ui-tkc-ink);
  transition: color 160ms ease;
  animation: ui-thinkc-in 420ms var(--ui-tkc-ease) both;
}
/* Hover: no fill – the words just lighten */
.ui-thinkc__head:hover .ui-thinkc__title { color: var(--ui-tkc-muted); }
.ui-thinkc__title .ui-thinkc__shimmer {
  color: var(--ui-tkc-muted);
}
.ui-thinkc__time {
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  color: var(--aui-placeholder, var(--ui-tkc-faint));
}
/* The chevron sits right after the words so collapsed "Worked for Xm >" is always discoverable */
.ui-thinkc__chevron {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  margin-left: -4px;
  color: var(--ui-tkc-icon);
  opacity: 0.5;
  transition: opacity 160ms ease;
}
.ui-thinkc__head:is(:hover, :focus-visible) .ui-thinkc__chevron,
.ui-thinkc__head[aria-expanded="true"] .ui-thinkc__chevron { opacity: 0.85; }
.ui-thinkc__chevron svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.1;
  stroke-linecap: round;
  stroke-linejoin: round;
  transform: rotate(-90deg);
  transition: transform 260ms var(--ui-tkc-ease);
}
.ui-thinkc__head[aria-expanded="true"] .ui-thinkc__chevron svg {
  transform: none;
}

/* Inline progress ring + N/M steps pill beside the chevron */
.ui-thinkc__steps-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 20px;
  padding: 0 7px 0 5px;
  border-radius: 999px;
  background: var(--ui-tkc-wash);
  box-shadow: inset 0 0 0 0.5px var(--ui-tkc-line);
  font-size: 11.5px;
  line-height: 16px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--ui-tkc-text);
  white-space: nowrap;
}
.ui-thinkc__ring {
  width: 13px;
  height: 13px;
  transform: rotate(-90deg);
}
.ui-thinkc__ring-track {
  fill: none;
  stroke: currentColor;
  stroke-opacity: 0.2;
  stroke-width: 1.75;
}
.ui-thinkc__ring-arc {
  fill: none;
  stroke: var(--ui-tkc-accent);
  stroke-width: 1.75;
  stroke-linecap: round;
  transition: stroke-dashoffset 280ms var(--ui-tkc-ease), stroke 200ms ease;
}
.ui-thinkc__steps-badge[data-tone="done"] .ui-thinkc__ring-arc {
  stroke: var(--ui-tkc-ink);
}
.ui-thinkc__steps-badge[data-tone="error"] .ui-thinkc__ring-arc {
  stroke: var(--aui-danger, #dc2626);
}
.ui-thinkc__steps-count {
  color: var(--ui-tkc-text);
}

/* Dynamic progress checklist inside the collapsible body */
.ui-thinkc__plan {
  margin: 0;
  padding: 6px 0 8px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ui-thinkc__plan[data-has-trail] {
  margin-bottom: 4px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--ui-tkc-line);
}
.ui-thinkc__plan-item {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  line-height: 18px;
  color: var(--ui-tkc-text);
}
.ui-thinkc__plan-icon {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
}
.ui-thinkc__plan-check {
  width: 14px;
  height: 14px;
}
.ui-thinkc__plan-check circle {
  fill: var(--ui-tkc-fill);
  stroke: var(--ui-tkc-muted);
  stroke-width: 1.25;
}
.ui-thinkc__plan-check path {
  fill: none;
  stroke: var(--ui-tkc-ink);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.ui-thinkc__plan-pulse {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--ui-tkc-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ui-tkc-accent) 22%, transparent);
  animation: ui-thinkc-pulse 1.1s ease-in-out infinite;
}
.ui-thinkc__plan-pending {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  border: 1.4px solid var(--ui-tkc-faint);
}
.ui-thinkc__plan-fail {
  width: 14px;
  height: 14px;
}
.ui-thinkc__plan-fail circle {
  fill: rgba(220, 38, 38, 0.12);
  stroke: var(--aui-danger, #dc2626);
  stroke-width: 1.25;
}
.ui-thinkc__plan-fail path {
  fill: none;
  stroke: var(--aui-danger, #dc2626);
  stroke-width: 1.5;
  stroke-linecap: round;
}
.ui-thinkc__plan-skip {
  width: 14px;
  height: 14px;
}
.ui-thinkc__plan-skip circle,
.ui-thinkc__plan-skip path {
  fill: none;
  stroke: var(--ui-tkc-faint);
  stroke-width: 1.25;
  stroke-linecap: round;
}
.ui-thinkc__plan-item[data-status="in_progress"] .ui-thinkc__plan-title {
  color: var(--ui-tkc-ink);
  font-weight: 500;
}
.ui-thinkc__plan-item[data-status="done"] .ui-thinkc__plan-title {
  color: var(--ui-tkc-text);
}
.ui-thinkc__plan-item[data-status="pending"] .ui-thinkc__plan-title {
  color: var(--ui-tkc-muted);
}
.ui-thinkc__plan-item[data-status="skipped"] .ui-thinkc__plan-title {
  color: var(--ui-tkc-muted);
  text-decoration: line-through;
}
.ui-thinkc__plan-item[data-status="failed"] .ui-thinkc__plan-title {
  color: var(--aui-danger, #dc2626);
}


/* Body: folds away under a hairline – only this part animates and clips */
.ui-thinkc__body {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows 360ms var(--ui-tkc-ease), opacity 260ms ease;
}
.ui-thinkc__body[data-open="false"] {
  grid-template-rows: 0fr;
  opacity: 0;
}
.ui-thinkc__clip {
  min-height: 0;
  /* clips only while folded, so tooltips can reach out when open */
  overflow: visible;
}
.ui-thinkc__body[data-open="false"] .ui-thinkc__clip {
  overflow: hidden;
}
.ui-thinkc__list {
  margin: 0;
  padding: 6px 0 0;
  list-style: none;
}

/* Timeline: icon column with a thin rail growing down to the next node */
.ui-thinkc__item {
  position: relative;
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 10px;
  padding-bottom: 12px;
  animation: ui-thinkc-in 520ms var(--ui-tkc-ease) both;
}
.ui-thinkc__item:not(:last-child)::before {
  content: "";
  position: absolute;
  left: 7.5px;
  top: 22px;
  bottom: 2px;
  width: 1px;
  background: var(--ui-tkc-rail);
  transform-origin: top;
  animation: ui-thinkc-line 520ms var(--ui-tkc-ease) both;
}
.ui-thinkc__node {
  display: grid;
  place-items: center;
  width: 16px;
  height: 20px;
}
.ui-thinkc__globe {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: var(--ui-tkc-icon);
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* A finished step is a small gray dot, the running one a monochrome pixel that pulses */
.ui-thinkc__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--ui-tkc-faint);
  transition: background-color 300ms ease, border-radius 300ms ease;
}
.ui-thinkc__item[data-active] .ui-thinkc__dot {
  width: 6px;
  height: 6px;
  border-radius: 1.5px;
  background: var(--ui-tkc-accent);
  animation: ui-thinkc-pulse 1s ease-in-out infinite;
}
.ui-thinkc__item[data-kind="error"] .ui-thinkc__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--aui-danger, #dc2626);
}
/* Colleague interim prose: clean readable body copy with breathing room, zero heavy chrome */
.ui-thinkc__item[data-kind="note"] {
  padding-top: 2px;
  padding-bottom: 14px;
}
.ui-thinkc__item[data-kind="note"]:not(:last-child)::before {
  top: 0;
  bottom: 0;
}
.ui-thinkc__item[data-kind="note"] .ui-thinkc__label {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--ui-tkc-ink);
}
.ui-thinkc__item[data-kind="thinking"] {
  padding-top: 2px;
  padding-bottom: 6px;
}
.ui-thinkc__item[data-kind="thinking"] .ui-thinkc__label {
  font-weight: 500;
  color: var(--ui-tkc-muted);
}
/* Collapsible per-step receipt disclosure keeps verbose evidence compact by default */
.ui-thinkc__receipt {
  margin-top: 6px;
}
.ui-thinkc__receipt-summary {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  line-height: 16px;
  color: var(--ui-tkc-muted);
  cursor: pointer;
  list-style: none;
  user-select: none;
  transition: color 140ms ease;
}
.ui-thinkc__receipt-summary::-webkit-details-marker {
  display: none;
}
.ui-thinkc__receipt-summary:hover {
  color: var(--ui-tkc-ink);
}
.ui-thinkc__receipt-chevron {
  width: 12px;
  height: 12px;
  transition: transform 200ms var(--ui-tkc-ease);
}
.ui-thinkc__receipt[open] > .ui-thinkc__receipt-summary .ui-thinkc__receipt-chevron {
  transform: rotate(90deg);
}
.ui-thinkc__check {
  width: 16px;
  height: 16px;
  animation: ui-thinkc-pop 460ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.ui-thinkc__check circle {
  fill: var(--ui-tkc-accent);
}
.ui-thinkc__check path {
  fill: none;
  stroke: var(--aui-on-primary, #fff);
  stroke-width: 1.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 9;
  stroke-dashoffset: 9;
  animation: ui-thinkc-draw 360ms var(--ui-tkc-ease) 180ms forwards;
}

.ui-thinkc__content {
  min-width: 0;
}
.ui-thinkc__label {
  position: relative;
  display: inline-block;
  max-width: 100%;
  overflow-wrap: anywhere;
  white-space: pre-line;
  text-align: start;
  color: var(--ui-tkc-text);
  transition: color 300ms ease;
}
/* The running step: gray with a darker band sweeping through */
.ui-thinkc__item[data-active] .ui-thinkc__label {
  color: var(--ui-tkc-muted);
}
.ui-thinkc__item[data-kind="done"] .ui-thinkc__label {
  font-weight: 500;
  color: var(--ui-tkc-ink);
}

/* Sources: small white chips that pop in one after another */
.ui-thinkc__sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  padding: 1px 0 2px;
}
.ui-thinkc__source {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  height: 26px;
  padding: 0 8px 0 6px;
  border-radius: calc(var(--aui-radius-sm, 5px) + 1px);
  background: var(--aui-surface, var(--ui-tkc-card));
  box-shadow: var(--ui-tkc-shadow);
  font-size: 12px;
  line-height: 16px;
  color: var(--ui-tkc-ink);
  text-decoration: none;
  animation: ui-thinkc-chip 420ms var(--ui-tkc-ease) both;
}
a.ui-thinkc__source,
.ui-thinkc__more {
  position: relative;
  cursor: pointer;
  transition: background-color 160ms ease, color 160ms ease;
}
a.ui-thinkc__source:hover {
  background: var(--ui-tkc-wash);
}
/* "+3 more" – the quiet chip with an inner hairline */
.ui-thinkc .ui-thinkc__more {
  padding: 0 8px;
  background: none;
  box-shadow: inset 0 0 0 0.5px var(--ui-tkc-line);
  font-size: 12px;
  font-weight: 500;
  color: var(--ui-tkc-text);
}
.ui-thinkc .ui-thinkc__more:hover {
  background: var(--ui-tkc-wash);
  color: var(--ui-tkc-ink);
}
.ui-thinkc .ui-thinkc__more[aria-expanded="true"] {
  background: var(--ui-tkc-fill);
  color: var(--ui-tkc-ink);
}

/* Tooltip above the chip – a small white popover */
.ui-thinkc__tip {
  position: absolute;
  left: 50%;
  bottom: calc(100% + 6px);
  z-index: 2;
  padding: 4px 8px;
  border-radius: 6px;
  background: var(--ui-tkc-card);
  box-shadow: var(--ui-tkc-shadow-pop);
  color: var(--ui-tkc-text);
  font-size: 12px;
  line-height: 16px;
  width: max-content;
  max-width: min(320px, 80vw);
  overflow-wrap: anywhere;
  pointer-events: none;
  opacity: 0;
  transform: translate(-50%, 4px);
  transition: opacity 140ms ease, transform 200ms var(--ui-tkc-ease);
}
.ui-thinkc__source:hover .ui-thinkc__tip,
.ui-thinkc__source:focus-visible .ui-thinkc__tip {
  opacity: 1;
  transform: translate(-50%, 0);
  transition-delay: 250ms;
}

.ui-thinkc__source[data-count] {
  padding: 0 8px;
  background: none;
  box-shadow: inset 0 0 0 0.5px var(--ui-tkc-line);
  color: var(--ui-tkc-text);
}
.ui-thinkc__source-label {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ui-thinkc__favicon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.ui-thinkc__favicon {
  display: grid;
  place-items: center;
  flex: none;
  width: 14px;
  height: 14px;
  border-radius: 4px;
  overflow: hidden;
  box-shadow: var(--ui-tkc-ring);
}
.ui-thinkc__favicon svg {
  width: 100%;
  height: 100%;
}

/* Shimmer over the working label – a darker band runs through the gray text */
.ui-thinkc__shimmer {
  position: relative;
}
.ui-thinkc__shimmer::after {
  content: attr(data-text);
  content: attr(data-text) / "";
  position: absolute;
  inset: 0;
  /* wraps exactly like the text below it, so a long label keeps its sweep inside the card */
  white-space: inherit;
  overflow-wrap: inherit;
  color: transparent;
  background: linear-gradient(90deg, transparent 38%, var(--ui-tkc-shine) 50%, transparent 62%) 100% 0 / 300% 100%
    no-repeat;
  -webkit-background-clip: text;
  background-clip: text;
  animation: ui-thinkc-sweep 1.6s linear infinite;
  pointer-events: none;
}

@keyframes ui-thinkc-in {
  from { opacity: 0; transform: translateY(6px); filter: blur(3px); }
  to { opacity: 1; transform: none; filter: none; }
}
@keyframes ui-thinkc-line {
  from { transform: scaleY(0); }
  to { transform: scaleY(1); }
}
@keyframes ui-thinkc-chip {
  from { opacity: 0; transform: translateY(4px) scale(0.92); }
  to { opacity: 1; transform: none; }
}
@keyframes ui-thinkc-pulse {
  50% { transform: scale(0.7); opacity: 0.45; }
}
@keyframes ui-thinkc-pixel {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.2; }
}
@keyframes ui-thinkc-settle {
  from { opacity: 0.2; transform: scale(0.6); }
  to { opacity: 1; transform: none; }
}
@keyframes ui-thinkc-pop {
  0% { transform: scale(0.5); }
  60% { transform: scale(1.12); }
  100% { transform: scale(1); }
}
@keyframes ui-thinkc-draw {
  to { stroke-dashoffset: 0; }
}
@keyframes ui-thinkc-sweep {
  from { background-position: 100% 0; }
  to { background-position: 0% 0; }
}

/* Narrow (phones) */
@container (max-width: 360px) {
  .ui-thinkc__head { padding: 0 8px 0 0; }
  .ui-thinkc__list { padding: 6px 0 0; }
}
/* Touch screens: bigger tap targets */
@media (pointer: coarse) {
  .ui-thinkc__head { height: 52px; }
  .ui-thinkc__source { height: 32px; }
}
@media (prefers-reduced-motion: reduce) {
  .ui-thinkc *,
  .ui-thinkc *::before,
  .ui-thinkc *::after {
    animation-duration: 1ms !important;
    animation-delay: 0ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
  .ui-thinkc__shimmer::after {
    display: none;
  }
  .ui-thinkc__check path {
    stroke-dashoffset: 0;
  }
}

/* Dark mode: follows a .dark class or data-theme="dark" on any ancestor, e.g. <html> */
:where(.dark, [data-theme="dark"]) .ui-thinkc {
  --ui-tkc-card: #1c1c1e;
  --ui-tkc-ink: var(--aui-ink, rgba(255, 255, 255, 0.9));
  --ui-tkc-strong: #ffffff;
  --ui-tkc-text: var(--aui-muted, rgba(255, 255, 255, 0.62));
  --ui-tkc-muted: var(--aui-muted, rgba(255, 255, 255, 0.46));
  --ui-tkc-faint: rgba(255, 255, 255, 0.3);
  --ui-tkc-icon: var(--aui-muted, rgba(255, 255, 255, 0.5));
  --ui-tkc-line: var(--aui-border, rgba(255, 255, 255, 0.08));
  --ui-tkc-rail: var(--aui-border, rgba(255, 255, 255, 0.1));
  --ui-tkc-fill: rgba(255, 255, 255, 0.08);
  --ui-tkc-wash: var(--aui-subtle, rgba(255, 255, 255, 0.04));
  --ui-tkc-accent: var(--aui-ink, rgba(255, 255, 255, 0.88));
  --ui-tkc-shine: #ffffff;
  --ui-tkc-shadow: var(--aui-shadow-card, 0 0 0 0.5px rgba(255, 255, 255, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.4));
  --ui-tkc-shadow-pop: 0 0 0 0.5px rgba(255, 255, 255, 0.12), 0 12px 28px -10px rgba(0, 0, 0, 0.6);
  --ui-tkc-ring: 0 0 0 0.5px rgba(255, 255, 255, 0.14);
  --ui-tkc-focus: var(--aui-focus, rgba(255, 255, 255, 0.75));
}
:where(.dark, [data-theme="dark"]) .ui-thinkc__tip {
  background: #232326;
}
`;
