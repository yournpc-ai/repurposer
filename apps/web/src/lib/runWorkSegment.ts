import type { ProductionStage, WorkflowStep } from "@/lib/types"
import type { RunTerminalSource } from "@/lib/use-run-events"

/** The run row stays open after the run's tools finish while its matching
 * delivery reply is pending. Only the delivery's visible speech (or a real
 * fallback terminal) settles the segment. */
export type RunWorkPhase = "running" | "reviewing" | "settled"

/** Only the current attempt projects into the RunBlock. Older attempts stay
 * persisted server-side but cannot leave a stale running row after re-claim. */
export function visibleProductionStages(step: WorkflowStep): ProductionStage[] {
  const stages = step.production_stages ?? []
  if (stages.length === 0) return []
  const attempt = step.attempt ?? Math.max(...stages.map((stage) => stage.attempt))
  return stages
    .filter((stage) => stage.attempt === attempt)
    .sort((a, b) => a.seq - b.seq)
}

export interface RunAttemptKey {
  runId: string
  /** Client attachment epoch. The RunBlock key remains runId-only. */
  attempt: number
}

export interface RunWorkSeal extends RunAttemptKey {
  endedAtMs: number
}

export function sameRunAttempt(
  left: RunAttemptKey | null,
  right: RunAttemptKey | null,
): boolean {
  return left?.runId === right?.runId && left?.attempt === right?.attempt
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

/** Only a terminal snapshot on initial mount is historical hydration. An
 * explicit same-run recovery can also receive a terminal snapshot, but its
 * delivery may still be live, so it keeps the bounded review wait. */
export function isHistoricalRunTerminal({
  terminal,
  terminalSource,
  runStartedExplicitly,
}: {
  terminal: boolean
  terminalSource: RunTerminalSource
  runStartedExplicitly: boolean
}): boolean {
  return terminal && terminalSource === "snapshot" && !runStartedExplicitly
}

function parseMs(value: string | null): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

/** Latest observable step edge, used by the replay/no-reply fallback.
 * Invalid partial timestamps never poison it. */
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

interface WorkInterval {
  start: number
  end: number
}

function workInterval(
  startedAt: string | null,
  finishedAt: string | null,
): WorkInterval | null | "invalid" {
  if (startedAt == null && finishedAt == null) return null
  const start = parseMs(startedAt)
  const end = parseMs(finishedAt)
  if (start == null || end == null || end < start) return "invalid"
  return { start, end }
}

/** Union the observable work intervals. The current step row covers work
 * outside its internal stages; persisted stages retain earlier attempts after
 * the step's own timestamps move to a retry. Gaps between those intervals are
 * user/queue/review wait, not worked time. */
export function runWorkElapsedMs(
  runStartedAt: string | null,
  steps: WorkflowStep[],
  _workEndedAtMs: number | null,
  renderAttemptCount = 1,
): number | null {
  if (parseMs(runStartedAt) == null) return null
  const intervals: WorkInterval[] = []
  for (const step of steps) {
    const attempt = Math.max(
      step.attempt ?? 1,
      step.kind === "render" ? renderAttemptCount : 1,
    )
    const stages = step.production_stages ?? []
    if (attempt > 1) {
      const stageAttempts = new Set(stages.map((stage) => stage.attempt))
      for (let index = 1; index <= attempt; index += 1) {
        // A retried legacy step has already overwritten its earlier step
        // timestamps. Without each attempt's stages, a precise total is not
        // recoverable; fall back to the honest title/action count.
        if (!stageAttempts.has(index)) return null
      }
    }
    const currentStep = workInterval(step.started_at, step.finished_at)
    if (currentStep === "invalid") return null
    if (currentStep) intervals.push(currentStep)
    for (const stage of stages) {
      const interval = workInterval(stage.started_at, stage.finished_at)
      if (interval === "invalid" || interval === null) return null
      intervals.push(interval)
    }
  }
  if (intervals.length === 0) return null
  intervals.sort((a, b) => a.start - b.start || a.end - b.end)
  let elapsed = 0
  let current = intervals[0]
  for (const next of intervals.slice(1)) {
    if (next.start <= current.end) {
      current = { start: current.start, end: Math.max(current.end, next.end) }
    } else {
      elapsed += current.end - current.start
      current = next
    }
  }
  return elapsed + current.end - current.start
}

/** Write-once per attachment attempt. A late reply from an older run or an
 * earlier same-run recovery can neither seal the current attempt nor rewrite
 * its frozen clock. */
export function nextRunWorkSeal(
  current: RunWorkSeal | null,
  attached: RunAttemptKey | null,
  target: RunWorkSeal,
): RunWorkSeal | null {
  if (!sameRunAttempt(attached, target) || sameRunAttempt(current, target)) {
    return current
  }
  return target
}
