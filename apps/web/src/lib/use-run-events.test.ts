import { describe, expect, it } from "vitest"

import {
  createRunEventGeneration,
  nextRunAttachment,
  runEventsForAttachment,
  type RunEventsState,
} from "@/lib/use-run-events"

describe("run attachment generations", () => {
  it("the Chat landing uses the attachment ordinal even if the server counter arrived first", () => {
    expect(nextRunAttachment(0, true)).toEqual({ attempt: 1, uploadRetryCount: 1 })
    expect(nextRunAttachment(1, true)).toEqual({ attempt: 2, uploadRetryCount: 2 })
    expect(nextRunAttachment(2, false)).toEqual({ attempt: 0, uploadRetryCount: 0 })
  })

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
