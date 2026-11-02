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
import { runWorkElapsedMs, runWorkPhase, visibleProductionStages } from "@/lib/runWorkSegment"
import { cn } from "@/lib/utils"
import type { ProductionStage, WorkflowStep } from "@/lib/types"

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
  renderAttemptCount = 1,
  narrativeFallback,
  hasUploads,
}: {
  steps: WorkflowStep[]
  /** Read fallback for legacy rows without an honest elapsed span. */
  title: string
  runStartedAt: string | null
  /** Run-world terminal, not the work segment's delivery seal. */
  terminal: boolean
  cancelled?: boolean
  failed: boolean
  reviewPending: boolean
  /** First-visible delivery edge, or the bounded no-reply fallback. */
  workEndedAtMs: number | null
  /** Persisted delivery rows prove how many render attempts need stage history. */
  renderAttemptCount?: number
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
    : runWorkElapsedMs(runStartedAt, steps, workEndedAtMs, renderAttemptCount)

  const runningMs = running?.started_at ? Date.parse(running.started_at) : null
  const stageElapsed =
    now != null && runningMs != null && !Number.isNaN(runningMs)
      ? formatElapsed(now - runningMs)
      : null

  const stepDetails = steps.length > 0 ? (
    <div className="mt-2 ml-[5.5px] flex flex-col gap-1.5 border-l border-foreground/15 pl-3.5">
      {steps.map((step) => (
        <TaskRow key={step.id} step={step} t={t} />
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
      settledLabel={failed
        ? t("chat.runFailed")
        : elapsedMs == null
          ? title || t("chat.activityFold.actionCount", { count: steps.length })
          : undefined}
      failed={failed}
    />
  )
}

function TaskRow({ step, t }: { step: WorkflowStep; t: TFunction }) {
  const noop = step.status === "skipped" || step.noop === true
  const icon =
    step.status === "running" ? (
      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
    ) : step.status === "failed" ? (
      <X className="h-3.5 w-3.5 text-destructive" />
    ) : step.status === "waiting" ? (
      <CircleHelp className="h-3.5 w-3.5 text-primary" />
    ) : null
  const label = step.kind === "render" && step.summary === "Uploaded"
    ? t("chat.legacyStepSummaries.uploaded")
    : step.summary ?? step.kind
  const stages = visibleProductionStages(step)
  return (
    <div className="flex flex-col gap-1.5">
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
      {stages.length > 0 ? (
        <div className="ml-5.5 flex flex-col gap-1">
          {stages.map((stage) => (
            <ProductionStageRow key={stage.event_id} stage={stage} t={t} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function ProductionStageRow({ stage, t }: { stage: ProductionStage; t: TFunction }) {
  const label = t(`chat.productionStages.${stage.kind}`, { defaultValue: stage.kind })
  const reused =
    stage.reused_count != null && stage.reused_count > 0 && stage.item_count != null
      ? t("chat.productionStages.reuseSummary", {
          reused: stage.reused_count,
          total: stage.item_count,
        })
      : null
  return (
    <div className="flex items-baseline gap-2 text-xs">
      <span className="flex h-3 w-3 shrink-0 items-center justify-center self-center">
        {stage.status === "running" ? (
          <Loader2 className="h-3 w-3 animate-spin text-primary" />
        ) : stage.status === "failed" ? (
          <X className="h-3 w-3 text-destructive" />
        ) : (
          <Check className="h-3 w-3 text-meta-foreground" />
        )}
      </span>
      <span
        className={cn(
          "min-w-0 break-words",
          stage.status === "failed" ? "text-destructive" : "text-meta-foreground",
          stage.status === "running" && "shimmer text-muted-foreground",
        )}
      >
        {label}{reused ? ` · ${reused}` : ""}
      </span>
    </div>
  )
}
