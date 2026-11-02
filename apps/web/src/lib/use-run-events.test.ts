import { describe, expect, it } from "vitest"

import {
  createRunEventGeneration,
  runEventsForAttachment,
  type RunEventsState,
} from "@/lib/use-run-events"

describe("run attachment generations", () => {
  it("a same-run retry creates a new owner and rejects every old callback", () => {
    const generations = createRunEventGeneration()
    const failedAttempt = generations.begin()
    expect(generations.owns(failedAttempt)).toBe(true)

    const retryAttempt = generations.begin()
    expect(retryAttempt).not.toBe(failedAttempt)
    expect(generations.owns(failedAttempt)).toBe(false)
    expect(generations.owns(retryAttempt)).toBe(true)

    // Late cleanup from the old stream cannot invalidate the recovery either.
    generations.invalidate(failedAttempt)
    expect(generations.owns(retryAttempt)).toBe(true)
    generations.invalidate(retryAttempt)
    expect(generations.owns(retryAttempt)).toBe(false)
  })

  it("the new attachment is active immediately instead of reusing terminal state", () => {
    const failed: RunEventsState = {
      steps: [],
      status: "failed",
      progress: 100,
      createdAt: null,
      terminal: true,
      terminalSource: "update",
      uploadRetryCount: 0,
      subscriptionRunId: "run-1",
      subscriptionAttempt: 0,
    }
    const recovered = runEventsForAttachment(failed, "run-1", 1)
    expect(recovered).toMatchObject({
      status: "pending",
      terminal: false,
      terminalSource: null,
      subscriptionRunId: "run-1",
      subscriptionAttempt: 1,
    })
    expect(runEventsForAttachment(recovered, "run-1", 1)).toBe(recovered)
  })
})
