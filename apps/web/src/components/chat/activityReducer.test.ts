/** Activity reducer pair contract (ADR-087 §3 + Phase 3 Batch A): the
 * client side of the Activity Stream — upsert idempotence, arrival order,
 * the settle sweep's zero-dangling law, and the per-turn reset. */

import { describe, expect, it } from "vitest"

import {
  resetActivities,
  sweepActivities,
  upsertActivityFrame,
} from "./activityReducer"
import type { ActivityFramePayload } from "@/lib/chat-stream"

function frame(
  id: string,
  status: ActivityFramePayload["status"],
  seq = 1,
): ActivityFramePayload {
  return { activity_id: id, seq, kind: "read", status, key: null }
}

describe("upsertActivityFrame", () => {
  it("first sighting appends in arrival order", () => {
    let list: ActivityFramePayload[] = []
    list = upsertActivityFrame(list, frame("a", "active", 1))
    list = upsertActivityFrame(list, frame("b", "active", 1))
    expect(list.map((a) => a.activity_id)).toEqual(["a", "b"])
  })

  it("a status flip on the same id replaces in place (append-only wire, ordered map)", () => {
    let list: ActivityFramePayload[] = []
    list = upsertActivityFrame(list, frame("a", "active", 1))
    list = upsertActivityFrame(list, frame("b", "active", 1))
    list = upsertActivityFrame(list, frame("a", "completed", 2))
    expect(list.map((a) => [a.activity_id, a.status])).toEqual([
      ["a", "completed"],
      ["b", "active"],
    ])
  })

  it("is idempotent: the same frame redelivered never duplicates", () => {
    let list: ActivityFramePayload[] = []
    list = upsertActivityFrame(list, frame("a", "active", 1))
    list = upsertActivityFrame(list, frame("a", "active", 1))
    expect(list).toHaveLength(1)
  })

  it("never mutates the previous list (React state discipline)", () => {
    const prev = [frame("a", "active", 1)]
    const next = upsertActivityFrame(prev, frame("a", "completed", 2))
    expect(prev[0].status).toBe("active")
    expect(next[0].status).toBe("completed")
  })

  it("keeps the FIRST-seen `at` as the birth moment; the settle frame's own at never moves the row (S7/E7)", () => {
    let list: ActivityFramePayload[] = []
    list = upsertActivityFrame(list, {
      ...frame("a", "active", 1),
      at: "2026-09-23T08:00:00.000Z",
    })
    list = upsertActivityFrame(list, {
      ...frame("a", "completed", 2),
      at: "2026-09-23T08:00:01.200Z",
      duration_ms: 1200,
    })
    expect(list[0].at).toBe("2026-09-23T08:00:00.000Z")
    expect(list[0].status).toBe("completed")
    expect(list[0].duration_ms).toBe(1200)
  })

  it("a first frame without `at` yields to the settle frame's stamp (defensive, pre-S7 wire)", () => {
    let list: ActivityFramePayload[] = []
    list = upsertActivityFrame(list, frame("a", "active", 1))
    list = upsertActivityFrame(list, {
      ...frame("a", "completed", 2),
      at: "2026-09-23T08:00:01.200Z",
    })
    expect(list[0].at).toBe("2026-09-23T08:00:01.200Z")
  })
})

describe("sweepActivities — zero dangling (假活跃禁令)", () => {
  it("flips every still-active frame to the terminal status", () => {
    const list = [frame("a", "active"), frame("b", "active")]
    const swept = sweepActivities(list, "completed")
    expect(swept.every((a) => a.status === "completed")).toBe(true)
  })

  it("leaves already-terminal frames untouched", () => {
    const list = [frame("a", "completed"), frame("b", "failed"), frame("c", "active")]
    const swept = sweepActivities(list, "cancelled")
    expect(swept.map((a) => a.status)).toEqual(["completed", "failed", "cancelled"])
  })

  it("after a sweep, no active frame survives (T16-B client twin)", () => {
    const list = [frame("a", "active"), frame("b", "completed"), frame("c", "active")]
    for (const status of ["completed", "failed", "cancelled"] as const) {
      expect(
        sweepActivities(list, status).some((a) => a.status === "active"),
      ).toBe(false)
    }
  })
})

describe("resetActivities — the per-turn block", () => {
  it("a new turn starts from an empty stream (v1 no-persistence line)", () => {
    const settled = sweepActivities([frame("a", "active")], "completed")
    const nextTurn = resetActivities()
    expect(nextTurn).toEqual([])
    // the settled turn's history is untouched by the next turn's reset
    expect(settled[0].status).toBe("completed")
  })
})
