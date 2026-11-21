// components/ui/tool-call-card-clean.tsx
"use client";

import { useTranslation } from "react-i18next";
import {
  Children,
  isValidElement,
  useId,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

/** Clean disclosure for ordered, server-reported tool receipts. */

export type ToolCallStatus = "accepted" | "queued" | "running" | "success" | "error" | "cancelled" | "unknown" | "notExecuted" | "pending" | "denied" | "approved" | "versionSaved" | "outputGenerated" | "delivered";

export type ToolCallCardProps = {
  /** Tool name as the agent calls it, shown in mono – e.g. "search_web" */
  name: string;
  /** Short human summary – e.g. "Searched the web for 'CRM pricing 2026'" */
  summary?: ReactNode;
  /** Icon in the tile on the left – defaults to a wrench */
  icon?: ReactNode;
  status: ToolCallStatus;
  /** User-facing details from the persisted receipt, including fixed media/version links. */
  children?: ReactNode;
  /** Duration reported by the receipt, in milliseconds */
  duration?: number;
  /** Start expanded (uncontrolled) */
  defaultOpen?: boolean;
  /** Expanded state (controlled) */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Opens the card when the call fails and closes it again on the next run, unless someone toggled it */
  openOnError?: boolean;
  className?: string;
};

export type ToolCallGroupProps = {
  /** ToolCallCard elements in native call order, keyed by call ID */
  children: ReactNode;
  /** Group heading when no call is running */
  label?: string;
  /** Label while any call is running */
  runningLabel?: string;
  /** Optional elapsed time reported for this group, in milliseconds */
  duration?: number;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
};

/* ---------- Card ---------- */

export function ToolCallCard({
  name,
  summary,
  icon,
  status,
  children,
  duration,
  defaultOpen = false,
  open: openProp,
  onOpenChange,
  openOnError = true,
  className,
}: ToolCallCardProps) {
  const id = useId();
  const [openState, setOpenState] = useState(defaultOpen);
  const open = openProp ?? openState;
  const setOpen = (next: boolean) => {
    if (openProp === undefined) setOpenState(next);
    onOpenChange?.(next);
  };

  // Open on failure, close again on the next run – only while nobody has toggled it by hand
  const [prevStatus, setPrevStatus] = useState(status);
  const [autoOpened, setAutoOpened] = useState(false);
  if (status !== prevStatus) {
    setPrevStatus(status);
    if (openProp === undefined && openOnError) {
      if (status === "error" && !openState) {
        setOpenState(true);
        setAutoOpened(true);
      } else if (prevStatus === "error" && autoOpened) {
        setOpenState(false);
        setAutoOpened(false);
      }
    }
  }

  const { t } = useTranslation();
  const statusLabel = t(`agentReceipt.${status}`);
  return (
    <div
      className={["ui-tclc", className].filter(Boolean).join(" ")}
      data-status={status}
      data-open={open || undefined}
    >
      {/* React 19 hoists this into <head> once, no matter how many cards render */}
      <style href="ui-tool-call-clean" precedence="default">
        {css}
      </style>
      <span className="ui-tclc-sr" role="status" aria-live="polite">
        {name} · {statusLabel}
      </span>

      <button
        type="button"
        className="ui-tclc__head"
        aria-expanded={open}
        aria-controls={`${id}-body`}
        onClick={() => {
          setAutoOpened(false);
          setOpen(!open);
        }}
      >
        <span className="ui-tclc__icon" aria-hidden="true">
          {icon ?? <WrenchIcon />}
        </span>
        <span className="ui-tclc__main">
          <code className="ui-tclc__name" title={name}>
            {name}
          </code>
          {summary != null && (
            <span className="ui-tclc__summary" dir="auto" title={typeof summary === "string" ? summary : undefined}>
              {summary}
            </span>
          )}
        </span>
        <span className="ui-tclc__status" key={status}>
          {status === "running" && <Spinner />}
          {status === "success" && (
            <svg className="ui-tclc__ok" viewBox="0 0 16 16" aria-hidden="true">
              <circle cx="8" cy="8" r="7" />
              <path d="M5.1 8.2 7.1 10.1 10.9 6" pathLength={1} />
            </svg>
          )}
          {status === "error" && <ErrorIcon />}
          <span className="ui-tclc__time">
            {statusLabel}{duration != null && ` · ${formatMs(duration)}`}
          </span>
        </span>
        <Chevron />
      </button>

      <div className="ui-tclc__body" id={`${id}-body`} inert={!open}>
        <div className="ui-tclc__clip">
          <div className="ui-tclc__sections">
            {children ?? statusLabel}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- Group ---------- */

export function ToolCallGroup({
  children,
  label,
  runningLabel,
  duration,
  defaultOpen = false,
  open: openProp,
  onOpenChange,
  className,
}: ToolCallGroupProps) {
  const id = useId();
  const [openState, setOpenState] = useState(defaultOpen);
  const open = openProp ?? openState;

  // Read the cards' props to summarise them in the header
  const calls = Children.toArray(children)
    .filter(isValidElement)
    .map((c) => (c as ReactElement<Partial<ToolCallCardProps>>).props);
  const running = calls.some((c) => c.status === "running");
  const { t } = useTranslation();
  const title = (running ? runningLabel : undefined) ?? label ?? t("agentReceipt.group", { count: calls.length });
  const icons = calls.slice(-3);

  return (
    <div
      className={["ui-tclc-group", className].filter(Boolean).join(" ")}
      data-running={running || undefined}
      data-open={open || undefined}
    >
      <style href="ui-tool-call-clean" precedence="default">
        {css}
      </style>
      <span className="ui-tclc-sr" role="status" aria-live="polite">
        {title}
      </span>

      <button
        type="button"
        className="ui-tclc-group__head"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        onClick={() => {
          if (openProp === undefined) setOpenState(!open);
          onOpenChange?.(!open);
        }}
      >
        <span className="ui-tclc-group__stack" aria-hidden="true">
          {icons.map((c, i) => (
            <span className="ui-tclc__icon" key={calls.length - icons.length + i}>
              {c.icon ?? <WrenchIcon />}
            </span>
          ))}
        </span>
        <span className="ui-tclc-group__title" key={running ? "busy" : "done"}>
          <span className={running ? "ui-tclc-group__label ui-tclc__shine" : "ui-tclc-group__label"} data-text={title}>
            {title}
          </span>
          {duration != null && <span className="ui-tclc-group__time">· {formatMs(duration)}</span>}
        </span>
        <Chevron />
      </button>

      <div className="ui-tclc__body" id={`${id}-list`} inert={!open}>
        <div className="ui-tclc__clip">
          <div className="ui-tclc-group__list">{children}</div>
        </div>
      </div>
    </div>
  );
}

/* ---------- Pieces ---------- */

function Spinner() {
  return (
    <svg className="ui-tclc__spinner" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 2a6 6 0 0 1 6 6" />
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg className="ui-tclc__err" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="7" />
      <path d="M8 4.9v3.5M8 10.9v.1" />
    </svg>
  );
}

function Chevron() {
  return (
    <svg className="ui-tclc__chevron" viewBox="0 0 12 12" aria-hidden="true">
      <path d="M3.5 5.25 6 7.75l2.5-2.5" />
    </svg>
  );
}

function WrenchIcon() {
  return (
    <svg viewBox="0 0 16 16">
      <path d="M10.2 2.4a3.5 3.5 0 0 0-4.3 4.6L2.6 10.3a1.4 1.4 0 0 0 2 2L7.9 9a3.5 3.5 0 0 0 4.6-4.3l-2 2-1.6-.4-.4-1.6 1.7-2.3Z" />
    </svg>
  );
}

/* ---------- Helpers ---------- */

function formatMs(ms: number) {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(Math.floor(ms / 100) / 10).toFixed(1)}s`;
  const s = Math.floor(ms / 1000);
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
  const h = Math.floor(s / 3600);
  if (h < 24) return `${h}h ${String(Math.floor(s / 60) % 60).padStart(2, "0")}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

const css = /* css */ `
.ui-tclc,
.ui-tclc-group {
  --ui-tclc-card: #ffffff;
  --ui-tclc-strong: var(--aui-ink, #000000);
  --ui-tclc-ink: var(--aui-ink, rgba(0, 0, 0, 0.88));
  --ui-tclc-text: var(--aui-muted, rgba(0, 0, 0, 0.61));
  --ui-tclc-muted: var(--aui-muted, rgba(0, 0, 0, 0.45));
  --ui-tclc-faint: var(--aui-placeholder, rgba(0, 0, 0, 0.27));
  --ui-tclc-icon: var(--aui-muted, rgba(0, 0, 0, 0.447));
  --ui-tclc-line: var(--aui-border, rgba(0, 0, 0, 0.06));
  --ui-tclc-wash: var(--aui-subtle, rgba(0, 0, 0, 0.03));
  --ui-tclc-wash-big: var(--aui-subtle, rgba(0, 0, 0, 0.015));
  --ui-tclc-code: #fafafa;
  --ui-tclc-accent: rgba(0, 96, 226, 0.765);
  --ui-tclc-red: var(--aui-red, #f04438);
  --ui-tclc-red-bg: color-mix(in srgb, var(--aui-red, #f04438) 4%, transparent);
  --ui-tclc-red-line: color-mix(in srgb, var(--aui-red, #f04438) 14%, transparent);
  --ui-tclc-key: rgba(0, 0, 0, 0.88);
  --ui-tclc-str: color-mix(in srgb, var(--aui-cyan, #14b3f0) 90%, transparent);
  --ui-tclc-num: var(--aui-warning, #b25e00);
  --ui-tclc-lit: var(--aui-purple, #a651f0);
  --ui-tclc-shine: rgba(255, 255, 255, 0.82);
  --ui-tclc-shadow: 0 0 0 0.5px rgba(0, 0, 0, 0.06), 0 1px 1px -1px rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --ui-tclc-focus: var(--aui-focus, rgba(0, 96, 226, 0.7));
  --ui-tclc-ease: var(--aui-ease, cubic-bezier(0.22, 1, 0.36, 1));
  --ui-tclc-mono: var(--aui-font-mono, ui-monospace, "SF Mono", Menlo, monospace);
  box-sizing: border-box;
  container-type: inline-size;
  min-width: 0;
  color: var(--ui-tclc-ink);
  font-family: var(--aui-font, "Inter", "InterVariable", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif);
  font-size: 13px;
  line-height: 20px;
  font-weight: 400;
  -webkit-font-smoothing: antialiased;
}
.ui-tclc *,
.ui-tclc-group * { box-sizing: border-box; }

.ui-tclc {
  position: relative;
  border-radius: var(--aui-radius-lg, 10px);
  background: var(--aui-surface, var(--ui-tclc-card));
  box-shadow: var(--aui-shadow-card, var(--ui-tclc-shadow));
}
.ui-tclc-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.ui-tclc__head {
  all: unset;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 44px;
  padding: 0 14px;
  border-radius: var(--aui-radius-lg, 10px);
  cursor: pointer;
  transition: background-color 160ms ease, border-radius 0ms linear 380ms;
}
.ui-tclc[data-open] .ui-tclc__head {
  border-radius: var(--aui-radius-lg, 10px) var(--aui-radius-lg, 10px) 0 0;
  transition: background-color 160ms ease;
}
.ui-tclc__head:focus-visible,
.ui-tclc-group__head:focus-visible {
  outline: 2px solid var(--ui-tclc-focus);
  outline-offset: 2px;
}
@media (hover: hover) {
  .ui-tclc__head:hover { background: var(--ui-tclc-wash-big); }
  .ui-tclc__head:hover .ui-tclc__chevron { stroke: var(--ui-tclc-ink); }
  .ui-tclc-group__head:hover { background: var(--ui-tclc-wash); color: var(--ui-tclc-ink); }
}
.ui-tclc__icon {
  display: grid;
  place-items: center;
  flex: none;
  width: 16px;
  height: 16px;
  color: var(--ui-tclc-icon);
}
.ui-tclc__icon > svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.4; stroke-linecap: round; stroke-linejoin: round; }

.ui-tclc__main {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.ui-tclc__name {
  flex: 0 1 auto;
  max-width: 55%;
  overflow: hidden;
  color: var(--ui-tclc-strong);
  font-family: var(--ui-tclc-mono);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ui-tclc__summary {
  flex: 1 1 0;
  min-width: 0;
  overflow: hidden;
  color: var(--ui-tclc-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ui-tclc__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
  color: var(--ui-tclc-muted);
  font-size: 12px;
  line-height: 16px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  animation: ui-tclc-in 360ms var(--ui-tclc-ease) both;
}
.ui-tclc[data-status="error"] .ui-tclc__status { color: var(--ui-tclc-red); font-weight: 500; }
.ui-tclc__status > svg { width: 14px; height: 14px; flex: none; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.ui-tclc__spinner circle { stroke: var(--ui-tclc-line); stroke-width: 1.6; }
.ui-tclc__spinner path { stroke: var(--ui-tclc-accent); stroke-width: 1.6; }
.ui-tclc__spinner { animation: ui-tclc-spin 800ms linear infinite; }
.ui-tclc__ok { animation: ui-tclc-pop 460ms cubic-bezier(0.34, 1.56, 0.64, 1) both; }
.ui-tclc__ok circle { fill: var(--ui-tclc-accent); }
.ui-tclc__ok path { stroke: #fff; stroke-width: 1.5; stroke-dasharray: 1; stroke-dashoffset: 1; animation: ui-tclc-draw 360ms var(--ui-tclc-ease) 160ms forwards; }
.ui-tclc__err circle { fill: var(--ui-tclc-red); }
.ui-tclc__err path { stroke: #fff; stroke-width: 1.6; stroke-linecap: round; }

.ui-tclc__chevron {
  flex: none;
  width: 12px;
  height: 12px;
  fill: none;
  stroke: var(--ui-tclc-icon);
  stroke-width: 1.2;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: transform 360ms var(--ui-tclc-ease), stroke 160ms ease;
}
.ui-tclc[data-open] > .ui-tclc__head .ui-tclc__chevron,
.ui-tclc-group[data-open] > .ui-tclc-group__head .ui-tclc__chevron { transform: rotate(180deg); }
.ui-tclc__body {
  display: grid;
  grid-template-rows: 0fr;
  opacity: 0;
  transition: grid-template-rows 380ms var(--ui-tclc-ease), opacity 240ms ease;
}
.ui-tclc[data-open] > .ui-tclc__body,
.ui-tclc-group[data-open] > .ui-tclc__body {
  grid-template-rows: 1fr;
  opacity: 1;
}
.ui-tclc__clip { min-height: 0; overflow: hidden; }
.ui-tclc__sections {
  display: grid;
  gap: 14px;
  padding: 12px 14px 14px;
  border-top: 0.5px solid var(--ui-tclc-line);
}

.ui-tclc__section { display: grid; gap: 6px; min-width: 0; }
.ui-tclc-group { display: grid; }
.ui-tclc-group__head {
  all: unset;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 8px;
  justify-self: start;
  max-width: 100%;
  min-height: 32px;
  margin-left: -6px;
  padding: 4px 10px 4px 6px;
  border-radius: calc(var(--aui-radius, 7px) + 1px);
  color: var(--ui-tclc-ink);
  cursor: pointer;
  transition: background-color 160ms ease, color 160ms ease;
}
.ui-tclc-group__stack { display: flex; flex: none; padding: 0.5px; }
.ui-tclc-group__stack .ui-tclc__icon {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: var(--ui-tclc-card);
  box-shadow: var(--ui-tclc-shadow);
  animation: ui-tclc-pop 420ms var(--ui-tclc-ease) both;
}
.ui-tclc-group__stack .ui-tclc__icon + .ui-tclc__icon { margin-left: -4px; }
.ui-tclc-group__stack .ui-tclc__icon > svg { width: 12px; height: 12px; stroke-width: 1.5; }
.ui-tclc-group__title {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  white-space: nowrap;
  animation: ui-tclc-in 360ms var(--ui-tclc-ease) both;
}
.ui-tclc-group__label {
  position: relative;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: inherit;
  font-weight: 500;
}
.ui-tclc-group__label.ui-tclc__shine { color: var(--ui-tclc-muted); }
.ui-tclc-group__time { flex: none; color: var(--ui-tclc-faint); font-variant-numeric: tabular-nums; }
.ui-tclc-group__list { display: grid; gap: 8px; padding: 6px 0 2px; }
.ui-tclc__shine::after {
  content: attr(data-text);
  content: attr(data-text) / "";
  position: absolute;
  inset: 0;
  white-space: nowrap;
  color: transparent;
  background: linear-gradient(90deg, transparent 38%, var(--ui-tclc-shine) 50%, transparent 62%) 100% 0 / 300% 100% no-repeat;
  -webkit-background-clip: text;
  background-clip: text;
  animation: ui-tclc-sweep 1.8s linear infinite;
  pointer-events: none;
}

@keyframes ui-tclc-in {
  from { opacity: 0; transform: translateY(3px); filter: blur(2px); }
  to { opacity: 1; transform: none; filter: none; }
}
@keyframes ui-tclc-pop {
  from { opacity: 0; transform: scale(0.6); }
  to { opacity: 1; transform: none; }
}
@keyframes ui-tclc-spin { to { transform: rotate(360deg); } }
@keyframes ui-tclc-draw { to { stroke-dashoffset: 0; } }
@keyframes ui-tclc-sweep {
  from { background-position: 100% 0; }
  to { background-position: 0% 0; }
}
@container (max-width: 360px) {
  .ui-tclc__head { gap: 8px; padding: 0 12px; }
  .ui-tclc__sections { padding: 12px 12px 12px; }
}
@media (pointer: coarse) {
  .ui-tclc__head { min-height: 52px; }
}
@media (prefers-reduced-motion: reduce) {
  .ui-tclc *,
  .ui-tclc-group *,
  .ui-tclc *::after,
  .ui-tclc-group *::after {
    animation-duration: 1ms !important;
    animation-delay: 0ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
  .ui-tclc__shine::after { display: none; }
  .ui-tclc__ok path { stroke-dashoffset: 0; }
}
:where(.dark, [data-theme="dark"]) .ui-tclc, :where(.dark, [data-theme="dark"]) .ui-tclc-group {
  --ui-tclc-card: #1c1c1e;
  --ui-tclc-strong: var(--aui-ink, #ffffff);
  --ui-tclc-ink: var(--aui-ink, rgba(255, 255, 255, 0.9));
  --ui-tclc-text: var(--aui-muted, rgba(255, 255, 255, 0.62));
  --ui-tclc-muted: var(--aui-muted, rgba(255, 255, 255, 0.46));
  --ui-tclc-faint: var(--aui-placeholder, rgba(255, 255, 255, 0.3));
  --ui-tclc-icon: var(--aui-muted, rgba(255, 255, 255, 0.5));
  --ui-tclc-line: var(--aui-border, rgba(255, 255, 255, 0.08));
  --ui-tclc-wash: var(--aui-subtle, rgba(255, 255, 255, 0.04));
  --ui-tclc-wash-big: var(--aui-subtle, rgba(255, 255, 255, 0.025));
  --ui-tclc-code: #212123;
  --ui-tclc-accent: var(--aui-blue, #4fb0fe);
  --ui-tclc-red: var(--aui-danger, #ff8a7a);
  --ui-tclc-red-bg: color-mix(in srgb, var(--aui-red, #ff6b5f) 7%, transparent);
  --ui-tclc-red-line: color-mix(in srgb, var(--aui-red, #ff6b5f) 18%, transparent);
  --ui-tclc-key: rgba(255, 255, 255, 0.9);
  --ui-tclc-str: var(--aui-cyan, #5cc6ee);
  --ui-tclc-num: var(--aui-orange, #f2a15c);
  --ui-tclc-lit: #cfaff5;
  --ui-tclc-shine: #ffffff;
  --ui-tclc-shadow: 0 0 0 0.5px rgba(255, 255, 255, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.4);
  --ui-tclc-focus: var(--aui-focus, rgba(77, 141, 255, 0.8));
}
`;
