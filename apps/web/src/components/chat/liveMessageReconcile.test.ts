import { describe, expect, it } from "vitest"

import type { OverlayMessage } from "./historyReplay"
import {
  insertRecoveredMessage,
  isFreshPolledRow,
  observedMessageSeq,
  prependMissingHistory,
  shouldAdmitPolledTrigger,
} from "./liveMessageReconcile"

function message(
  id: string,
  seq?: number,
  overrides: Partial<OverlayMessage> = {},
): OverlayMessage {
  return {
    id,
    role: "assistant",
    content: id,
    ...(seq == null ? {} : { seq }),
    ...overrides,
  }
}

describe("run review poll admission", () => {
  it("does not revive an activity from before the observed tail", () => {
    expect(isFreshPolledRow(6, 14)).toBe(false)
    expect(isFreshPolledRow(6, null)).toBe(false)
    expect(isFreshPolledRow(null, 14)).toBe(false)
  })

  it("admits a newly landed activity on the next poll", () => {
    expect(isFreshPolledRow(15, 14)).toBe(true)
  })

  it("keeps the observation watermark ahead of rendered rows", () => {
    expect(observedMessageSeq(20, [message("old", 4), message("new", 14)])).toBe(20)
    expect(observedMessageSeq(null, [message("old", 4), message("local")])).toBe(4)
  })

  it("scopes run review speech to its own run without backfilling generic watches", () => {
    expect(
      shouldAdmitPolledTrigger({ fresh: false, reviewRunId: null, rowRunId: "run-1" }),
    ).toBe(false)
    expect(
      shouldAdmitPolledTrigger({ fresh: false, reviewRunId: "run-1", rowRunId: "run-1" }),
    ).toBe(true)
    expect(
      shouldAdmitPolledTrigger({ fresh: true, reviewRunId: "run-1", rowRunId: "run-2" }),
    ).toBe(false)
  })
})

describe("recovered prose placement", () => {
  it("places a scoped late delivery before an already visible later server row", () => {
    const result = insertRecoveredMessage(
      [message("start", 14), message("later", 16)],
      message("trigger", 12),
      { fresh: false },
    )
    expect(result.map((row) => row.id)).toEqual(["trigger", "start", "later"])
  })

  it("places a backfill before the optimistic suffix, not after the user's newer row", () => {
    const result = insertRecoveredMessage(
      [message("start", 10), message("local-user", undefined, { role: "user" })],
      message("trigger", 12),
      { fresh: false },
    )
    expect(result.map((row) => row.id)).toEqual(["start", "trigger", "local-user"])
  })

  it("keeps a fresh delivery at the live edge while preserving typewriter state", () => {
    const local = message("local-user", undefined, { role: "user" })
    const result = insertRecoveredMessage(
      [message("start", 14), local],
      message("delivery", 15, { streaming: true }),
      { fresh: true },
    )
    expect(result.map((row) => row.id)).toEqual(["start", "local-user", "delivery"])
    expect(result[1]).toBe(local)
    expect(result[2].streaming).toBe(true)
  })

  it("uses seq rather than arrival order when a newer row won the race", () => {
    const result = insertRecoveredMessage(
      [message("start", 14), message("next", 16)],
      message("delivery", 15),
      { fresh: true },
    )
    expect(result.map((row) => row.id)).toEqual(["start", "delivery", "next"])
  })

  it("deduplicates a row already recovered by another channel", () => {
    const previous = [message("delivery", 15, { streaming: true })]
    expect(
      insertRecoveredMessage(previous, message("delivery", 15), { fresh: true }),
    ).toBe(previous)
  })
})

describe("run terminal recovery journey", () => {
  it("ignores an old material row while landing the new delivery after the visible start", () => {
    const previous = [message("start", 14)]
    const oldActivity = message("old-web-page", 6, {
      content: "",
      activity: { activity_id: "read-6", kind: "read", status: "completed", key: "done" },
    })
    const afterOldActivity = isFreshPolledRow(oldActivity.seq, 14)
      ? insertRecoveredMessage(previous, oldActivity, { fresh: false })
      : previous
    expect(afterOldActivity).toBe(previous)
    const result = insertRecoveredMessage(
      afterOldActivity,
      message("delivery", 15, { streaming: true }),
      { fresh: isFreshPolledRow(15, 14) },
    )
    expect(result.map((row) => row.id)).toEqual(["start", "delivery"])
  })
})

describe("mount history replay", () => {
  it("prepends only archive ids absent from the live array", () => {
    const live = message("live", 2, { streaming: true })
    const result = prependMissingHistory(
      [live],
      [message("archive", 1), message("live", 2)],
    )
    expect(result.map((row) => row.id)).toEqual(["archive", "live"])
    expect(result[1]).toBe(live)
  })
})
