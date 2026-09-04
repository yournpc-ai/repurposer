/** RunTaskList — the run's task list (the Claude Code anatomy): ONE
 * persistent block — pinned bottom-most in the message flow while the run
 * is live, the archive of it once terminal. THE HEADER IS THE ANCHOR
 * (2026-09-05 层级裁决): `☷ title · elapsed` is itself the expand/collapse
 * toggle — CC's `* Creating… (2m 45s)` line, never a separate row — and the
 * steps render FLAT under it (the retired "Preparation · n steps" group row
 * was a fake middle level, 层级错乱). Live defaults open (the user watches
 * the work check off, CC's in-flight pose); the terminal frame settles the
 * SAME line into the summary state — rows folded, chevron stays, one click
 * re-opens the flat receipt (CC's "Thought for 42s (ctrl+o to expand)") —
 * and the completion prose follows over SSE. Between header and checklist
 * one narrative line (碎碎念) — the running step's stage hint shimmering +
 * its own elapsed: the full form of FLORA's "Running node…" action line
 * (the dock's RunStatusRow is its collapsed twin). Row text is
 * BUILDER-WRITTEN: spec.summary arrives preset from the server (the static
 * task name / slot tag) and is rewritten with the quantified line when the
 * step completes — the frontend renders spec fields, never kind→copy
 * dictionaries. The only frontend copy left is the PROGRESSIVE fallback
 * (stage hints / kind progressive) for the live narrative line. */

import { useEffect, useState } from "react"
import type { TFunction } from "i18next"
import {
  Check,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  ListChecks,
  Loader2,
  Minus,
  Square,
  X,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { cn } from "@/lib/utils"
import type { WorkflowStep } from "@/lib/types"

/** Ticking clock for the elapsed counters — null until mounted (SSR-safe:
 * the server render and the first client render both show no elapsed), and
 * frozen once `live` goes false (the terminal frame keeps its last read).
 * Shared by the checklist, the folded status row AND the dock's ThinkingRow
 * (one clock, one hydration contract — 2026-09-05 减法批). */
export function useNow(live: boolean): number | null {
  const [now, setNow] = useState<number | null>(null)
  useEffect(() => {
    if (!live) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [live])
  return now
}

/** "1m 6s" / "45s" / "1h 3m" — the Claude Code elapsed shorthand, the ONE
 * copy (the thinking row consumed a byte-identical twin until the same
 * subtraction batch). */
export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

/** The live narrative's step pick + progressive copy chain (shared by the
 * full checklist's 碎碎念 line and the folded status row): the running step
 * wins; a parked interrupt (review tier) has no running step and reads
 * through the same chain ("waiting for your direction", not the queued
 * fallback). Copy chain: the runner's stage hint → the kind's progressive
 * form → the preset task name → the raw kind.
 * Honesty carve-out (2026-09-04): the preprocess node's "Analyzing your
 * uploads…" is a lie on a zero-upload (copy-writer) run — it validates
 * material and admits the writer lift, so it reads the generic
 * "Preparing generation…" instead. */
function runNarrative(
  steps: WorkflowStep[],
  t: TFunction,
  hasUploads: boolean,
): { running: WorkflowStep | null; waiting: WorkflowStep | null; label: string | null } {
  const running = steps.find((s) => s.status === "running") ?? null
  const waiting = steps.find((s) => s.status === "waiting") ?? null
  const step = running ?? waiting
  const label = step
    ? step.kind === "preprocess" && !hasUploads
      ? t("results.stepper.prepare")
      : (step.stage ? t(`results.stepper.${step.stage}`, { defaultValue: "" }) : "") ||
        t(`chat.stepKinds.${step.kind}`, { defaultValue: "" }) ||
        step.summary ||
        step.kind
    : null
  return { running, waiting, label }
}

export function RunTaskList({
  steps,
  title,
  runStartedAt,
  terminal,
  narrativeFallback,
  hasUploads,
}: {
  steps: WorkflowStep[]
  /** The plan's summary line — the header's resting title. */
  title: string
  runStartedAt: string | null
  terminal: boolean
  /** What the narrative line says when no step is running yet (assets still
   * processing / the run still queued) — the caller knows which. */
  narrativeFallback: string
  /** Honest preprocess copy: with zero uploads the "Analyzing your
   * uploads…" progressive is a lie (chat-flow-sequencing 验收 5). */
  hasUploads: boolean
}) {
  const { t } = useTranslation()
  const now = useNow(!terminal)
  const { running, label: narrativeLabel } = runNarrative(steps, t, hasUploads)
  const startedMs = runStartedAt ? Date.parse(runStartedAt) : null
  // The archive frame (mounting an already-terminal run) has no ticking
  // clock — the total reads off the last step's finish instead.
  const endMs = terminal
    ? Math.max(
        startedMs ?? 0,
        ...steps
          .map((s) => Date.parse((s.finished_at ?? s.started_at ?? "") as string))
          .filter((ms) => !Number.isNaN(ms)),
      )
    : now
  const elapsed =
    endMs != null && startedMs != null && !Number.isNaN(endMs)
      ? formatElapsed(endMs - startedMs)
      : null

  const runningMs = running?.started_at ? Date.parse(running.started_at) : null
  const stageElapsed =
    now != null && runningMs != null ? formatElapsed(now - runningMs) : null

  // The header IS the anchor: userOpen null = follow the pose — open while
  // live (CC's in-flight checklist), folded summary once terminal. The
  // settle resets an untouched toggle so the archive always lands on the
  // one-line receipt; an explicit post-settle click still re-opens it.
  const [userOpen, setUserOpen] = useState<boolean | null>(null)
  useEffect(() => {
    if (terminal) setUserOpen(null)
  }, [terminal])
  const open = userOpen ?? !terminal

  return (
    <div className="w-full">
      {/* Header — the ✻ line AND the expand anchor (层级裁决): title +
          total elapsed + trailing chevron; one click folds/unfolds the flat
          checklist below. A resting title, never the running step's name —
          "current activity" belongs to the narrative line alone. */}
      <button
        type="button"
        onClick={() => setUserOpen(!open)}
        className="flex w-full items-center gap-2.5 rounded-md text-left text-sm transition-colors hover:bg-accent/50"
      >
        <ListChecks className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span
          className={cn(
            "min-w-0 truncate font-medium",
            terminal && "text-muted-foreground",
          )}
        >
          {title}
        </span>
        {elapsed ? (
          <span className="shrink-0 text-sm text-muted-foreground">
            {elapsed}
          </span>
        ) : null}
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronUp className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
      </button>

      {/* Narrative line (碎碎念) — the Claude Code status line: ONE live row
          naming what's happening now + its own elapsed, replaced per stage.
          Live only — the terminal frame owns its own summary pose. */}
      {!terminal ? (
        <div className="mt-2.5 flex items-center gap-2.5 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
          <span className="shimmer min-w-0 truncate">
            {narrativeLabel ?? narrativeFallback}
          </span>
          {stageElapsed ? <span className="shrink-0">{stageElapsed}</span> : null}
        </div>
      ) : null}

      {/* The checklist — FLAT (the group row was a fake middle level): every
          step is a sibling row, new runtime fan-out rows (render steps)
          append at the bottom as they're born. Hidden in the terminal
          summary pose; the header's chevron re-opens the full receipt. */}
      {open ? (
        <div className="mt-3 flex flex-col gap-2">
          {steps.map((step) => (
            <TaskRow key={step.id} step={step} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function TaskRow({ step }: { step: WorkflowStep }) {
  const icon =
    step.status === "running" ? (
      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
    ) : step.status === "done" ? (
      <Check className="h-3.5 w-3.5 text-muted-foreground" />
    ) : step.status === "failed" ? (
      <X className="h-3.5 w-3.5 text-destructive" />
    ) : step.status === "waiting" ? (
      <CircleHelp className="h-3.5 w-3.5 text-primary" />
    ) : step.status === "skipped" ? (
      <Minus className="h-3.5 w-3.5 text-muted-foreground/50" />
    ) : (
      <Square className="h-3 w-3 text-muted-foreground/50" />
    )
  // Builder-written text: done rows carry the runner's quantified rewrite,
  // everything else the creation-time preset (static task name / slot tag).
  const label = step.summary ?? step.kind
  return (
    <Marker>
      <MarkerIcon>{icon}</MarkerIcon>
      <MarkerContent
        className={cn(
          "text-xs",
          step.status === "done" && "text-muted-foreground",
          step.status === "pending" && "text-muted-foreground/70",
          step.status === "skipped" && "text-muted-foreground/60 line-through",
          step.status === "failed" && "text-destructive"
        )}
      >
        {step.status === "failed" && step.error
          ? `${label} — ${step.error}`
          : label}
      </MarkerContent>
    </Marker>
  )
}

/** RunStatusRow — the folded 打勾 (ADR-051, the Claude Code collapsed form /
 * FLORA "Running node…"): ONE shimmer status line docked above the input
 * while a run is live and the history region is closed. Click = expand the
 * step log — the history's RunTaskList is the ONLY checklist; this row
 * never grows a second one. A square child of the dock's frosted container
 * (D4 一体容器): no fill / rounding of its own. */
export function RunStatusRow({
  steps,
  runStartedAt,
  narrativeFallback,
  hasUploads,
  onClick,
}: {
  steps: WorkflowStep[]
  runStartedAt: string | null
  /** What the line says when no step is running yet (assets processing /
   * the run still queued) — the caller knows which. */
  narrativeFallback: string
  /** Same honest-preprocess switch as the full list. */
  hasUploads: boolean
  onClick: () => void
}) {
  const { t } = useTranslation()
  const now = useNow(true)
  const { running, waiting, label } = runNarrative(steps, t, hasUploads)
  const startedMs = runStartedAt ? Date.parse(runStartedAt) : null
  const elapsed =
    now != null && startedMs != null ? formatElapsed(now - startedMs) : null
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={t("results.dock.history")}
      className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-xs text-muted-foreground hover:bg-accent/50"
    >
      {waiting && !running ? (
        <CircleHelp className="h-3.5 w-3.5 shrink-0 text-primary" />
      ) : (
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
      )}
      <span className="shimmer min-w-0 flex-1 truncate">
        {label ?? narrativeFallback}
      </span>
      {elapsed ? <span className="shrink-0 tabular-nums">{elapsed}</span> : null}
      <ChevronUp className="h-3.5 w-3.5 shrink-0" />
    </button>
  )
}
