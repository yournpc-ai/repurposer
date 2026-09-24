/** The shared moment-ordering layer's contract (iter-3 S7, E7): one
 * (moment, arrival-order) sort for every mixed timeline — messages ×
 * activity rows interleave by real time and the stream never scrambles. */

import { describe, expect, it } from "vitest"

import {
  buildConversationUnits,
  momentOf,
  orderMoments,
} from "@/lib/chatTimeline"
import type { ActivityFramePayload } from "@/lib/chat-stream"
import type { OverlayMessage } from "@/components/chat/historyReplay"

function msg(id: string, at?: string): OverlayMessage {
  return { id, role: "user", content: id, at }
}

function activity(id: string, at?: string): ActivityFramePayload {
  return { activity_id: id, seq: 1, kind: "read", status: "completed", key: null, at }
}

describe("momentOf", () => {
  it("parses ISO; missing/unparseable = undated (+∞), never a guess", () => {
    expect(momentOf("2026-09-23T08:00:00Z")).toBe(Date.parse("2026-09-23T08:00:00Z"))
    expect(momentOf(undefined)).toBe(Number.POSITIVE_INFINITY)
    expect(momentOf("not-a-date")).toBe(Number.POSITIVE_INFINITY)
  })
})

describe("orderMoments", () => {
  it("sorts by moment, arrival order as the stable tiebreak", () => {
    const units = orderMoments<string>([
      { t: 300, order: 0, unit: "c" },
      { t: 100, order: 1, unit: "a" },
      { t: 100, order: 2, unit: "b" },
    ])
    expect(units).toEqual(["a", "b", "c"])
  })

  it("never mutates the input", () => {
    const entries = [
      { t: 2, order: 0, unit: "b" },
      { t: 1, order: 1, unit: "a" },
    ]
    orderMoments(entries)
    expect(entries.map((e) => e.unit)).toEqual(["b", "a"])
  })
})

describe("buildConversationUnits — the non-run single stream", () => {
  it("a turn's activity rows land BETWEEN the user echo and the assistant reply", () => {
    const units = buildConversationUnits(
      [
        msg("user", "2026-09-23T08:00:00Z"),
        msg("reply", "2026-09-23T08:00:05Z"),
      ],
      [
        activity("a1", "2026-09-23T08:00:01Z"),
        activity("a2", "2026-09-23T08:00:03Z"),
      ],
    )
    expect(units.map((u) => (u.kind === "message" ? u.message.id : u.activity.activity_id))).toEqual([
      "user",
      "a1",
      "a2",
      "reply",
    ])
  })

  it("undated rows (optimistic sends / pre-S7 frames) land at the end, arrival order kept", () => {
    const units = buildConversationUnits(
      [msg("dated", "2026-09-23T08:00:00Z"), msg("fresh")],
      [activity("a1", "2026-09-23T08:00:01Z"), activity("legacy")],
    )
    expect(units.map((u) => (u.kind === "message" ? u.message.id : u.activity.activity_id))).toEqual([
      "dated",
      "a1",
      "fresh",
      "legacy",
    ])
  })

  it("a same-moment tie lands the message first (messages claim the lower order numbers)", () => {
    const units = buildConversationUnits(
      [msg("m", "2026-09-23T08:00:00Z")],
      [activity("a", "2026-09-23T08:00:00Z")],
    )
    expect(units.map((u) => u.kind)).toEqual(["message", "activity"])
  })

  it("empty activities = the messages verbatim (the pre-S7 shape)", () => {
    const units = buildConversationUnits([msg("a"), msg("b")], [])
    expect(units.map((u) => u.kind)).toEqual(["message", "message"])
  })

  it("an ACTIVE activity never interleaves — the now-line owns it until it settles (2026-09-24 合一律)", () => {
    const live = { ...activity("live", "2026-09-23T08:00:02Z"), status: "active" as const }
    const units = buildConversationUnits(
      [msg("user", "2026-09-23T08:00:00Z")],
      [activity("done", "2026-09-23T08:00:01Z"), live],
    )
    expect(units.map((u) => (u.kind === "message" ? u.message.id : u.activity.activity_id))).toEqual([
      "user",
      "done",
    ])
  })
})
