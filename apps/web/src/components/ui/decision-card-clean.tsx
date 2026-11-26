// components/ui/decision-card-clean.tsx
"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  ArrowUp,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Loader2,
  X,
} from "@/components/ui/icons";

import { Badge } from "@/components/ui/badge-clean";
import { Button } from "@/components/ui/button-clean";

/*
 * Decision Card – Clean style (AffectUI, Hugeicons & studio tokens).
 * Sits just above the chat composer as a card of its own:
 *   · compact head: "Needs you" badge with ? icon, optional task label, ← i / n → pager, fold (Later), and optional dismiss (×)
 *   · numbered option rows with optional summary, Recommended tag, and selected check/loading state
 *   · last row for custom freeform words with inline round send arrow
 *   · supports both AffectUI's immediate-decide mode and multi-question batch-review-then-submit mode
 *   · keyboard: 1–5 selects, ↑/↓ moves across rows and into the custom field, Esc folds to one line
 */

export type DecisionKind = "decision" | "pick" | "approval";

export type DecisionBlock = {
  x: number;
  y: number;
  w: number;
  h: number;
  r?: number;
  tone?: "ink" | "mid" | "soft";
};

export type DecisionOption = {
  id: string;
  title: string;
  /** Short reason shown muted below the option title */
  summary?: string;
  /** Small neutral Recommended tag – focus starts on this row */
  recommended?: boolean;
  /** pick: custom preview node or wireframe blocks */
  preview?: ReactNode;
  blocks?: DecisionBlock[];
};

export type Decision = {
  id: string;
  question: string;
  /** Optional context/group label shown muted in the header */
  task?: string;
  kind?: DecisionKind;
  options?: DecisionOption[];
  facts?: { label: string; value: string }[];
  /** Whether to show the custom freeform input row (default true) */
  allowOwn?: boolean;
};

export type DecisionAnswer = { option?: string; text?: string } | "approve" | "decline";

export type DecisionCardLabels = {
  needsYou: string;
  later: string;
  show: string;
  recommended: string;
  approve: string;
  decline: string;
  own: string;
  send: string;
  answered: string;
  previous: string;
  next: string;
  submit: string;
  skip: string;
  dismiss: string;
  allDone: string;
  waiting: (n: number) => string;
  of: (i: number, n: number) => string;
};

export type DecisionCardProps = {
  /** Open decisions in order. */
  decisions: Decision[];
  /** Immediate mode: called when one decision is answered. */
  onDecide?: (id: string, answer: DecisionAnswer) => void;
  /** Folded to one line via Later/chevron or Esc. */
  onLater?: (id: string) => void;
  /** Optional dismiss/bail channel (× in header, Skip in batch footer). */
  onDismiss?: () => void;
  /**
   * "immediate" (default): AffectUI stock mode — picking an option settles it right away.
   * "batch": multi-question review mode — picking records into `answers` and advances pages,
   * allowing ←/→ review before clicking Submit on the final page.
   */
  mode?: "immediate" | "batch";
  /** Controlled draft answers by decision id (batch mode). */
  answers?: Record<string, DecisionAnswer | undefined>;
  /** Called when an option or freeform text changes (batch mode). */
  onSelect?: (id: string, answer: DecisionAnswer | null) => void;
  /** Called when the user submits all batch answers. */
  onSubmitAll?: () => void;
  /** Whether batch submission is currently enabled. */
  canSubmit?: boolean;
  /** Disables controls and displays inline progress while submitting. */
  submitting?: boolean;
  /** Reset page index when this key changes (e.g. a new question group digest). */
  resetKey?: string | null;
  /** Start folded to one line. */
  defaultFolded?: boolean;
  /** Increment to unfold, pulse once, and focus the active row. */
  reveal?: number;
  labels?: Partial<DecisionCardLabels>;
  className?: string;
};

const LABELS: DecisionCardLabels = {
  needsYou: "Needs you",
  later: "Later",
  show: "Show",
  recommended: "Recommended",
  approve: "Approve",
  decline: "Decline",
  own: "Something else…",
  send: "Send",
  answered: "Answered",
  previous: "Previous",
  next: "Next",
  submit: "Submit",
  skip: "Skip",
  dismiss: "Dismiss",
  allDone: "Nothing else waits",
  waiting: (n) => (n === 1 ? "1 question waiting" : `${n.toLocaleString("en-US")} questions waiting`),
  of: (i, n) => `${i} / ${n}`,
};

type Row = {
  id: string;
  title: string;
  summary?: string;
  recommended?: boolean;
  preview?: ReactNode;
  blocks?: DecisionBlock[];
  answer: DecisionAnswer;
};

const rowsOf = (d: Decision, L: DecisionCardLabels): Row[] =>
  d.kind === "approval"
    ? [
        { id: "approve", title: L.approve, answer: "approve" },
        { id: "decline", title: L.decline, answer: "decline" },
      ]
    : (d.options ?? []).map((o) => ({ ...o, answer: { option: o.id } }));

const labelOf = (d: Decision, a: DecisionAnswer, L: DecisionCardLabels) =>
  a === "approve"
    ? L.approve
    : a === "decline"
      ? L.decline
      : a.option
        ? (d.options?.find((o) => o.id === a.option)?.title ?? a.option)
        : (a.text ?? "");

const Blocks = ({ blocks }: { blocks: DecisionBlock[] }) => (
  <svg className="ui-dcc__wire" viewBox="0 0 120 80" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    <rect className="ui-dcc__wire-page" x="0.5" y="0.5" width="119" height="79" rx="6" />
    {blocks.map((b, i) => (
      <rect key={i} data-tone={b.tone ?? "soft"} x={b.x} y={b.y} width={b.w} height={b.h} rx={b.r ?? 2} />
    ))}
  </svg>
);

export function DecisionCard({
  decisions,
  onDecide,
  onLater,
  onDismiss,
  mode = "immediate",
  answers,
  onSelect,
  onSubmitAll,
  canSubmit = false,
  submitting = false,
  resetKey,
  defaultFolded = false,
  reveal,
  labels,
  className,
}: DecisionCardProps) {
  const L: DecisionCardLabels = { ...LABELS, ...labels };
  const isBatch = mode === "batch";

  // Immediate mode: track locally answered items until caller drops them
  const [gone, setGone] = useState<ReadonlySet<string>>(() => new Set());
  const [pickedRowId, setPickedRowId] = useState<string | null>(null);
  useEffect(() => {
    if (isBatch) return;
    setGone((g) => {
      if (!g.size) return g;
      const ids = new Set(decisions.map((d) => d.id));
      const next = new Set([...g].filter((id) => ids.has(id)));
      return next.size === g.size ? g : next;
    });
  }, [decisions, isBatch]);

  useEffect(() => {
    if (!submitting) setPickedRowId(null);
  }, [submitting]);

  const open = isBatch ? decisions : decisions.filter((d) => !gone.has(d.id));
  const [curId, setCurId] = useState<string | null>(null);
  const [folded, setFolded] = useState(defaultFolded);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [pulse, setPulse] = useState(false);
  const [say, setSay] = useState("");

  useEffect(() => {
    setCurId(null);
    setFolded(defaultFolded);
  }, [resetKey, defaultFolded]);

  const index = Math.max(0, open.findIndex((d) => d.id === curId));
  const current = open[index] ?? null;
  const last = useRef(current);
  if (current) last.current = current;
  const shown = current ?? last.current;
  const viewMode = !current ? "none" : folded ? "min" : "full";

  const root = useRef<HTMLDivElement>(null);
  const want = useRef<"row" | "show" | "prev" | "next" | null>(null);
  const focusIn = useRef(false);
  focusIn.current = typeof document !== "undefined" && !!root.current?.contains(document.activeElement);

  const announce = (text: string) => setSay((s) => (s === text ? `${text}\u00A0` : text));

  useLayoutEffect(() => {
    const lost = focusIn.current && viewMode !== "none" && (!document.activeElement || document.activeElement === document.body);
    const w = want.current ?? (lost ? (viewMode === "min" ? "show" : "row") : null);
    want.current = null;
    if (!w) return;
    const box = root.current;
    const el =
      (w === "show" && box?.querySelector<HTMLElement>(".ui-dcc__show")) ||
      ((w === "prev" || w === "next") && box?.querySelector<HTMLElement>(`.ui-dcc__page[data-step="${w}"]`)) ||
      box?.querySelector<HTMLElement>('[role="option"][tabindex="0"], .ui-dcc__input');
    el?.focus({ preventScroll: true });
  });

  const firstReveal = useRef(reveal);
  useEffect(() => {
    if (reveal === firstReveal.current) return;
    firstReveal.current = reveal;
    setFolded(false);
    want.current = "row";
    setPulse(true);
    const t = window.setTimeout(() => setPulse(false), 700);
    return () => window.clearTimeout(t);
  }, [reveal]);

  const pageTo = (nextIndex: number, keepArrowFocus?: "prev" | "next") => {
    if (open.length < 2) return;
    const clamped = Math.max(0, Math.min(open.length - 1, nextIndex));
    if (keepArrowFocus && root.current?.contains(document.activeElement)) {
      want.current = keepArrowFocus;
    }
    setCurId(open[clamped].id);
  };

  const pageStep = (step: number) => {
    if (open.length < 2) return;
    const nextIndex = isBatch
      ? Math.max(0, Math.min(open.length - 1, index + step))
      : (index + step + open.length) % open.length;
    pageTo(nextIndex, step < 0 ? "prev" : "next");
  };

  const handleAnswer = (d: Decision, a: DecisionAnswer, rowId?: string) => {
    if (submitting) return;
    if (isBatch) {
      onSelect?.(d.id, a);
      announce(`${L.answered}: ${labelOf(d, a, L)}.`);
      const isLast = index >= open.length - 1;
      if (!isLast) {
        setCurId(open[index + 1].id);
      }
      return;
    }
    setPickedRowId(rowId ?? null);
    const left = open.length - 1;
    const next = open[index + 1] ?? open[index - 1] ?? null;
    if (open.length > 1) {
      setGone((g) => new Set(g).add(d.id));
      setCurId(next?.id ?? null);
    }
    setDrafts(({ [d.id]: _, ...rest }) => rest);
    announce(`${L.answered}: ${labelOf(d, a, L)}. ${left ? L.waiting(left) : L.allDone}`);
    onDecide?.(d.id, a);
  };

  const later = () => {
    if (!current) return;
    setFolded(true);
    want.current = "show";
    announce(`${L.later} – ${L.waiting(open.length)}`);
    onLater?.(current.id);
  };

  const show = () => {
    setFolded(false);
    want.current = "row";
  };

  return (
    <div ref={root} className={["ui-dcc", className].filter(Boolean).join(" ")} data-mode={viewMode}>
      <style href="ui-decision-card-clean" precedence="default">
        {css}
      </style>
      <span className="ui-dcc__sr" role="status" aria-live="polite">
        {say}
      </span>
      <div className="ui-dcc__wrap" inert={viewMode === "none"}>
        <div className="ui-dcc__inner">
          {viewMode === "min" ? (
            <div className="ui-dcc__box ui-dcc__box--min">
              <div className="ui-dcc__head">
                <Badge tone="warning" size="sm" icon={<CircleHelp />}>
                  {L.needsYou}
                </Badge>
                <span className="ui-dcc__task ui-dcc__num">
                  {open.length === 1 && current ? current.question : L.waiting(open.length)}
                </span>
                <span className="ui-dcc__tools">
                  <button type="button" className="ui-dcc__link ui-dcc__show" onClick={show}>
                    {L.show}
                  </button>
                  {onDismiss ? (
                    <button
                      type="button"
                      className="ui-dcc__page"
                      aria-label={L.dismiss}
                      disabled={submitting}
                      onClick={onDismiss}
                    >
                      <X className="size-3.5" aria-hidden="true" />
                    </button>
                  ) : null}
                </span>
              </div>
            </div>
          ) : shown ? (
            <DecisionBody
              key={shown.id}
              d={shown}
              L={L}
              count={open.length}
              index={index}
              pulse={pulse}
              isBatch={isBatch}
              submitting={submitting}
              pickedRowId={pickedRowId}
              selectedAnswer={isBatch ? answers?.[shown.id] : undefined}
              draft={
                isBatch
                  ? typeof answers?.[shown.id] === "object" && answers?.[shown.id] && "text" in (answers[shown.id] as { text?: string })
                    ? ((answers[shown.id] as { text?: string }).text ?? "")
                    : ""
                  : (drafts[shown.id] ?? "")
              }
              onDraft={(text) => {
                if (isBatch) {
                  onSelect?.(shown.id, text ? { text } : null);
                } else {
                  setDrafts((x) => ({ ...x, [shown.id]: text }));
                }
              }}
              onAnswer={(a, rowId) => handleAnswer(shown, a, rowId)}
              onLater={later}
              onDismiss={onDismiss}
              onPage={pageStep}
              onSubmitAll={onSubmitAll}
              canSubmit={canSubmit}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function DecisionBody({
  d,
  L,
  count,
  index,
  pulse,
  isBatch,
  submitting,
  pickedRowId,
  selectedAnswer,
  draft,
  onDraft,
  onAnswer,
  onLater,
  onDismiss,
  onPage,
  onSubmitAll,
  canSubmit,
}: {
  d: Decision;
  L: DecisionCardLabels;
  count: number;
  index: number;
  pulse: boolean;
  isBatch: boolean;
  submitting: boolean;
  pickedRowId: string | null;
  selectedAnswer?: DecisionAnswer;
  draft: string;
  onDraft: (text: string) => void;
  onAnswer: (a: DecisionAnswer, rowId?: string) => void;
  onLater: () => void;
  onDismiss?: () => void;
  onPage: (step: number) => void;
  onSubmitAll?: () => void;
  canSubmit: boolean;
}) {
  const qid = `ui-dcc-q-${useId().replace(/:/g, "")}`;
  const rows = rowsOf(d, L);
  const tiles = d.kind === "pick";
  const allowOwn = d.allowOwn !== false;
  const isLastPage = index >= count - 1;
  const isFirstPage = index <= 0;

  const selectedOptionId =
    typeof selectedAnswer === "object" && selectedAnswer && "option" in selectedAnswer
      ? selectedAnswer.option
      : selectedAnswer === "approve" || selectedAnswer === "decline"
        ? selectedAnswer
        : null;

  const [at, setAt] = useState(() => {
    if (selectedOptionId) {
      const idx = rows.findIndex((r) => r.id === selectedOptionId);
      if (idx >= 0) return idx;
    }
    return Math.max(0, rows.findIndex((r) => r.recommended));
  });
  const box = useRef<HTMLDivElement>(null);
  const own = useRef<HTMLInputElement>(null);

  const focusRow = (i: number) => {
    setAt(i);
    box.current?.querySelector<HTMLElement>(`[data-row="${i}"]`)?.focus();
  };

  const commitOwn = () => {
    if (submitting) return;
    if (isBatch) {
      if (isLastPage) {
        if (canSubmit) onSubmitAll?.();
      } else {
        onPage(1);
      }
      return;
    }
    const text = draft.trim();
    if (!text) return own.current?.focus();
    onAnswer({ text });
  };

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.metaKey || e.ctrlKey || e.altKey || e.nativeEvent.isComposing) return;
    if (e.key === "Escape") {
      e.preventDefault();
      return onLater();
    }
    if ((e.target as HTMLElement).getAttribute("role") !== "option") return;
    const n = Number(e.key);
    if (n >= 1 && n <= rows.length) {
      e.preventDefault();
      return onAnswer(rows[n - 1].answer, rows[n - 1].id);
    }
    if (allowOwn && (n === rows.length + 1 || (e.key === "ArrowDown" && at === rows.length - 1))) {
      e.preventDefault();
      return own.current?.focus();
    }
    const nextKeys = tiles ? ["ArrowRight", "ArrowDown"] : ["ArrowDown"];
    const prevKeys = tiles ? ["ArrowLeft", "ArrowUp"] : ["ArrowUp"];
    if (nextKeys.includes(e.key)) {
      e.preventDefault();
      focusRow(Math.min(rows.length - 1, at + 1));
    } else if (prevKeys.includes(e.key)) {
      e.preventDefault();
      focusRow(Math.max(0, at - 1));
    } else if (e.key === "Home") {
      e.preventDefault();
      focusRow(0);
    } else if (e.key === "End") {
      e.preventDefault();
      focusRow(rows.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onAnswer(rows[at].answer, rows[at].id);
    }
  };

  return (
    <div
      ref={box}
      className="ui-dcc__box"
      role="group"
      aria-labelledby={qid}
      data-pulse={pulse || undefined}
      onKeyDown={onKey}
    >
      <div className="ui-dcc__head">
        <Badge tone="warning" size="sm" icon={<CircleHelp />}>
          {L.needsYou}
        </Badge>
        {d.task ? (
          <span className="ui-dcc__task" dir="auto" title={d.task}>
            {d.task}
          </span>
        ) : null}
        <span className="ui-dcc__tools">
          {count > 1 && (
            <span className="ui-dcc__pager">
              <button
                type="button"
                className="ui-dcc__page"
                data-step="prev"
                aria-label={L.previous}
                disabled={submitting || (isBatch && isFirstPage)}
                onClick={() => onPage(-1)}
              >
                <ChevronLeft className="size-3.5" aria-hidden="true" />
              </button>
              <span
                className="ui-dcc__num ui-dcc__count"
                aria-live="polite"
                style={{ minWidth: `${L.of(count, count).length}ch` }}
              >
                {L.of(index + 1, count)}
              </span>
              <button
                type="button"
                className="ui-dcc__page"
                data-step="next"
                aria-label={L.next}
                disabled={submitting || (isBatch && isLastPage)}
                onClick={() => onPage(1)}
              >
                <ChevronRight className="size-3.5" aria-hidden="true" />
              </button>
            </span>
          )}
          <button
            type="button"
            className="ui-dcc__page"
            aria-label={L.later}
            title={L.later}
            aria-keyshortcuts="Escape"
            onClick={onLater}
          >
            <ChevronDown className="size-3.5" aria-hidden="true" />
          </button>
          {onDismiss ? (
            <button
              type="button"
              className="ui-dcc__page"
              aria-label={L.dismiss}
              title={L.dismiss}
              disabled={submitting}
              onClick={onDismiss}
            >
              <X className="size-3.5" aria-hidden="true" />
            </button>
          ) : null}
        </span>
      </div>

      <div className="ui-dcc__body">
        <p id={qid} className="ui-dcc__q" dir="auto">
          {d.question}
        </p>

        {d.facts && d.facts.length > 0 && (
          <dl className="ui-dcc__facts">
            {d.facts.slice(0, 3).map((f, i) => (
              <div key={i}>
                <dt title={f.label}>{f.label}</dt>
                <dd dir="auto">{f.value}</dd>
              </div>
            ))}
          </dl>
        )}

        {rows.length > 0 && (
          <div
            className={tiles ? "ui-dcc__tiles" : "ui-dcc__rows"}
            role="listbox"
            aria-labelledby={qid}
            aria-orientation={tiles ? "horizontal" : "vertical"}
            data-many={tiles && rows.length > 3 ? "" : undefined}
            style={tiles ? ({ "--ui-dcc-cols": Math.max(3, rows.length) } as CSSProperties) : undefined}
          >
            {rows.map((r, i) => {
              const isPicked = isBatch ? selectedOptionId === r.id : submitting && pickedRowId === r.id;
              return (
                <button
                  key={r.id}
                  type="button"
                  role="option"
                  disabled={submitting}
                  className={tiles ? "ui-dcc__tile" : "ui-dcc__opt"}
                  data-row={i}
                  data-selected={isPicked ? "" : undefined}
                  aria-selected={isPicked || i === at}
                  aria-pressed={isBatch ? isPicked : undefined}
                  aria-keyshortcuts={i < 9 ? String(i + 1) : undefined}
                  tabIndex={i === at ? 0 : -1}
                  onFocus={() => setAt(i)}
                  onClick={() => onAnswer(r.answer, r.id)}
                >
                  {tiles && (
                    <span className="ui-dcc__frame" aria-hidden="true">
                      {r.preview ?? (r.blocks ? <Blocks blocks={r.blocks} /> : null)}
                    </span>
                  )}
                  {tiles && r.recommended && <span className="ui-dcc__tag ui-dcc__tag--tile">{L.recommended}</span>}
                  <span className="ui-dcc__row">
                    <span className="ui-dcc__key ui-dcc__num" aria-hidden="true">
                      {i + 1}
                    </span>
                    <span className="ui-dcc__text">
                      <span className="ui-dcc__title" dir="auto">
                        {r.title}
                      </span>
                      {!tiles && r.summary && (
                        <span className="ui-dcc__summary" dir="auto">
                          {r.summary}
                        </span>
                      )}
                    </span>
                    {r.recommended && <span className="ui-dcc__tag ui-dcc__tag--row">{L.recommended}</span>}
                    {submitting && !isBatch && pickedRowId === r.id ? (
                      <Loader2 className="ui-dcc__check size-3.5 animate-spin" aria-hidden="true" />
                    ) : isBatch && isPicked ? (
                      <Check className="ui-dcc__check size-3.5" aria-hidden="true" />
                    ) : null}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {allowOwn && (
          <div
            className="ui-dcc__own"
            data-filled={isBatch && draft.trim() ? "" : undefined}
            onClick={(e) => e.target === e.currentTarget && own.current?.focus()}
          >
            <span className="ui-dcc__key ui-dcc__num" aria-hidden="true">
              {rows.length + 1}
            </span>
            <input
              ref={own}
              className="ui-dcc__input"
              value={draft}
              disabled={submitting}
              placeholder={L.own}
              aria-label={isBatch ? d.question : `${L.own.replace(/…$/, "")}: ${d.question}`}
              aria-keyshortcuts={rows.length < 9 ? String(rows.length + 1) : undefined}
              dir="auto"
              onChange={(e) => onDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.nativeEvent.isComposing) return;
                if (e.key === "Enter") {
                  e.preventDefault();
                  commitOwn();
                } else if (e.key === "ArrowUp" && !draft && rows.length > 0) {
                  e.preventDefault();
                  focusRow(rows.length - 1);
                }
              }}
            />
            {!isBatch && (
              <button
                type="button"
                className="ui-dcc__send"
                aria-label={L.send}
                title={L.send}
                aria-disabled={!draft.trim() || submitting || undefined}
                data-shown={draft.trim() && !submitting ? "" : undefined}
                tabIndex={draft.trim() && !submitting ? 0 : -1}
                onClick={commitOwn}
              >
                <ArrowUp className="size-3.5" aria-hidden="true" />
              </button>
            )}
          </div>
        )}

        {isBatch && (
          <div className="ui-dcc__foot">
            {onDismiss ? (
              <Button variant="ghost" size="sm" disabled={submitting} onClick={onDismiss}>
                {L.skip}
              </Button>
            ) : null}
            {isLastPage ? (
              <Button
                variant="primary"
                size="sm"
                loading={submitting}
                disabled={!canSubmit || submitting}
                onClick={() => onSubmitAll?.()}
              >
                {L.submit}
              </Button>
            ) : (
              <Button variant="secondary" size="sm" disabled={submitting} onClick={() => onPage(1)}>
                {L.next}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- Styles ---------- */

const css = /* css */ `
/* Colors, sizes and motion as variables – override them on .ui-dcc */
.ui-dcc {
  --ui-dcc-card: var(--aui-surface, #ffffff);
  --ui-dcc-ink: var(--aui-ink, rgba(0, 0, 0, 0.88));
  --ui-dcc-text: var(--aui-muted, rgba(0, 0, 0, 0.61));
  --ui-dcc-muted: var(--aui-muted, rgba(0, 0, 0, 0.45));
  --ui-dcc-faint: var(--aui-placeholder, rgba(0, 0, 0, 0.27));
  --ui-dcc-line: var(--aui-border, rgba(0, 0, 0, 0.06));
  --ui-dcc-fill: var(--aui-subtle, rgba(0, 0, 0, 0.05));
  --ui-dcc-well: var(--aui-subtle, rgba(0, 0, 0, 0.025));
  --ui-dcc-selected: color-mix(in srgb, var(--ui-dcc-ink) 6%, var(--ui-dcc-card));
  --ui-dcc-pulse: rgba(0, 0, 0, 0.045);
  --ui-dcc-wire-ink: rgba(0, 0, 0, 0.42);
  --ui-dcc-wire-mid: rgba(0, 0, 0, 0.16);
  --ui-dcc-wire-soft: rgba(0, 0, 0, 0.07);
  --ui-dcc-focus: var(--aui-focus, rgba(0, 0, 0, 0.72));
  --ui-dcc-solid: var(--aui-primary, rgba(0, 0, 0, 0.88));
  --ui-dcc-on-solid: var(--aui-on-primary, #fcfcfc);
  --ui-dcc-placeholder: var(--aui-placeholder, rgba(0, 0, 0, 0.36));
  --ui-dcc-shadow: 0 0 0 0.5px rgba(0, 0, 0, 0.06), 0 1px 1px -1px rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --ui-dcc-float: 0 0 0 0.5px rgba(0, 0, 0, 0.07), 0 1px 2px rgba(0, 0, 0, 0.05), 0 10px 28px -12px rgba(0, 0, 0, 0.14);
  --ui-dcc-ease: var(--aui-ease, cubic-bezier(0.23, 1, 0.32, 1));
  position: relative;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  container: ui-dcc / inline-size;
  font-family: var(--aui-font, "Inter", "InterVariable", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif);
  font-size: 13px;
  font-weight: 400;
  line-height: 20px;
  color: var(--ui-dcc-text);
  text-align: left;
  -webkit-font-smoothing: antialiased;
}
.ui-dcc *, .ui-dcc *::before, .ui-dcc *::after { box-sizing: border-box; }
:where(.ui-dcc button:not(.ui-buttonc)) { margin: 0; padding: 0; border: 0; background: none; font: inherit; color: inherit; text-align: inherit; cursor: pointer; -webkit-tap-highlight-color: transparent; }
:where(.ui-dcc button:not(.ui-buttonc)):disabled { opacity: 0.4; cursor: not-allowed; }
:where(.ui-dcc button:not(.ui-buttonc)):focus-visible { outline: 2px solid var(--ui-dcc-focus); outline-offset: 2px; }
.ui-dcc :is(p, dl, dd) { margin: 0; }
.ui-dcc svg { display: block; flex: none; }
.ui-dcc__sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.ui-dcc__num { font-variant-numeric: tabular-nums; }

.ui-dcc__wrap { display: grid; grid-template-rows: 1fr; opacity: 1; transition: grid-template-rows 360ms var(--ui-dcc-ease), opacity 220ms ease; }
.ui-dcc[data-mode="none"] .ui-dcc__wrap { grid-template-rows: 0fr; opacity: 0; }
.ui-dcc__inner { min-width: 0; min-height: 0; margin: -8px; padding: 8px; overflow: hidden; }
.ui-dcc:not([data-mode="none"]) .ui-dcc__inner { overflow: visible; animation: ui-dcc-clip 360ms both; }
@keyframes ui-dcc-clip { 0%, 99.9% { overflow: hidden; } 100% { overflow: visible; } }

/* ----- One floating card: head on top ----- */
.ui-dcc__box {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: 10px;
  border-radius: calc(var(--aui-radius-lg, 10px) + 6px);
  background: var(--ui-dcc-card);
  box-shadow: var(--aui-shadow-card, var(--ui-dcc-float));
  animation: ui-dcc-in 220ms ease both;
  transition: background-color 320ms ease;
}
.ui-dcc__box[data-pulse] { background: color-mix(in srgb, var(--ui-dcc-card), #808080 9%); }
.ui-dcc__head { display: flex; align-items: center; gap: 8px; min-width: 0; min-height: 28px; padding: 2px 4px 4px 10px; }
.ui-dcc__task { flex: 1; min-width: 0; overflow: hidden; font-size: 12px; color: var(--ui-dcc-muted); white-space: nowrap; text-overflow: ellipsis; }
.ui-dcc__tools { display: flex; flex: none; align-items: center; gap: 2px; margin-left: auto; }
.ui-dcc__count { text-align: center; padding: 0 2px; }
.ui-dcc__pager { display: inline-flex; align-items: center; gap: 2px; margin-right: 2px; font-size: 12px; color: var(--ui-dcc-muted); white-space: nowrap; }
.ui-dcc__page {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: calc(var(--aui-radius-sm, 5px) + 1px);
  color: var(--ui-dcc-muted);
  transition: background-color 140ms ease, color 140ms ease;
}
.ui-dcc__page:hover:not(:disabled) { background: var(--ui-dcc-fill); color: var(--ui-dcc-ink); }
.ui-dcc__link {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 8px;
  border-radius: calc(var(--aui-radius-sm, 5px) + 1px);
  font-size: 12px;
  font-weight: 500;
  color: var(--ui-dcc-text);
  white-space: nowrap;
  transition: background-color 140ms ease, color 140ms ease;
}
.ui-dcc__link:hover { background: var(--ui-dcc-fill); color: var(--ui-dcc-ink); }
.ui-dcc__box--min { animation-duration: 180ms; }
.ui-dcc__box--min .ui-dcc__head { min-height: 28px; padding: 0 4px 0 8px; }

/* ----- Question, rows, custom input, and footer ----- */
.ui-dcc__body { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.ui-dcc__q { padding: 4px 10px 8px; font-size: 14px; font-weight: 500; line-height: 20px; color: var(--ui-dcc-ink); overflow-wrap: anywhere; }
.ui-dcc__facts { display: grid; grid-template-columns: minmax(56px, max-content) minmax(0, 1fr); gap: 2px 12px; padding: 2px 10px 6px; }
.ui-dcc__facts > div { display: grid; grid-column: 1 / -1; grid-template-columns: subgrid; font-size: 13px; line-height: 20px; }
.ui-dcc__facts dt { max-width: 112px; overflow: hidden; color: var(--ui-dcc-muted); white-space: nowrap; text-overflow: ellipsis; }
.ui-dcc__facts dd { display: -webkit-box; min-width: 0; overflow: hidden; color: var(--ui-dcc-ink); overflow-wrap: break-word; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; }

.ui-dcc__rows { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; }
.ui-dcc__opt {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  min-height: 40px;
  padding: 8px 10px;
  border-radius: calc(var(--aui-radius-sm, 5px) + 3px);
  color: var(--ui-dcc-ink);
  transition: background-color 120ms ease, box-shadow 120ms ease;
}
.ui-dcc__opt:hover:not(:disabled),
.ui-dcc__rows:focus-within .ui-dcc__opt[aria-selected="true"] {
  background: var(--ui-dcc-fill);
}
.ui-dcc__opt[data-selected] {
  background: var(--ui-dcc-selected);
  box-shadow: inset 0 0 0 0.5px var(--ui-dcc-line);
}
.ui-dcc :is(.ui-dcc__opt, .ui-dcc__tile):focus-visible { outline-offset: -2px; }
.ui-dcc__row { display: flex; flex: 1; align-items: flex-start; gap: 10px; min-width: 0; }
.ui-dcc__key {
  display: grid;
  flex: none;
  place-items: center;
  width: 22px;
  height: 22px;
  margin-top: 1px;
  border-radius: calc(var(--aui-radius-sm, 5px) + 1px);
  background: var(--ui-dcc-fill);
  font-size: 12px;
  font-weight: 500;
  line-height: 16px;
  color: var(--ui-dcc-muted);
  transition: background-color 120ms ease, box-shadow 120ms ease, color 120ms ease;
}
.ui-dcc__text { display: flex; flex: 1; flex-direction: column; min-width: 0; }
.ui-dcc__title { font-size: 13px; font-weight: 500; line-height: 20px; overflow-wrap: break-word; }
.ui-dcc__summary { margin-top: 1px; font-size: 12px; line-height: 17px; color: var(--ui-dcc-muted); overflow-wrap: break-word; }
.ui-dcc__tag {
  flex: none;
  align-self: center;
  padding: 0 6px;
  border-radius: var(--aui-radius-sm, 5px);
  background: var(--ui-dcc-fill);
  font-size: 11px;
  font-weight: 500;
  line-height: 18px;
  color: var(--ui-dcc-muted);
  white-space: nowrap;
  transition: background-color 120ms ease, box-shadow 120ms ease;
}
.ui-dcc__check { flex: none; align-self: center; color: var(--ui-dcc-ink); }
.ui-dcc__opt:hover:not(:disabled) :is(.ui-dcc__key, .ui-dcc__tag),
.ui-dcc__opt[data-selected] :is(.ui-dcc__key, .ui-dcc__tag),
.ui-dcc__rows:focus-within .ui-dcc__opt[aria-selected="true"] :is(.ui-dcc__key, .ui-dcc__tag) {
  background: var(--ui-dcc-card);
  box-shadow: var(--ui-dcc-shadow);
}
.ui-dcc__opt[data-selected] .ui-dcc__key { color: var(--ui-dcc-ink); }

/* ----- pick: preview tiles ----- */
.ui-dcc__tiles { display: grid; grid-template-columns: repeat(var(--ui-dcc-cols, 3), minmax(0, 1fr)); gap: 4px; }
.ui-dcc__tile { position: relative; display: flex; flex-direction: column; gap: 6px; min-width: 0; padding: 4px; border-radius: var(--aui-radius-lg, 10px); color: var(--ui-dcc-ink); transition: background-color 120ms ease; }
.ui-dcc__tile:hover, .ui-dcc__tiles:focus-within .ui-dcc__tile[aria-selected="true"] { background: var(--ui-dcc-fill); }
.ui-dcc__frame { position: relative; display: grid; place-items: center; aspect-ratio: 3 / 2; overflow: hidden; padding: 6px; border-radius: 7px; background: var(--ui-dcc-well); box-shadow: inset 0 0 0 1px var(--ui-dcc-line); }
.ui-dcc__frame > * { width: 100%; height: 100%; }
.ui-dcc__tile .ui-dcc__tag--tile { position: absolute; top: 10px; right: 10px; background: var(--ui-dcc-card); box-shadow: var(--ui-dcc-shadow); }
.ui-dcc__tile .ui-dcc__tag--row { display: none; }
.ui-dcc__wire-page { fill: var(--ui-dcc-card); }
.ui-dcc__wire [data-tone="ink"] { fill: var(--ui-dcc-wire-ink); }
.ui-dcc__wire [data-tone="mid"] { fill: var(--ui-dcc-wire-mid); }
.ui-dcc__wire [data-tone="soft"] { fill: var(--ui-dcc-wire-soft); }
.ui-dcc__tile .ui-dcc__row { align-items: flex-start; gap: 8px; padding: 0 2px 2px; }
.ui-dcc__tile .ui-dcc__key { width: 20px; height: 20px; font-size: 11px; }
.ui-dcc__tile:hover .ui-dcc__key, .ui-dcc__tiles:focus-within .ui-dcc__tile[aria-selected="true"] .ui-dcc__key { background: var(--ui-dcc-card); box-shadow: var(--ui-dcc-shadow); }

/* ----- Custom answer: the last row ----- */
.ui-dcc__own {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  min-height: 40px;
  padding: 6px 10px;
  border-radius: calc(var(--aui-radius-sm, 5px) + 3px);
  cursor: text;
  transition: background-color 120ms ease, box-shadow 120ms ease;
}
.ui-dcc__own:hover { background: var(--ui-dcc-well); }
.ui-dcc__own:focus-within,
.ui-dcc__own[data-filled] {
  background: var(--ui-dcc-well);
  box-shadow: inset 0 0 0 1px var(--ui-dcc-line);
}
.ui-dcc__own .ui-dcc__key { margin-top: 0; }
.ui-dcc__input { flex: 1; min-width: 0; height: 28px; margin: 0; padding: 0; border: 0; background: none; font: inherit; font-size: 13px; color: var(--ui-dcc-ink); outline: none; }
.ui-dcc__input::placeholder { color: var(--ui-dcc-placeholder); }
.ui-dcc__send {
  display: grid;
  flex: none;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: var(--ui-dcc-solid);
  color: var(--ui-dcc-on-solid);
  opacity: 0;
  transform: scale(0.8);
  pointer-events: none;
  transition: opacity 140ms ease, transform 180ms var(--ui-dcc-ease);
}
.ui-dcc__send[data-shown] { opacity: 1; transform: none; pointer-events: auto; }
.ui-dcc__send[data-shown]:active { transform: scale(0.92); }

/* ----- Batch footer: Skip + Next / Submit ----- */
.ui-dcc__foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
  padding: 10px 4px 2px;
  border-top: 0.5px solid var(--ui-dcc-line);
}

@container ui-dcc (max-width: 560px) {
  .ui-dcc__facts > div { grid-template-columns: 56px minmax(0, 1fr); }
  .ui-dcc__tiles[data-many] { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .ui-dcc__pager { gap: 0; }
}
@container ui-dcc (max-width: 420px) {
  .ui-dcc__tiles, .ui-dcc__tiles[data-many] { grid-template-columns: minmax(0, 1fr); gap: 0; }
  .ui-dcc__tile { flex-direction: row; align-items: center; gap: 10px; min-height: 44px; padding: 4px 6px; border-radius: calc(var(--aui-radius-sm, 5px) + 3px); }
  .ui-dcc__tile .ui-dcc__row { flex: 1; align-items: center; gap: 10px; padding: 0; }
  .ui-dcc__tile .ui-dcc__key { width: 22px; height: 22px; font-size: 12px; }
  .ui-dcc__frame { order: 1; flex: none; width: 54px; padding: 3px; border-radius: 6px; }
  .ui-dcc__tile .ui-dcc__tag--tile { display: none; }
  .ui-dcc__tile .ui-dcc__tag--row { display: block; }
}

@media (pointer: coarse) {
  .ui-dcc__opt, .ui-dcc__own { min-height: 44px; }
  .ui-dcc__page, .ui-dcc__send { position: relative; width: 32px; height: 32px; }
  .ui-dcc__link { position: relative; height: 32px; }
  .ui-dcc__page::after, .ui-dcc__send::after, .ui-dcc__link::after { content: ""; position: absolute; inset: -4px; }
  .ui-dcc__head, .ui-dcc__box--min .ui-dcc__head { min-height: 40px; }
}

@keyframes ui-dcc-in { from { opacity: 0; } }

@media (prefers-reduced-motion: reduce) {
  .ui-dcc *, .ui-dcc *::before, .ui-dcc *::after { animation: none !important; transition: none !important; }
  .ui-dcc__wrap { transition: none; }
}

:where(.dark, [data-theme="dark"]) .ui-dcc {
  --ui-dcc-card: var(--aui-surface, #1b1b1e);
  --ui-dcc-ink: var(--aui-ink, rgba(255, 255, 255, 0.9));
  --ui-dcc-text: var(--aui-muted, rgba(255, 255, 255, 0.62));
  --ui-dcc-muted: var(--aui-muted, rgba(255, 255, 255, 0.45));
  --ui-dcc-faint: var(--aui-placeholder, rgba(255, 255, 255, 0.28));
  --ui-dcc-line: var(--aui-border, rgba(255, 255, 255, 0.08));
  --ui-dcc-fill: var(--aui-subtle, rgba(255, 255, 255, 0.07));
  --ui-dcc-well: var(--aui-subtle, rgba(255, 255, 255, 0.035));
  --ui-dcc-selected: color-mix(in srgb, var(--ui-dcc-ink) 9%, var(--ui-dcc-card));
  --ui-dcc-wire-ink: rgba(255, 255, 255, 0.5);
  --ui-dcc-wire-mid: rgba(255, 255, 255, 0.2);
  --ui-dcc-wire-soft: rgba(255, 255, 255, 0.08);
  --ui-dcc-focus: var(--aui-focus, rgba(255, 255, 255, 0.75));
  --ui-dcc-solid: var(--aui-primary, rgba(255, 255, 255, 0.92));
  --ui-dcc-on-solid: var(--aui-on-primary, #141416);
  --ui-dcc-placeholder: var(--aui-placeholder, rgba(255, 255, 255, 0.32));
  --ui-dcc-shadow: 0 0 0 0.5px rgba(255, 255, 255, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.4);
  --ui-dcc-float: 0 0 0 0.5px rgba(255, 255, 255, 0.12), 0 12px 28px -10px rgba(0, 0, 0, 0.6);
}
`;
