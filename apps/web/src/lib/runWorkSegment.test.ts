import { describe, expect, it } from "vitest"

import {
  nextRunWorkSeal,
  runStepEndMs,
  runWorkElapsedMs,
  runWorkPhase,
  type RunWorkSeal,
} from "@/lib/runWorkSegment"
import type { WorkflowStep } from "@/lib/types"

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

describe("run work lifecycle", () => {
  it("run terminal opens the review phase instead of settling the row", () => {
    expect(
      runWorkPhase({ terminal: true, reviewPending: true, workEndedAtMs: null }),
    ).toBe("reviewing")
    expect(
      runWorkPhase({ terminal: false, reviewPending: true, workEndedAtMs: null }),
    ).toBe("running")
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

  it("the seal is run-scoped and write-once", () => {
    const first: RunWorkSeal = { runId: "run-a", endedAtMs: START_MS + 130_000 }
    expect(nextRunWorkSeal(null, "run-a", first)).toBe(first)
    expect(
      nextRunWorkSeal(first, "run-a", {
        runId: "run-a",
        endedAtMs: START_MS + 200_000,
      }),
    ).toBe(first)
    expect(
      nextRunWorkSeal(first, "run-b", {
        runId: "run-a",
        endedAtMs: START_MS + 200_000,
      }),
    ).toBe(first)
    const second: RunWorkSeal = { runId: "run-b", endedAtMs: START_MS + 200_000 }
    expect(nextRunWorkSeal(first, "run-b", second)).toBe(second)
  })

  it("uses the first-visible edge live and the observable step span on replay", () => {
    const steps = [step({})]
    const visibleAt = START_MS + 130_000
    expect(runWorkElapsedMs(START, steps, visibleAt)).toBe(130_000)
    expect(runWorkElapsedMs(START, steps, null)).toBe(120_000)
  })

  it("ignores invalid step timestamps and never invents an elapsed span", () => {
    const steps = [
      step({ id: "bad", finished_at: "not-a-date" }),
      step({ id: "last", seq: 2, finished_at: "2026-10-24T08:03:00Z" }),
    ]
    expect(runStepEndMs(START, steps)).toBe(START_MS + 180_000)
    expect(runWorkElapsedMs(null, steps, null)).toBeNull()
    expect(runWorkElapsedMs(START, steps, START_MS - 1)).toBeNull()
  })
})
