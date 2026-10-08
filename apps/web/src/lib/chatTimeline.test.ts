/** The conversation timeline layer's contract (ADR-108 数组位置律): the
 * persisted array's order IS the render order — buildConversationUnits MAPS
 * rows to units in place and never re-sorts; foldActivityUnits is the
 * display-layer folding projection (呈现层纯函数, ADR-110 段聚合). */

import { describe, expect, it } from "vitest"

import {
  buildConversationUnits,
  foldActivityUnits,
  foldSummary,
  type ConversationUnit,
} from "@/lib/chatTimeline"
import type { ActivityRowFrame, OverlayMessage } from "@/components/chat/historyReplay"

function msg(id: string, at?: string): OverlayMessage {
  return { id, role: "user", content: id, at }
}

function assistantMsg(id: string, at?: string): OverlayMessage {
  return { id, role: "assistant", content: id, at }
}

function activityMsg(
  id: string,
  over: Partial<ActivityRowFrame> = {},
): OverlayMessage {
  return {
    id: `row-${id}`,
    role: "assistant",
    content: "",
    activity: {
      activity_id: id,
      kind: "read",
      status: "completed",
      key: null,
      ...over,
    },
  }
}

function unitId(u: ConversationUnit): string {
  if (u.kind === "message") return u.message.id
  if (u.kind === "activity") return u.activity.activity_id
  return `fold:${u.rows.map((r) => r.activity_id).join("+")}`
}

function foldOf(u: ConversationUnit): {
  rows: ActivityRowFrame[]
  elapsedMs: number | null
} {
  if (u.kind !== "activityFold") throw new Error("expected a fold")
  return u
}

describe("buildConversationUnits — the array map (ADR-108)", () => {
  it("renders every row at its array position — NEVER re-sorted by timestamp", () => {
    // The array's order disagrees with the rows' `at` stamps on purpose:
    // the array wins, always (回放恒等性 — the live arrival order and the
    // replayed seq order are the same array).
    const units = buildConversationUnits([
      msg("user", "2026-09-23T08:00:05Z"),
      activityMsg("a1", { at: "2026-09-23T08:00:01Z" }),
      activityMsg("a2", { at: "2026-09-23T08:00:03Z" }),
      msg("reply", "2026-09-23T08:00:00Z"),
    ])
    expect(units.map(unitId)).toEqual(["user", "a1", "a2", "reply"])
  })

  it("an ACTIVE activity never renders in the walk — the now-line owns it (合一律)", () => {
    const units = buildConversationUnits([
      msg("user"),
      activityMsg("done"),
      activityMsg("live", { status: "active" }),
    ])
    expect(units.map(unitId)).toEqual(["user", "done"])
  })

  it("draft/run span rows stay retired — 落定即退役 (the card / receipt is the evidence)", () => {
    const units = buildConversationUnits([
      msg("user"),
      activityMsg("draft-done", { kind: "draft", key: "chat.activity.draftDone" }),
      activityMsg("edit-failed", {
        kind: "draft",
        status: "failed",
        key: "chat.activity.edit",
      }),
      activityMsg("milestone", { kind: "draft", key: "chat.explore.plansReady", count: 2 }),
      activityMsg("run-done", { kind: "run", key: "chat.activity.runDone" }),
      activityMsg("run-live", { kind: "run", status: "active", key: "chat.activity.run" }),
      msg("reply"),
    ])
    expect(units.map(unitId)).toEqual(["user", "milestone", "reply"])
  })
})

describe("foldActivityUnits — the segment aggregate (ADR-110)", () => {
  const read = (id: string, over: Partial<ActivityRowFrame> = {}) =>
    activityMsg(id, { key: "chat.inspectingDone.transcript", ...over })

  it("completed rows fold ACROSS different keys into ONE aggregate — the CC collapse", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        msg("user"),
        read("r1", { key: "chat.inspectingDone.understanding" }),
        read("r2", { key: "chat.explore.searchingDone" }),
        read("r3", { key: "chat.explore.candidatesReady", count: 12 }),
        assistantMsg("reply"),
      ]),
    )
    expect(units.map(unitId)).toEqual(["user", "fold:r1+r2+r3", "reply"])
    expect(foldSummary(foldOf(units[1]).rows)).toEqual([
      { key: "chat.inspectingDone.understanding", repeat: 1, count: undefined, name: undefined, total: undefined },
      { key: "chat.explore.searchingDone", repeat: 1, count: undefined, name: undefined, total: undefined },
      { key: "chat.explore.candidatesReady", repeat: 1, count: 12, name: undefined, total: undefined },
    ])
  })

  it("a lone settled row folds too (全收) — no bare rows between speeches", () => {
    const units = foldActivityUnits(
      buildConversationUnits([msg("user"), read("r1"), assistantMsg("reply")]),
    )
    expect(units.map(unitId)).toEqual(["user", "fold:r1", "reply"])
  })

  it("a fold never crosses a message boundary", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("a1"),
        read("a2"),
        assistantMsg("mid"),
        read("b1", { key: "chat.inspectingDone.segment" }),
        read("b2", { key: "chat.inspectingDone.segment" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:a1+a2", "mid", "fold:b1+b2"])
  })

  it("consecutive same-act rows merge into ONE ×N fragment inside the aggregate", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("r1", { duration_ms: 400 }),
        read("r2", { duration_ms: 600 }),
        read("r3", { key: "chat.explore.searchingDone" }),
        assistantMsg("reply"),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:r1+r2+r3", "reply"])
    // The merged fragment can't speak one honest artifact count — it drops
    // to undefined (the ×N repeat says the rest).
    expect(foldSummary(foldOf(units[0]).rows)).toEqual([
      { key: "chat.inspectingDone.transcript", repeat: 2, count: undefined, name: undefined, total: undefined },
      { key: "chat.explore.searchingDone", repeat: 1, count: undefined, name: undefined, total: undefined },
    ])
  })

  it("beats naming DIFFERENT files stay separate fragments of one aggregate", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        activityMsg("f1", { key: "chat.material.readingDone", name: "a.mp4" }),
        activityMsg("f2", { key: "chat.material.readingDone", name: "b.mp4" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:f1+f2"])
    expect(foldSummary(foldOf(units[0]).rows).map((f) => f.name)).toEqual([
      "a.mp4",
      "b.mp4",
    ])
  })

  it("failed/cancelled rows never fold — they stay visible and break the run", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("ok1", { key: "chat.inspectingDone.transcript" }),
        read("bad", { key: "chat.inspecting.transcript", status: "failed" }),
        read("ok2", { key: "chat.inspectingDone.transcript" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:ok1", "bad", "fold:ok2"])
  })

  it("elapsed = the segment wall clock — first row's birth → the prose's arrival", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("r1", { at: "2026-09-23T08:00:01Z", duration_ms: 400 }),
        read("r2", { at: "2026-09-23T08:00:03Z" }),
        assistantMsg("reply", "2026-09-23T08:00:10Z"),
      ]),
    )
    expect(foldOf(units[0]).elapsedMs).toBe(9000)
  })

  it("a USER-message boundary is no honest end — falls back to the last row's own end", () => {
    // The failed-turn scenario: the user may return hours later; their
    // message's stamp must not fabricate a multi-hour elapsed.
    const units = foldActivityUnits(
      buildConversationUnits([
        read("r1", { at: "2026-09-23T08:00:01Z" }),
        read("r2", { at: "2026-09-23T08:00:03Z", duration_ms: 2000 }),
        msg("user", "2026-09-23T11:00:00Z"),
      ]),
    )
    expect(foldOf(units[0]).elapsedMs).toBe(4000)
  })

  it("no boundary and no stamps → the summed durations; nothing measurable → null", () => {
    const withDurations = foldActivityUnits(
      buildConversationUnits([
        read("r1", { duration_ms: 400 }),
        read("r2", { duration_ms: 600 }),
      ]),
    )
    expect(foldOf(withDurations[0]).elapsedMs).toBe(1000)
    const bare = foldActivityUnits(buildConversationUnits([read("r1")]))
    expect(foldOf(bare[0]).elapsedMs).toBeNull()
  })
})
