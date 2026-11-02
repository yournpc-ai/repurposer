import { describe, expect, it } from "vitest"

import {
  nextRunWorkSeal,
  isHistoricalRunTerminal,
  runStepEndMs,
  runWorkElapsedMs,
  runWorkPhase,
  sameRunAttempt,
  visibleProductionStages,
  type RunWorkSeal,
} from "@/lib/runWorkSegment"
import type { ProductionStage, WorkflowStep } from "@/lib/types"

const START = "2026-10-24T08:00:00Z"
const START_MS = Date.parse(START)

function step(over: Partial<WorkflowStep>): WorkflowStep {
  return {
    id: "s1",
    kind: "render",
    status: "done",
    seq: 1,
    error: null,
    cost: null,
    started_at: START,
    finished_at: "2026-10-24T08:02:00Z",
    ...over,
  }
}

function productionStage(over: Partial<ProductionStage>): ProductionStage {
  return {
    event_id: "stage-1",
    kind: "validate",
    run_id: "run-1",
    step_id: "s1",
    attempt: 1,
    seq: 0,
    status: "completed",
    started_at: START,
    finished_at: "2026-10-24T08:01:00Z",
    ...over,
  }
}

describe("RunBlock production-stage projection", () => {
  it("legacy Runs keep their original Prepare/Render display with no backfill", () => {
    expect(visibleProductionStages(step({ production_stages: undefined }))).toEqual([])
  })

  it("live snapshots and history project only the current attempt in persistent seq order", () => {
    const current = step({
      attempt: 2,
      production_stages: [
        productionStage({ event_id: "old-running", attempt: 1, status: "running", seq: 0 }),
        productionStage({ event_id: "new-second", attempt: 2, status: "running", seq: 2 }),
        productionStage({ event_id: "new-first", attempt: 2, seq: 1 }),
      ],
    })
    const project = (value: WorkflowStep) =>
      visibleProductionStages(value).map((stage) => stage.event_id)
    expect(project(current)).toEqual(["new-first", "new-second"])

    const lateOldAttempt = {
      ...current,
      production_stages: current.production_stages?.map((stage) =>
        stage.attempt === 1 ? { ...stage, status: "failed" as const } : stage,
      ),
    }
    expect(project(lateOldAttempt)).toEqual(project(current))
  })
})

describe("run work lifecycle", () => {
  it("run terminal opens the review phase instead of settling the row", () => {
    expect(
      runWorkPhase({ terminal: true, reviewPending: true, workEndedAtMs: null }),
    ).toBe("reviewing")
    expect(
      runWorkPhase({ terminal: false, reviewPending: true, workEndedAtMs: null }),
    ).toBe("running")
  })

  it("historical snapshots never replay reviewing, unlike a live recovery snapshot", () => {
    expect(isHistoricalRunTerminal({
      terminal: true,
      terminalSource: "snapshot",
      runStartedExplicitly: false,
    })).toBe(true)
    expect(isHistoricalRunTerminal({
      terminal: true,
      terminalSource: "snapshot",
      runStartedExplicitly: true,
    })).toBe(false)
    expect(isHistoricalRunTerminal({
      terminal: true,
      terminalSource: "update",
      runStartedExplicitly: false,
    })).toBe(false)
  })

  it("a visible-delivery seal settles once, even while the reply is still typing", () => {
    expect(
      runWorkPhase({
        terminal: true,
        reviewPending: true,
        workEndedAtMs: START_MS + 130_000,
      }),
    ).toBe("settled")
    expect(
      runWorkPhase({ terminal: true, reviewPending: false, workEndedAtMs: null }),
    ).toBe("settled")
  })

  it("seals once per run attachment and ignores older attempts", () => {
    expect(sameRunAttempt(null, null)).toBe(true)
    expect(sameRunAttempt(null, { runId: "run-a", attempt: 0 })).toBe(false)
    const firstAttachment = { runId: "run-a", attempt: 0 }
    const first: RunWorkSeal = { ...firstAttachment, endedAtMs: START_MS + 130_000 }
    expect(nextRunWorkSeal(null, firstAttachment, first)).toBe(first)
    expect(
      nextRunWorkSeal(first, firstAttachment, {
        ...firstAttachment,
        endedAtMs: START_MS + 200_000,
      }),
    ).toBe(first)
    expect(
      nextRunWorkSeal(first, { runId: "run-b", attempt: 0 }, {
        ...firstAttachment,
        endedAtMs: START_MS + 200_000,
      }),
    ).toBe(first)

    const retryAttachment = { runId: "run-a", attempt: 1 }
    const retry: RunWorkSeal = { ...retryAttachment, endedAtMs: START_MS + 260_000 }
    expect(nextRunWorkSeal(first, retryAttachment, retry)).toBe(retry)
    expect(nextRunWorkSeal(retry, retryAttachment, first)).toBe(retry)

    const otherRun: RunWorkSeal = { runId: "run-b", attempt: 0, endedAtMs: START_MS + 300_000 }
    expect(nextRunWorkSeal(retry, { runId: "run-b", attempt: 0 }, otherRun)).toBe(otherRun)
  })

  it("uses observable work, never the delivery review wait", () => {
    const steps = [step({})]
    const visibleAt = START_MS + 130_000
    expect(runWorkElapsedMs(START, steps, visibleAt)).toBe(120_000)
    expect(runWorkElapsedMs(START, steps, null)).toBe(120_000)
  })

  it("excludes the user's wait between a failed attempt and its retry", () => {
    const retry = step({
      attempt: 2,
      started_at: "2026-10-24T12:00:00Z",
      finished_at: "2026-10-24T12:02:00Z",
      production_stages: [
        productionStage({
          event_id: "failed-attempt",
          attempt: 1,
          status: "failed",
          started_at: START,
          finished_at: "2026-10-24T08:01:00Z",
        }),
        productionStage({
          event_id: "retry-render",
          attempt: 2,
          started_at: "2026-10-24T12:00:00Z",
          finished_at: "2026-10-24T12:01:00Z",
        }),
      ],
    })
    expect(runWorkElapsedMs(
      START,
      [retry],
      Date.parse("2026-10-24T15:00:00Z"),
    )).toBe(180_000)
  })

  it("unions every persisted attempt without inventing the idle gaps", () => {
    const retried = step({
      attempt: 3,
      started_at: "2026-10-24T12:00:00Z",
      finished_at: "2026-10-24T12:01:00Z",
      production_stages: [
        productionStage({ event_id: "a1", attempt: 1, finished_at: "2026-10-24T08:00:30Z" }),
        productionStage({
          event_id: "a2",
          attempt: 2,
          started_at: "2026-10-24T09:00:00Z",
          finished_at: "2026-10-24T09:00:45Z",
        }),
        productionStage({
          event_id: "a3",
          attempt: 3,
          started_at: "2026-10-24T12:00:00Z",
          finished_at: "2026-10-24T12:00:20Z",
        }),
      ],
    })
    expect(runWorkElapsedMs(START, [retried], null)).toBe(135_000)
  })

  it("counts overlapping step and stage intervals only once", () => {
    const first = step({
      production_stages: [productionStage({
        started_at: "2026-10-24T08:00:30Z",
        finished_at: "2026-10-24T08:01:30Z",
      })],
    })
    const second = step({
      id: "s2",
      seq: 2,
      started_at: "2026-10-24T08:01:00Z",
      finished_at: "2026-10-24T08:03:00Z",
    })
    expect(runWorkElapsedMs(START, [first, second], null)).toBe(180_000)
  })

  it("old or partial retry facts fall back instead of showing false precision", () => {
    expect(runWorkElapsedMs(null, [step({})], null)).toBeNull()
    expect(runWorkElapsedMs(START, [step({ attempt: 2 })], null)).toBeNull()
    expect(runWorkElapsedMs(START, [step({
      attempt: 0,
      started_at: "2026-10-24T12:00:00Z",
      finished_at: "2026-10-24T12:02:00Z",
    })], null, 2)).toBeNull()
    expect(runWorkElapsedMs(START, [step({
      production_stages: [productionStage({ finished_at: null, status: "running" })],
    })], null)).toBeNull()
  })

  it("invalid step timestamps cannot become an elapsed span", () => {
    const steps = [
      step({ id: "bad", finished_at: "not-a-date" }),
      step({ id: "last", seq: 2, finished_at: "2026-10-24T08:03:00Z" }),
    ]
    expect(runStepEndMs(START, steps)).toBe(START_MS + 180_000)
    expect(runWorkElapsedMs(START, steps, null)).toBeNull()
  })
})
