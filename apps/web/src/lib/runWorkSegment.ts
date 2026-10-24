import type { WorkflowStep } from "@/lib/types"

/** The run row stays open after the run's tools finish while its matching
 * delivery reply is pending. Only the delivery's visible speech (or a real
 * fallback terminal) settles the segment. */
export type RunWorkPhase = "running" | "reviewing" | "settled"

export interface RunWorkSeal {
  runId: string
  endedAtMs: number
}

export function runWorkPhase({
  terminal,
  reviewPending,
  workEndedAtMs,
}: {
  terminal: boolean
  reviewPending: boolean
  workEndedAtMs: number | null
}): RunWorkPhase {
  if (!terminal) return "running"
  return reviewPending && workEndedAtMs == null ? "reviewing" : "settled"
}

function parseMs(value: string | null): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

/** Latest observable step edge, used by both the timeline anchor and the
 * replay/no-reply fallback. Invalid partial timestamps never poison it. */
export function runStepEndMs(
  runStartedAt: string | null,
  steps: WorkflowStep[],
): number | null {
  let end = parseMs(runStartedAt)
  for (const step of steps) {
    const stepEnd = parseMs(step.finished_at ?? step.started_at)
    if (stepEnd == null) continue
    end = end == null ? stepEnd : Math.max(end, stepEnd)
  }
  return end
}

/** A live delivery seal includes the review wait up to the first visible
 * reply. Without that client fact, replay honestly falls back to the run's
 * observable step span instead of treating a message write time as speech. */
export function runWorkElapsedMs(
  runStartedAt: string | null,
  steps: WorkflowStep[],
  workEndedAtMs: number | null,
): number | null {
  const start = parseMs(runStartedAt)
  if (start == null) return null
  const end = workEndedAtMs ?? runStepEndMs(runStartedAt, steps)
  if (end == null || !Number.isFinite(end) || end < start) return null
  return end - start
}

/** Write-once per run, scoped to the currently attached run. A late reply
 * from an older run can neither seal the new one nor rewrite a frozen clock. */
export function nextRunWorkSeal(
  current: RunWorkSeal | null,
  attachedRunId: string | null,
  target: RunWorkSeal,
): RunWorkSeal | null {
  if (attachedRunId !== target.runId || current?.runId === target.runId) {
    return current
  }
  return target
}
