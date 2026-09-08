/** RunTaskList — the run's task list (the Claude Code anatomy): ONE
 * persistent block — pinned bottom-most in the message flow while the run
 * is live, the archive of it once terminal. THE DYNAMIC ROW IS THE WHOLE
 * CHROME (2026-09-08 user ruling, twice — first merge, then the register
 * correction): the single row is the CC status line in ONE quiet register
 * — text-xs muted — and IT is the expand/collapse anchor. LIVE: ● shimmer
 * narrative (what's happening NOW — the text is dynamic by definition) +
 * its own stage elapsed. TERMINAL: the SAME line's receipt form — ✓ plan
 * title · total elapsed, same size same gray (降灰 reads as quiet, never
 * the retired header's text-sm/font-medium/ListChecks register — that
 * second row was the one ordered deleted, not archived). The steps render
 * FLAT under the one row (the "Preparation · n steps" group row died the
 * same way). Live defaults open (the user watches the work check off, CC's
 * in-flight pose); the terminal frame settles folded, one click re-opens
 * the flat receipt — and the completion prose follows over SSE. Row text
 * is BUILDER-WRITTEN: spec.summary arrives preset from the server (the
 * static task name / slot tag) and is rewritten with the quantified line
 * when the step completes — the frontend renders spec fields, never
 * kind→copy dictionaries. The only frontend copy left is the PROGRESSIVE
 * fallback (stage hints / kind progressive) for the live narrative. */

import { useEffect, useState } from "react"
import type { TFunction } from "i18next"
import {
  Check,
  ChevronDown,
  ChevronUp,
  CircleHelp,
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
 * Shared by the checklist's row AND the dock's ThinkingRow (one clock, one
 * hydration contract — 2026-09-05 减法批). */
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

/** The live narrative's step pick + progressive copy chain (the dynamic
 * row's reading material): the running step wins; a parked interrupt
 * (review tier) has no running step and reads through the same chain
 * ("waiting for your direction", not the queued fallback). Copy chain: the
 * runner's stage hint → the kind's progressive form → the preset task name
 * → the raw kind.
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
  /** The plan's summary line — the receipt row's resting title. */
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

  // THE dynamic row IS the anchor (2026-09-08 层级翻案): userOpen null =
  // follow the pose — open while live (CC's in-flight checklist), folded
  // receipt once terminal. The settle resets an untouched toggle so the
  // archive always lands on the one-line receipt; an explicit post-settle
  // click still re-opens it.
  const [userOpen, setUserOpen] = useState<boolean | null>(null)
  useEffect(() => {
    if (terminal) setUserOpen(null)
  }, [terminal])
  const open = userOpen ?? !terminal

  return (
    <div className="w-full">
      {/* THE ONE ROW — the dynamic action line, ONE quiet register in both
          states (text-xs muted): live = ● shimmer narrative + its stage
          clock; terminal = the SAME line's receipt form (✓ title · total
          elapsed — never the retired header's text-sm/font-medium). It is
          itself the expand/collapse toggle for the flat checklist below. */}
      <button
        type="button"
        onClick={() => setUserOpen(!open)}
        className="flex w-full items-center gap-2.5 rounded-md text-left text-xs text-muted-foreground transition-colors hover:bg-accent/50"
      >
        {terminal ? (
          <Check className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
        )}
        <span className={cn("min-w-0 truncate", !terminal && "shimmer")}>
          {terminal ? title : (narrativeLabel ?? narrativeFallback)}
        </span>
        {(terminal ? elapsed : stageElapsed) ? (
          <span className="shrink-0 tabular-nums">
            {terminal ? elapsed : stageElapsed}
          </span>
        ) : null}
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronUp className="h-3 w-3 shrink-0" />
        )}
      </button>

      {/* The checklist — FLAT under the one row: every step is a sibling
          row, new runtime fan-out rows (render steps) append at the bottom
          as they're born. Folded in the terminal receipt pose; the row's
          chevron re-opens the full receipt. */}
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
