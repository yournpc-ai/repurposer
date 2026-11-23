/** Transcript position, turn ownership, evidence and display-clock contracts. */

import { mapHistoryRows } from "./history"
import { describe, expect, it } from "vitest"

import {
  activityCategoryKey,
  activityFailureKey,
  foldActivityUnits,
} from "./activity"
import {
  buildConversationBlocks,
  conversationBlockUnits,
  buildConversationUnits,
  closeWorkSegment,
} from "./project"
import type {
  ActivityRowFrame,
  ConversationBlock,
  ConversationUnit,
  OverlayMessage,
} from "./types"

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

function blockUnits(block: ConversationBlock): ConversationUnit[] {
  return conversationBlockUnits(block)
}

function foldOf(u: ConversationUnit): {
  rows: ActivityRowFrame[]
  failure: ActivityRowFrame | null
  startedAtMs: number | null
  endedAtMs: number | null
  elapsedMs: number | null
  openTail: boolean
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

  it("holds Activity out of the visible walk until interim prose settles", () => {
    const held = {
      ...activityMsg("held", { status: "active" }),
      activityDisplayHeld: true,
    }
    expect(buildConversationUnits([
      assistantMsg("opening"),
      held,
      assistantMsg("later"),
    ]).map(unitId)).toEqual(["opening", "later"])

    expect(buildConversationUnits([
      assistantMsg("opening"),
      { ...held, activityDisplayHeld: undefined },
      assistantMsg("later"),
    ]).map(unitId)).toEqual(["opening", "held", "later"])
  })

  it("an ACTIVE activity enters the walk at its host position and owns the live segment", () => {
    const rows = [
      {
        ...assistantMsg("interim_prose"),
        streaming: true,
      },
      activityMsg("live", {
        status: "active",
        at: "2026-10-24T08:00:01Z",
      }),
    ]
    const units = foldActivityUnits(buildConversationUnits(rows))
    expect(units.map(unitId)).toEqual(["interim_prose", "fold:"])
    const fold = foldOf(units[1])
    expect(fold.rows).toEqual([])
    expect(fold.openTail).toBe(true)
    expect(units[1]).toMatchObject({
      rowKey: "row-live",
      firstActivityAt: "2026-10-24T08:00:01Z",
    })

    // An active-only attempt is not completed work and must not seal as one.
    expect(closeWorkSegment(rows, new Set(["row-live"]), 10_000)).toBe(rows)

    const completed = rows.map((m) =>
      m.id === "row-live" && m.activity
        ? {
            ...m,
            activity: {
              ...m.activity,
              status: "completed" as const,
              duration_ms: 62,
            },
          }
        : m,
    )
    const settled = foldActivityUnits(buildConversationUnits(completed))
    expect(settled[1]).toMatchObject({ rowKey: "row-live" })
    expect(foldOf(settled[1]).rows.map((r) => r.activity_id)).toEqual(["live"])
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

  it("the storyboard span's settle RENDERS — the one 落定即退役 exception (分镜不是开工)", () => {
    // 2026-10-17 user ruling: no docked card absorbs the design beat — the
    // markdown message is the deliverable and the settled row (carrying its
    // honest duration) is the receipt; it folds like any completed span.
    const units = buildConversationUnits([
      msg("user"),
      activityMsg("sb-done", {
        kind: "draft",
        key: "chat.activity.storyboardDone",
        duration_ms: 32500,
      }),
      msg("reply"),
    ])
    expect(units.map(unitId)).toEqual(["user", "sb-done", "reply"])
    const folded = foldActivityUnits(units)
    const fold = foldOf(folded[1])
    expect(fold.rows.map((r) => r.activity_id)).toEqual(["sb-done"])
    expect(fold.rows[0].duration_ms).toBe(32500)
  })

  it("video design, revision and review receipts all survive history replay", () => {
    const keys = [
      "chat.activity.videoDesignDone",
      "chat.activity.videoReviseDone",
      "chat.activity.videoReviewDone",
    ]
    const units = buildConversationUnits([
      msg("user"),
      ...keys.map((key, index) => activityMsg(`video-${index}`, { kind: "draft", key })),
      msg("reply"),
    ])

    expect(units.map(unitId)).toEqual(["user", "video-0", "video-1", "video-2", "reply"])
  })

  it("the PATCH variant's pair rides the same exception — an adjust receipt renders", () => {
    // A targeted edit's span persists exactly like the compose span: the
    // storyboardEdit/storyboardEditDone keys must NOT be swallowed by the
    // draft filter (missing the exemption would make the patch receipt
    // vanish from the timeline entirely).
    const units = buildConversationUnits([
      msg("user"),
      activityMsg("sb-edit-live", {
        kind: "draft",
        status: "active",
        key: "chat.activity.storyboardEdit",
      }),
      activityMsg("sb-edit-done", {
        kind: "draft",
        key: "chat.activity.storyboardEditDone",
        duration_ms: 4100,
      }),
      activityMsg("sb-edit-cancelled", {
        kind: "draft",
        status: "cancelled",
        key: "chat.activity.storyboardEdit",
      }),
      msg("reply"),
    ])
    // The active attempt owns the live segment; its accepted successor joins
    // that segment, while the cancelled attempt leaves no visible row.
    expect(units.map(unitId)).toEqual([
      "user",
      "sb-edit-live",
      "sb-edit-done",
      "reply",
    ])
    const folded = foldActivityUnits(units)
    expect(folded.map(unitId)).toEqual(["user", "fold:sb-edit-done", "reply"])
    expect(folded[1]).toMatchObject({ rowKey: "row-sb-edit-live" })
  })
})

describe("foldActivityUnits — the segment aggregate (ADR-110)", () => {
  const read = (id: string, over: Partial<ActivityRowFrame> = {}) =>
    activityMsg(id, { key: "chat.inspectingDone.transcript", ...over })

  it("2+ completed rows fold ACROSS different keys into ONE aggregate — the CC collapse", () => {
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
    expect(foldOf(units[1]).rows.map(r => [r.key, r.count])).toEqual([
      ["chat.inspectingDone.understanding", undefined],
      ["chat.explore.searchingDone", undefined],
      ["chat.explore.candidatesReady", 12],
    ])
  })

  it("a lone settled row folds too (2026-10-16 ruling — 完成就收, no single-row exemption)", () => {
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

  it("retains each material name, category, count and duration in its original position", () => {
    const materials = [
      read("r1", { name: "a.pdf", duration_ms: 400 }),
      read("r2", { assetType: "web_page", name: "b.test", count: 2, total: 3 }),
      read("r3", { name: "a.pdf", count: 4 }),
    ]
    const [fold] = foldActivityUnits(buildConversationUnits(materials))
    expect(foldOf(fold).rows).toEqual(materials.map(m => m.activity))
  })

  it("a contiguous failure settles the current segment without a second top-level status", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("ok1", { key: "chat.inspectingDone.transcript" }),
        read("bad", { key: "chat.inspecting.transcript", status: "failed" }),
        read("ok2", { key: "chat.inspectingDone.transcript" }),
        read("ok3", { key: "chat.inspectingDone.transcript" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:ok1", "fold:ok2+ok3"])
    expect(units[0]).toMatchObject({
      rowKey: "row-ok1",
      openTail: false,
      failure: { activity_id: "bad", status: "failed" },
    })
    expect(foldOf(units[1]).openTail).toBe(true)
  })

  it("an isolated failure stays standalone and never merges across prose", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("ok1"),
        assistantMsg("middle"),
        read("bad", { status: "failed" }),
        read("ok2"),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:ok1", "middle", "bad", "fold:ok2"])
  })

  it("a failed segment uses one wall clock, not Worked time plus the failed tool duration", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("ok1", { at: "1970-01-01T00:00:01.000Z", duration_ms: 400 }),
        read("bad", {
          at: "1970-01-01T00:00:02.000Z",
          duration_ms: 23_000,
          status: "failed",
        }),
      ]),
    )
    expect(foldOf(units[0])).toMatchObject({
      endedAtMs: 25_000,
      elapsedMs: 24_000,
      openTail: false,
      failure: { activity_id: "bad" },
    })
  })

  it("cancelled attempts retire without leaving a row or breaking the work segment", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("ok1", { key: "chat.inspectingDone.transcript" }),
        read("retry", {
          key: "chat.activity.storyboardEdit",
          kind: "draft",
          status: "cancelled",
          duration_ms: 62,
        }),
        read("ok2", { key: "chat.inspectingDone.transcript" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:ok1+ok2"])
  })

  it("an automatic retry sequence shows only the current live attempt and its eventual receipt", () => {
    const attempt = (id: string, status: ActivityRowFrame["status"]) =>
      activityMsg(id, {
        kind: "draft",
        status,
        key: status === "completed"
          ? "chat.activity.storyboardEditDone"
          : "chat.activity.storyboardEdit",
        duration_ms: status === "cancelled" ? 62 : undefined,
      })
    const rows = [
      assistantMsg("interim_prose-1"),
      attempt("attempt-1", "cancelled"),
      assistantMsg("interim_prose-2"),
      attempt("attempt-2", "cancelled"),
      { ...assistantMsg("interim_prose-3"), streaming: true },
      attempt("attempt-3", "active"),
    ]
    const live = foldActivityUnits(buildConversationUnits(rows))
    expect(live.map(unitId)).toEqual([
      "interim_prose-1",
      "interim_prose-2",
      "interim_prose-3",
      "fold:",
    ])
    expect(live[3]).toMatchObject({ rowKey: "row-attempt-3", openTail: true })

    const accepted = rows.map((m) =>
      m.id === "row-attempt-3" ? attempt("attempt-3", "completed") : m,
    )
    const sealed = closeWorkSegment(accepted, new Set(["row-attempt-3"]), 35_000)
    const settled = foldActivityUnits(buildConversationUnits(sealed))
    expect(settled.map(unitId)).toEqual([
      "interim_prose-1",
      "interim_prose-2",
      "interim_prose-3",
      "fold:attempt-3",
    ])
    expect(foldOf(settled[3])).toMatchObject({
      endedAtMs: 35_000,
      openTail: false,
    })
  })

  it("fold 展开 = 原帧归位 (flora-parity-ui D4①): the fold keeps the ORIGINAL row frames — the expanded view renders the same identities, never copies", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("f1", { key: "chat.inspectingDone.transcript" }),
        read("f2", { key: "chat.inspectingDone.transcript" }),
      ]),
    )
    const rows = foldOf(units[0]).rows
    expect(rows.map((r) => r.activity_id)).toEqual(["f1", "f2"])
    // 展开态的类目分解从原帧投影(显示层不改写载荷) —— 折叠永不丢失行的
    // key/count/duration,审计继续读落库行。
    expect(rows[0]).toMatchObject({ key: "chat.inspectingDone.transcript" })
  })

  it("unsealed / replayed work falls back to the activity span — assistant created_at is not first-visible time", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("r1", { at: "2026-09-23T08:00:01Z", duration_ms: 400 }),
        read("r2", { at: "2026-09-23T08:00:03Z" }),
        assistantMsg("reply", "2026-09-23T08:00:10Z"),
      ]),
    )
    expect(foldOf(units[0]).elapsedMs).toBe(2000)
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

  it("a run-carrying assistant boundary is no honest end either — the run's span belongs to the receipt row", () => {
    // The zymix shape: material beats, then the DELIVERY prose stamped at
    // run completion. The prose's stamp must not stretch the fold's clock
    // over the whole run — the receipt already reports that total.
    const units = foldActivityUnits(
      buildConversationUnits([
        read("r1", { at: "2026-09-23T08:00:01Z" }),
        read("r2", { at: "2026-09-23T08:00:03Z", duration_ms: 2000 }),
        {
          id: "delivery",
          role: "assistant",
          content: "delivered",
          at: "2026-09-23T08:10:00Z",
        },
      ]),
    )
    expect(foldOf(units[0]).elapsedMs).toBe(4000)
  })

  it("openTail marks ONLY the walk's trailing fold — completed tail remains displayable while the turn continues", () => {
    // A fold closed by ANY following unit (the prose's boundary, a user
    // message, a run-carrying row) is settled — openTail stays false. The
    // trailing fold (no boundary exists yet) is the one open segment.
    const units = foldActivityUnits(
      buildConversationUnits([
        read("a1", { at: "2026-09-23T08:00:01Z" }),
        assistantMsg("reply", "2026-09-23T08:00:10Z"),
        read("b1", { at: "2026-09-23T08:00:20Z" }),
        msg("user", "2026-09-23T11:00:00Z"),
        read("c1", { at: "2026-09-23T11:00:05Z" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:a1", "reply", "fold:b1", "user", "fold:c1"])
    expect(foldOf(units[0]).openTail).toBe(false)
    expect(foldOf(units[2]).openTail).toBe(false)
    expect(foldOf(units[4]).openTail).toBe(true)
  })

  it("parallel durations are NEVER summed into a pretend wall clock; no timestamps → honest null", () => {
    const withDurations = foldActivityUnits(
      buildConversationUnits([
        read("r1", { duration_ms: 400 }),
        read("r2", { duration_ms: 600 }),
      ]),
    )
    expect(foldOf(withDurations[0]).elapsedMs).toBeNull()
    const bare = foldActivityUnits(
      buildConversationUnits([read("r1"), read("r2")]),
    )
    expect(foldOf(bare[0]).elapsedMs).toBeNull()
  })
})

describe("work-segment display lifecycle and clock", () => {
  const read = (id: string, over: Partial<ActivityRowFrame> = {}) =>
    activityMsg(id, { key: "chat.inspectingDone.transcript", ...over })

  it("an empty preview stays open; the display / terminal seal freezes send → first-visible wall time", () => {
    const rows: OverlayMessage[] = [
      msg("user", "2026-10-24T08:00:00Z"),
      read("r1", { at: "2026-10-24T08:00:01Z", duration_ms: 1000 }),
      read("r2", { at: "2026-10-24T08:00:05Z", duration_ms: 2000 }),
      {
        id: "reply",
        role: "assistant",
        content: "",
        streaming: true,
      },
    ]
    expect(foldOf(foldActivityUnits(buildConversationUnits(rows))[1]).openTail).toBe(true)

    const sendAt = Date.parse("2026-10-24T08:00:00Z")
    const visibleAt = sendAt + 35_000
    const sealedRows = closeWorkSegment(rows, new Set(["row-r1"]), visibleAt)
    const sealed = foldOf(foldActivityUnits(buildConversationUnits(sealedRows))[1])
    expect(sealed.openTail).toBe(false)
    expect(sealed.startedAtMs).toBe(sendAt)
    expect(sealed.endedAtMs).toBe(visibleAt)
    expect(sealed.elapsedMs).toBe(35_000)
    expect(sealed.rows.map((r) => r.duration_ms)).toEqual([1000, 2000])

    // The first actual character later flips the boundary without moving or
    // re-opening the sealed fold, and a second seal cannot move its clock.
    const visible = sealedRows.map((m) =>
      m.id === "reply" ? { ...m, content: "Reply" } : m,
    )
    const after = foldOf(foldActivityUnits(buildConversationUnits(visible))[1])
    expect(after.openTail).toBe(false)
    expect(after.elapsedMs).toBe(sealed.elapsedMs)
    const resealed = closeWorkSegment(visible, new Set(["row-r1"]), 90_000)
    expect(resealed.find((m) => m.id === "row-r1")?.workEndedAtMs).toBe(visibleAt)
  })

  it("first-visible seals only the segment BEFORE that prose row, never a later activity segment", () => {
    const rows: OverlayMessage[] = [
      read("before", { at: "2026-10-24T08:00:01Z" }),
      {
        id: "interim_prose",
        role: "assistant",
        content: "",
        streaming: true,
      },
      read("after", { at: "2026-10-24T08:00:02Z" }),
    ]
    const keys = new Set(["row-before", "row-after"])
    const sealed = closeWorkSegment(rows, keys, 35_000, undefined, "interim_prose")
    expect(sealed[0].workEndedAtMs).toBe(35_000)
    expect(sealed[2].workEndedAtMs).toBeUndefined()

    const withReply: OverlayMessage[] = [
      ...sealed,
      { id: "reply", role: "assistant", content: "", streaming: true },
    ]
    const finished = closeWorkSegment(withReply, keys, 40_000, undefined, "reply")
    expect(finished[0].workEndedAtMs).toBe(35_000)
    expect(finished[2].workEndedAtMs).toBe(40_000)
  })

  it("a terminal error row is not following prose and cannot steal the terminal seal", () => {
    const rows: OverlayMessage[] = [
      msg("user", "2026-10-24T08:00:00Z"),
      read("r1", { at: "2026-10-24T08:00:01Z" }),
      {
        id: "turn-error",
        role: "assistant",
        content: "The turn failed",
        meta: "error",
      },
    ]
    const sealed = closeWorkSegment(rows, new Set(["row-r1"]), 50_000)
    expect(sealed[1].workEndedAtMs).toBe(50_000)
    const fold = foldOf(foldActivityUnits(buildConversationUnits(sealed))[1])
    expect(fold.openTail).toBe(false)
    expect(fold.endedAtMs).toBe(50_000)
  })

  it("the next segment starts when the previous prose DRAINED, excluding its playback", () => {
    const rows: OverlayMessage[] = [
      {
        ...assistantMsg("interim_prose"),
        proseDrainedAtMs: 20_000,
      },
      read("r1", { at: "1970-01-01T00:00:15Z", duration_ms: 3000 }),
    ]
    const sealed = closeWorkSegment(rows, new Set(["row-r1"]), 30_000, 1_000)
    const fold = foldOf(foldActivityUnits(buildConversationUnits(sealed))[1])
    // Even an explicit turn-start gesture cannot reach back across prose.
    expect(fold.startedAtMs).toBe(20_000)
    expect(fold.elapsedMs).toBe(10_000)
  })

  it("Start's real click supplies the work boundary when no user / QA row exists", () => {
    const rows = [
      read("r1", { at: "1970-01-01T00:00:10Z", duration_ms: 2000 }),
    ]
    const sealed = closeWorkSegment(rows, new Set(["row-r1"]), 35_000, 5_000)
    const fold = foldOf(foldActivityUnits(buildConversationUnits(sealed))[0])
    expect(fold.startedAtMs).toBe(5_000)
    expect(fold.elapsedMs).toBe(30_000)
    expect(sealed[0].workStartedAtMs).toBe(5_000)
  })

  it("host-row keys, never a repeated per-turn activity_id, decide which segment seals", () => {
    const hosted = (hostId: string): OverlayMessage => ({
      ...activityMsg("a1"),
      id: hostId,
    })
    const rows = [hosted("turn-1-row"), assistantMsg("middle"), hosted("turn-2-row")]
    const sealed = closeWorkSegment(rows, new Set(["turn-2-row"]), 50_000)
    expect(sealed[0].workEndedAtMs).toBeUndefined()
    expect(sealed[2].workEndedAtMs).toBe(50_000)
    // A new turn's empty current set cannot touch the old orphan either.
    expect(closeWorkSegment(rows, new Set(), 80_000)).toBe(rows)
  })

  it("a failed fragment is already settled; only the later current fragment receives the live seal", () => {
    const rows = [
      read("ok1"),
      read("bad", { status: "failed" }),
      read("ok2"),
    ]
    const before = foldActivityUnits(buildConversationUnits(rows))
    expect(foldOf(before[0]).openTail).toBe(false)
    expect(foldOf(before[0]).failure?.activity_id).toBe("bad")
    expect(foldOf(before[1]).openTail).toBe(true)
    const sealedRows = closeWorkSegment(rows, new Set(["row-ok2"]), 60_000)
    expect(sealedRows[0].workEndedAtMs).toBeUndefined()
    expect(sealedRows[2].workEndedAtMs).toBe(60_000)
  })
})

describe("rowKey — the cross-turn render identity (行身份律)", () => {
  /** Two turns both number their first activity "a1" (per-turn scoping) —
   * the host row id is the only stable identity. */
  const hosted = (
    hostId: string,
    activityId: string,
    over: Partial<ActivityRowFrame> = {},
  ): OverlayMessage => ({
    id: hostId,
    role: "assistant",
    content: "",
    activity: {
      activity_id: activityId,
      kind: "read",
      status: "completed",
      key: "chat.inspectingDone.transcript",
      ...over,
    },
  })

  const unitRowKey = (u: ConversationUnit): string => {
    if (u.kind === "message") return u.message.id
    return u.rowKey
  }

  it("two turns' a1 groups separated by a message BOTH survive with non-colliding keys", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        hosted("t1-a1", "a1"),
        hosted("t1-a2", "a2"),
        assistantMsg("mid"),
        hosted("t2-a1", "a1"),
        hosted("t2-a4", "a4"),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:a1+a2", "mid", "fold:a1+a4"])
    // Both folds render — and their React keys come from the host rows,
    // never from the per-turn activity_id (fold-a1 twice = the collision).
    expect(units.map(unitRowKey)).toEqual(["t1-a1", "mid", "t2-a1"])
    expect(new Set(units.map(unitRowKey)).size).toBe(units.length)
  })

  it("failed pass-through rows with the same per-turn id keep distinct keys", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        hosted("t1-bad", "a1", { status: "failed" }),
        assistantMsg("mid"),
        hosted("t2-bad", "a1", { status: "failed" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["a1", "mid", "a1"])
    expect(units.map(unitRowKey)).toEqual(["t1-bad", "mid", "t2-bad"])
  })

  it("a segment gaining a settling member keeps the fold's identity (the head row never changes)", () => {
    const before = foldActivityUnits(
      buildConversationUnits([
        hosted("row-a1", "a1", { duration_ms: 400 }),
        hosted("row-a2", "a2", { status: "active" }), // live member of the same segment
      ]),
    )
    expect(foldOf(before[0]).rows.map((r) => r.activity_id)).toEqual(["a1"])
    // The a2 row settles IN PLACE (same host id, merged frame) and joins.
    const after = foldActivityUnits(
      buildConversationUnits([
        hosted("row-a1", "a1", { duration_ms: 400 }),
        hosted("row-a2", "a2", { duration_ms: 600 }),
      ]),
    )
    expect(foldOf(after[0]).rows.map((r) => r.activity_id)).toEqual(["a1", "a2"])
    expect(unitRowKey(after[0])).toBe(unitRowKey(before[0]))
  })

  it("a interim_prose-promoted host keys by birthKey (the OverlayMessage render-key law)", () => {
    const row = { ...hosted("promoted#ip1", "a1"), birthKey: "promoted" }
    const units = foldActivityUnits(buildConversationUnits([row]))
    expect(unitRowKey(units[0])).toBe("promoted")
  })
})

describe("activityFailureKey — failure is terminal copy, never an abandoned active label", () => {
  it("keeps explicit failure mirrors and falls every active-only key back to honest failure copy", () => {
    expect(activityFailureKey("chat.inspectingFailed.understanding")).toBe(
      "chat.inspectingFailed.understanding",
    )
    expect(activityFailureKey("chat.activity.repair")).toBe("chat.activity.repair")
    expect(activityFailureKey("chat.activity.storyboardEdit")).toBe("chat.failed")
    expect(activityFailureKey("chat.inspecting.outputSpec")).toBe("chat.failed")
    expect(activityFailureKey(null)).toBe("chat.failed")
  })
})

describe("activityCategoryKey — the settled surface's category form (归档归类目)", () => {
  it("the material reading family remaps to the name-free materialCategory keys", () => {
    expect(activityCategoryKey("chat.material.readingDone")).toBe(
      "chat.materialCategory.reading",
    )
    expect(activityCategoryKey("chat.material.readingDoneProgress")).toBe(
      "chat.materialCategory.reading",
    )
    expect(activityCategoryKey("chat.material.readingDone_video")).toBe(
      "chat.materialCategory.reading_video",
    )
    expect(activityCategoryKey("chat.material.readingDoneProgress_audio")).toBe(
      "chat.materialCategory.reading_audio",
    )
  })

  it("web_page beats fork off the beat's asset_type (their row key falls to the base form)", () => {
    expect(activityCategoryKey("chat.material.readingDoneProgress", "web_page")).toBe(
      "chat.materialCategory.reading_webPage",
    )
    expect(activityCategoryKey("chat.material.readingDone", "web_page")).toBe(
      "chat.materialCategory.reading_webPage",
    )
    // The key's own typed suffix wins over a missing/blank asset type.
    expect(activityCategoryKey("chat.material.readingDone_video", undefined)).toBe(
      "chat.materialCategory.reading_video",
    )
  })

  it("every other family is already category-shaped — the key passes through untouched", () => {
    expect(activityCategoryKey("chat.inspectingDone.webPage")).toBe(
      "chat.inspectingDone.webPage",
    )
    expect(activityCategoryKey("chat.explore.candidatesReady")).toBe(
      "chat.explore.candidatesReady",
    )
    expect(activityCategoryKey("chat.material.understandingDone")).toBe(
      "chat.material.understandingDone",
    )
    expect(activityCategoryKey(null)).toBeNull()
  })
})

describe("buildConversationBlocks — explicit turn ownership, stable block identity", () => {
  it("folds interim prose between tools and keeps the final reply in its opening", () => {
    const rows = [
      { ...msg("u1"), turnId: "t1" },
      { ...assistantMsg("opening"), turnId: "t1" },
      { ...activityMsg("a1"), turnId: "t1" },
      { ...assistantMsg("middle"), turnId: "t1" },
      { ...activityMsg("a2"), turnId: "t1" },
      { ...assistantMsg("final"), turnId: "t1" },
      { ...msg("u2"), turnId: "t2" },
      { ...assistantMsg("next"), turnId: "t2" },
    ]
    const blocks = buildConversationBlocks(
      foldActivityUnits(buildConversationUnits(rows)),
    )
    expect(blocks.map((block) => block.kind)).toEqual(["turn", "turn"])
    expect(blocks[0].key).toBe("turn:u1")
    expect(blockUnits(blocks[0]).map(unitId)).toEqual([
      "u1",
      "opening",
      "fold:a1+a2",
      "final",
    ])
    expect(blockUnits(blocks[0])[2]).toMatchObject({ trail: [
      { kind: "activity", rowKey: "row-a1" }, { kind: "note", text: "middle" },
      { kind: "activity", rowKey: "row-a2" },
    ] })
    expect(blockUnits(blocks[1]).map(unitId)).toEqual(["u2", "next"])
  })

  it("legacy rows stay independent and never borrow a neighbouring turn", () => {
    const blocks = buildConversationBlocks(
      foldActivityUnits(buildConversationUnits([
        assistantMsg("old-before"),
        { ...msg("new-user"), turnId: "new-turn" },
        { ...assistantMsg("new-reply"), turnId: "new-turn" },
        assistantMsg("old-after"),
      ])),
    )
    expect(blocks.map((block) => block.kind)).toEqual([
      "standalone",
      "turn",
      "standalone",
    ])
    expect(blockUnits(blocks[0]).map(unitId)).toEqual(["old-before"])
    expect(blockUnits(blocks[2]).map(unitId)).toEqual(["old-after"])
  })

  it("interleaved independent facts keep their type and never cause non-contiguous regrouping", () => {
    const blocks = buildConversationBlocks(
      foldActivityUnits(buildConversationUnits([
        { ...msg("u1"), turnId: "t1" },
        {
          ...assistantMsg("trigger"),
          independentKind: "trigger" as const,
        },
        { ...assistantMsg("after"), turnId: "t1" },
      ])),
    )
    expect(blocks.map((block) => block.kind)).toEqual([
      "turn",
      "standalone",
      "turn",
    ])
    expect(blocks.flatMap((block) => blockUnits(block).map(unitId))).toEqual([
      "u1",
      "trigger",
      "after",
    ])
    expect(blocks[0].key).not.toBe(blocks[2].key)
  })

  it("activity folds stop at an explicit turn boundary", () => {
    const units = foldActivityUnits(buildConversationUnits([
      { ...activityMsg("a1"), turnId: "t1" },
      { ...activityMsg("a2"), turnId: "t2" },
    ]))
    expect(units.map(unitId)).toEqual(["fold:a1", "fold:a2"])
  })

  it("cross-turn delivery and independent upload keep their own response and refs", () => {
    const rows = [
      { ...assistantMsg("first"), runId: "run-1", runDelivery: true, turnId: "delivery-1", outputRefs: ["video-1"] },
      { ...msg("user"), turnId: "retry-turn" },
      { ...assistantMsg("upload"), turnId: "retry-turn", outputRefs: ["video-2"] },
      { ...assistantMsg("later"), runId: "run-1", runDelivery: true, turnId: "delivery-2", outputRefs: ["video-3"] },
    ]
    const blocks = buildConversationBlocks(buildConversationUnits(rows))
    expect(blocks.map((block) => block.kind)).toEqual(["turn", "turn", "turn"])
    expect(blocks[0]).toMatchObject({ slots: [{ kind: "message", message: { id: "first", outputRefs: ["video-1"] } }] })
    expect(blocks[1]).toMatchObject({ user: { id: "user" }, slots: [{ kind: "message", message: { id: "upload", outputRefs: ["video-2"] } }] })
    expect(blocks[2]).toMatchObject({ slots: [{ kind: "message", message: { id: "later", outputRefs: ["video-3"] } }] })
    expect(blocks.flatMap(blockUnits).map(unitId)).toEqual(["first", "user", "upload", "later"])
  })

  const linkedOptionRows = (extra: Partial<OverlayMessage> = {}): OverlayMessage[] => [
    {
      ...assistantMsg("q1"),
      content: "",
      independentKind: "qa",
      qa: {
        question: "Which language?",
        answer: "English",
        muted: false,
        questionId: "q1",
        answerKind: "option",
      },
    },
    {
      ...msg("u1"),
      ...extra,
      content: "English",
      turnId: "u1",
      answeredQuestionId: "q1",
    },
    { ...assistantMsg("reply"), turnId: "u1" },
  ]

  it("suppresses a linked pure-option user bubble only after grouping its real Turn", () => {
    const rows = linkedOptionRows()
    const blocks = buildConversationBlocks(buildConversationUnits(rows))
    expect(blocks.map((block) => block.kind)).toEqual(["standalone", "turn"])
    expect(blockUnits(blocks[0]).map(unitId)).toEqual(["q1"])
    expect(blocks[1]).toMatchObject({ key: "turn:u1", turnId: "u1" })
    expect(blockUnits(blocks[1]).map(unitId)).toEqual(["reply"])
    // Suppression is only a visible-Slot projection; the durable user row remains.
    expect(rows[1]).toMatchObject({ id: "u1", turnId: "u1", answeredQuestionId: "q1" })
  })

  it("keeps an option answer's complete user bubble when it carries attachments", () => {
    const rows = linkedOptionRows({
      assets: [{
        id: "asset-1",
        type: "video",
        file_url: "talk.mp4",
        title: "talk.mp4",
        processing_status: "completed",
      }],
    })
    const blocks = buildConversationBlocks(buildConversationUnits(rows))
    expect(blockUnits(blocks[1]).map(unitId)).toEqual(["u1", "reply"])
    expect(rows[1].assets?.map((asset) => asset.id)).toEqual(["asset-1"])
  })

  it("keeps an option answer's complete user bubble when it carries focus", () => {
    const rows = linkedOptionRows({
      focus: { id: "output-1", label: "Exact output" },
    })
    const blocks = buildConversationBlocks(buildConversationUnits(rows))
    expect(blockUnits(blocks[1]).map(unitId)).toEqual(["u1", "reply"])
    expect(rows[1].focus).toEqual({ id: "output-1", label: "Exact output" })
  })

  it("keeps an associated user bubble until its option QA exists in the same projection", () => {
    const rows: OverlayMessage[] = [
      {
        ...msg("u1"),
        content: "English",
        turnId: "u1",
        answeredQuestionId: "q1",
      },
      { ...assistantMsg("reply"), turnId: "u1" },
    ]
    const [block] = buildConversationBlocks(buildConversationUnits(rows))
    expect(blockUnits(block).map(unitId)).toEqual(["u1", "reply"])
  })

  it("block keys use the first row's birth identity, not a reconciled turn id", () => {
    const row = {
      ...msg("server-user"),
      birthKey: "optimistic-user",
      turnId: "server-turn",
    }
    const [block] = buildConversationBlocks(buildConversationUnits([row]))
    expect(block.key).toBe("turn:optimistic-user")
  })
})


it("a failed upload never settles an adjacent different turn's Worked", () => {
  const previous = { ...activityMsg("previous"), turnId: "old-turn" }
  const failed = { ...activityMsg("upload", {
    status: "failed", key: "chat.activity.upload",
  }), turnId: "upload-turn" }
  const units = foldActivityUnits(buildConversationUnits([previous, failed]))
  expect(units).toHaveLength(2)
  expect(units[0]).toMatchObject({ kind: "activityFold", turnId: "old-turn", failure: null })
  expect(units[1]).toMatchObject({ kind: "activity", turnId: "upload-turn", activity: { status: "failed" } })
})

it("keeps every native group member when Stop or an approval interrupts a batch", () => {
  const rows = [
    activityMsg("one", { group_id: "read", call_index: 0, tool_name: "inspect_clip" }),
    activityMsg("two", { group_id: "read", call_index: 1, tool_name: "inspect_clip", status: "failed" }),
    activityMsg("three", { group_id: "media", call_state: "awaiting_authorization", status: "cancelled" }),
    activityMsg("four", { group_id: "media", call_state: "not_executed", status: "cancelled" }),
  ]
  const units = foldActivityUnits(buildConversationUnits(rows))
  expect(units.map(unitId)).toEqual(["fold:one+two+three+four"])
})

describe("turn work trails", () => {
  const turn = (m: OverlayMessage) => ({ ...m, turnId: "opening" })
  const activity = (id: string, frame: Partial<ActivityRowFrame> = {}) =>
    turn(activityMsg(id, frame))
  const speech = (id: string) => turn(assistantMsg(id))

  it("merges single calls and separate batches, sorting only within each declaration", () => {
    const rows = [
      activity("single", { call_id: "s" }),
      activity("second", { group_id: "g1", call_index: 1 }),
      activity("first", { group_id: "g1", call_index: 0 }),
      speech("checking"),
      activity("third", { group_id: "g2", call_index: 0 }),
      speech("reply"),
    ]
    const project = (messages: OverlayMessage[]) => foldActivityUnits(buildConversationUnits(messages))
    const live = project(rows)
    expect(live).toHaveLength(2)
    expect(live[0]).toMatchObject({ rowKey: "row-single", trail: [
      { rowKey: "row-single" }, { rowKey: "row-first" }, { rowKey: "row-second" },
      { kind: "note", text: "checking" }, { rowKey: "row-third" },
    ] })
    const replay = mapHistoryRows(rows.map((m, seq) => ({
      id: m.id, seq, role: m.role, content: m.content, turn_id: m.turnId, question: null, answer: null,
      intent: m.activity ? { type: "activity", frame: m.activity } : undefined,
    })), { t: key => key })
    expect(project(replay)[0]).toEqual(live[0])
    expect(project(replay).map(unitId)).toEqual(live.map(unitId))
  })

  it.each([
    { qa: { question: "Proceed?", answer: "Yes", muted: false }, independentKind: "qa" as const },
    { outputRefs: ["fixed-output"] },
    { blocks: [{ kind: "audio_playback" as const, project_id: "p", items: [] }] },
  ])("preserves the entity at its position and starts a new trail below it", entity => {
    const boundary = { ...speech("decision"), ...entity }
    const rows = [activity("before"), boundary, activity("after"), speech("reply")]
    const units = foldActivityUnits(buildConversationUnits(rows))
    expect(units.map(unitId)).toEqual(["fold:before", "decision", "fold:after", "reply"])
    expect(units[1]).toMatchObject({ message: entity })
  })

  it("keeps the last released prose outside on Stop, even if more work followed it", () => {
    const units = buildConversationUnits([
      activity("first"), speech("earlier"), activity("second"), speech("latest"), activity("third"),
    ])
    const live = foldActivityUnits(units, undefined, "opening")
    expect(live).toHaveLength(1)
    expect(live[0]).toMatchObject({ openTail: true, trail: [
      {}, { kind: "note", text: "earlier" }, {}, { kind: "note", text: "latest" }, {},
    ] })
    const stopped = foldActivityUnits(units)
    expect(stopped.map(unitId)).toEqual(["fold:first+second+third", "latest"])
    expect(stopped[0]).toMatchObject({ trail: [{}, { kind: "note", text: "earlier" }, {}, {}] })
  })

  it("freezes the combined span at the final reply, even after an earlier interim seal", () => {
    const keys = new Set(["row-a", "row-b"])
    const initial = [turn(msg("opening", "1970-01-01T00:00:01Z")), activity("a")]
    const first = closeWorkSegment([...initial, { ...speech("interim"), content: "" }], keys, 4000, undefined, "interim")
    const rows = [first[0], first[1], speech("interim"), activity("b")]
    const current = foldActivityUnits(buildConversationUnits(rows), undefined, "opening")
    expect(current[1]).toMatchObject({ startedAtMs: 1000, endedAtMs: null, openTail: true })
    const sealed = closeWorkSegment([...rows, { ...speech("reply"), content: "" }], keys, 17000, undefined, "reply")
    const final = [...sealed.slice(0, -1), speech("reply")]
    expect(foldActivityUnits(buildConversationUnits(final))[1]).toMatchObject({
      startedAtMs: 1000, endedAtMs: 17000, elapsedMs: 16000, openTail: false,
    })
    expect(closeWorkSegment(final, keys, 25000)).toBe(final)
  })

  it("keeps a worker receipt after authorization and uses overlapping wall time on replay", () => {
    const rows = [
      activity("long", { call_id: "export", group_id: "g", at: "1970-01-01T00:00:01Z", duration_ms: 9000 }),
      activity("short", { group_id: "g", at: "1970-01-01T00:00:02Z", duration_ms: 200 }),
      { ...speech("approve"), qa: { question: "Export?", answer: "Yes", muted: false } },
      { ...speech("worker"), content: "", jobReceipt: { callId: "export", role: "export", status: "available",
        chargedCredits: 3, outputId: "fixed-output" } },
    ]
    const units = foldActivityUnits(buildConversationUnits(rows))
    expect(units.map(unitId)).toEqual(["fold:long+short", "approve", "fold:export"])
    expect(foldOf(units[0]).elapsedMs).toBe(9000)
    expect(foldOf(units[0]).rows[0].jobReceipt).toBeUndefined()
    expect(foldOf(units[2]).rows[0].jobReceipt).toMatchObject({ chargedCredits: 3, outputId: "fixed-output" })
  })
})

it("preserves an output and its independently mounted block when its activity retires", () => {
  const row = { ...activityMsg("abandoned", { status: "cancelled" }), turnId: "turn",
    outputRefs: ["fixed"], blocks: [{ kind: "system_notice" as const, text: "Output available" }] }
  expect(foldActivityUnits(buildConversationUnits([row]))).toMatchObject([{
    kind: "message", message: { id: row.id, outputRefs: ["fixed"], blocks: row.blocks },
  }])
})
