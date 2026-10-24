/** RunTaskList — the run adapter for the shared WorkSegmentRow.
 *
 * The run world supplies steps, narrative, outcome and timestamps. The shared
 * row supplies live/reviewing/settled anatomy, disclosure and the Worked
 * receipt. Run terminal is NOT the row's settle edge: a pending delivery keeps
 * the same row open until its first visible reply or a bounded fallback. */

import { Check, CircleHelp, Loader2, X } from "lucide-react"
import type { TFunction } from "i18next"
import { useTranslation } from "react-i18next"

import { WorkSegmentRow } from "@/components/chat/ActivityStream"
import { formatElapsed, useNow } from "@/components/chat/workTiming"
import { runWorkElapsedMs, runWorkPhase } from "@/lib/runWorkSegment"
import { cn } from "@/lib/utils"
import type { WorkflowStep } from "@/lib/types"

/** Live narrative: running step → parked interrupt → honest queued/gap
 * fallback. Copy remains builder-written; only progressive fallbacks are
 * localized here. */
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
  failed,
  reviewPending,
  workEndedAtMs,
  narrativeFallback,
  hasUploads,
}: {
  steps: WorkflowStep[]
  /** Read fallback for legacy rows without an honest elapsed span. */
  title: string
  runStartedAt: string | null
  /** Run-world terminal, not the work segment's delivery seal. */
  terminal: boolean
  failed: boolean
  reviewPending: boolean
  /** First-visible delivery edge, or the bounded no-reply fallback. */
  workEndedAtMs: number | null
  narrativeFallback: string
  hasUploads: boolean
}) {
  const { t } = useTranslation()
  const phase = runWorkPhase({ terminal, reviewPending, workEndedAtMs })
  const live = phase !== "settled"
  const now = useNow(phase === "running")
  const { running, label: narrativeLabel } = runNarrative(steps, t, hasUploads)
  const runStarted = steps.some((s) => s.status !== "pending")
  const runLabel =
    narrativeLabel ??
    (runStarted ? t("chat.thinking") : null) ??
    narrativeFallback
  const liveLabel = phase === "reviewing" ? t("chat.closingReview") : runLabel
  const elapsedMs = live
    ? null
    : runWorkElapsedMs(runStartedAt, steps, workEndedAtMs)

  const runningMs = running?.started_at ? Date.parse(running.started_at) : null
  const stageElapsed =
    now != null && runningMs != null && !Number.isNaN(runningMs)
      ? formatElapsed(now - runningMs)
      : null

  const stepDetails = steps.length > 0 ? (
    <div className="mt-2 ml-[5.5px] flex flex-col gap-1.5 border-l border-foreground/15 pl-3.5">
      {steps.map((step) => (
        <TaskRow key={step.id} step={step} />
      ))}
    </div>
  ) : undefined

  return (
    <WorkSegmentRow
      liveLabel={live ? liveLabel : undefined}
      liveTrailing={phase === "running" ? stageElapsed : null}
      liveDetails={stepDetails}
      details={stepDetails}
      elapsedMs={elapsedMs}
      settledLabel={elapsedMs == null ? title || undefined : undefined}
      settledLeading={
        !live ? (
          failed ? (
            <X className="h-3 w-3 shrink-0 text-destructive" />
          ) : (
            <Check className="h-3 w-3 shrink-0" />
          )
        ) : null
      }
      failed={failed}
    />
  )
}

function TaskRow({ step }: { step: WorkflowStep }) {
  const noop = step.status === "skipped" || step.noop === true
  const icon =
    step.status === "running" ? (
      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
    ) : step.status === "failed" ? (
      <X className="h-3.5 w-3.5 text-destructive" />
    ) : step.status === "waiting" ? (
      <CircleHelp className="h-3.5 w-3.5 text-primary" />
    ) : null
  const label = step.summary ?? step.kind
  return (
    <div className="flex items-baseline gap-2 text-xs">
      <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center self-center">
        {icon}
      </span>
      <span
        className={cn(
          "min-w-0 break-words",
          noop
            ? "text-meta-foreground line-through decoration-foreground/25"
            : step.status === "done"
              ? "text-muted-foreground"
              : step.status === "failed"
                ? "text-destructive"
                : "text-muted-foreground/70",
          step.status === "running" && "shimmer text-muted-foreground",
        )}
      >
        {step.status === "failed" && step.error
          ? `${label} — ${step.error}`
          : label}
      </span>
    </div>
  )
}
