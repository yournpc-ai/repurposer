/** The conversation timeline layer's contract (ADR-108 数组位置律): the
 * persisted array's order IS the render order — buildConversationUnits MAPS
 * rows to units in place and never re-sorts; foldActivityUnits is the
 * display-layer folding projection (呈现层纯函数). */

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

describe("foldActivityUnits — the display-layer fold (ADR-108 §6)", () => {
  const read = (id: string, over: Partial<ActivityRowFrame> = {}) =>
    activityMsg(id, { key: "chat.inspectingDone.transcript", ...over })

  it("≥2 consecutive settled rows of one act fold into ONE aggregate row", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        msg("user"),
        read("r1", { duration_ms: 400 }),
        read("r2", { duration_ms: 600 }),
        read("r3"),
        msg("reply"),
      ]),
    )
    expect(units.map(unitId)).toEqual(["user", "fold:r1+r2+r3", "reply"])
    const fold = units[1]
    if (fold.kind !== "activityFold") throw new Error("expected a fold")
    expect(foldSummary(fold.rows)).toEqual({
      key: "chat.inspectingDone.transcript",
      count: 3,
      totalMs: 1000,
    })
  })

  it("a lone settled row never folds", () => {
    const units = foldActivityUnits(
      buildConversationUnits([msg("user"), read("r1"), msg("reply")]),
    )
    expect(units.map(unitId)).toEqual(["user", "r1", "reply"])
  })

  it("a fold never crosses a message boundary or a different key", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("a1"),
        read("a2"),
        msg("mid"),
        read("b1", { key: "chat.inspectingDone.segment" }),
        read("b2", { key: "chat.inspectingDone.segment" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:a1+a2", "mid", "fold:b1+b2"])
  })

  it("beats naming DIFFERENT files never fold together (the name rides the fold key)", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        activityMsg("f1", { key: "chat.material.readingDone", name: "a.mp4" }),
        activityMsg("f2", { key: "chat.material.readingDone", name: "b.mp4" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["f1", "f2"])
  })

  it("failed rows carry the active-form key — they never fold into completed ones", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("ok1", { key: "chat.inspectingDone.transcript" }),
        read("bad", { key: "chat.inspecting.transcript", status: "failed" }),
        read("ok2", { key: "chat.inspectingDone.transcript" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["ok1", "bad", "ok2"])
  })
})
