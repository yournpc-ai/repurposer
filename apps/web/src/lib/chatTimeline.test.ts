/** The conversation timeline layer's contract (ADR-108 数组位置律): the
 * persisted array's order IS the render order — buildConversationUnits MAPS
 * rows to units in place and never re-sorts; foldActivityUnits is the
 * display-layer folding projection (呈现层纯函数, ADR-110 段聚合), and
 * foldCategories / activityCategoryKey are the aggregate's expanded
 * decomposition (归档归类目 — settled surfaces speak categories, instance
 * names belong to the live phase). */

import { describe, expect, it } from "vitest"

import {
  activityCategoryKey,
  activityFailureKey,
  buildConversationUnits,
  closeWorkSegment,
  foldActivityUnits,
  foldCategories,
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

  it("an ACTIVE activity enters the walk at its host position and owns the live segment", () => {
    const rows = [
      {
        ...assistantMsg("checkpoint"),
        streaming: true,
      },
      activityMsg("live", {
        status: "active",
        at: "2026-10-24T08:00:01Z",
      }),
    ]
    const units = foldActivityUnits(buildConversationUnits(rows))
    expect(units.map(unitId)).toEqual(["checkpoint", "fold:"])
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
    expect(foldCategories(foldOf(units[1]).rows)).toEqual([
      { kind: "read", key: "chat.inspectingDone.understanding", repeat: 1, count: undefined },
      { kind: "read", key: "chat.explore.searchingDone", repeat: 1, count: undefined },
      { kind: "read", key: "chat.explore.candidatesReady", repeat: 1, count: 12 },
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

  it("same-key rows merge into ONE ×N category across the WHOLE segment — adjacency not required", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("r1", { duration_ms: 400 }),
        read("r2", { key: "chat.explore.searchingDone" }),
        read("r3", { duration_ms: 600 }),
        assistantMsg("reply"),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:r1+r2+r3", "reply"])
    expect(foldCategories(foldOf(units[0]).rows)).toEqual([
      { kind: "read", key: "chat.inspectingDone.transcript", repeat: 2, count: undefined },
      { kind: "read", key: "chat.explore.searchingDone", repeat: 1, count: undefined },
    ])
  })

  it("beats merge into ONE category regardless of instance names (归档归类目 — 名字是 live 期的言语)", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        activityMsg("f1", { key: "chat.material.readingDone", name: "a.mp4" }),
        activityMsg("f2", { key: "chat.material.readingDone", name: "b.mp4" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:f1+f2"])
    expect(foldCategories(foldOf(units[0]).rows)).toEqual([
      { kind: "read", key: "chat.material.readingDone", repeat: 2, count: undefined },
    ])
  })

  it("progress beats merge and drop the N/M numbering; milestone counts stay individual (two rows can't speak one honest count)", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        activityMsg("p1", {
          key: "chat.material.readingDoneProgress",
          name: "www.zymix.ai/en/",
          count: 1,
          total: 3,
        }),
        activityMsg("p2", {
          key: "chat.material.readingDoneProgress",
          name: "www.zymix.ai/en/about",
          count: 3,
          total: 3,
        }),
        activityMsg("m1", { key: "chat.explore.candidatesReady", count: 12 }),
        activityMsg("m2", { key: "chat.explore.candidatesReady", count: 4 }),
      ]),
    )
    expect(foldCategories(foldOf(units[0]).rows)).toEqual([
      { kind: "read", key: "chat.material.readingDoneProgress", repeat: 2, count: undefined },
      { kind: "read", key: "chat.explore.candidatesReady", repeat: 1, count: 12 },
      { kind: "read", key: "chat.explore.candidatesReady", repeat: 1, count: 4 },
    ])
  })

  it("same key but different asset types stay separate categories (web_page beats share the base reading key with file beats)", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        activityMsg("f1", { key: "chat.material.readingDone", name: "a.pdf" }),
        activityMsg("w1", {
          key: "chat.material.readingDone",
          name: "www.zymix.ai/en/",
          assetType: "web_page",
        }),
        activityMsg("w2", {
          key: "chat.material.readingDone",
          name: "www.zymix.ai/en/about",
          assetType: "web_page",
        }),
      ]),
    )
    expect(foldCategories(foldOf(units[0]).rows)).toEqual([
      { kind: "read", key: "chat.material.readingDone", assetType: undefined, repeat: 1, count: undefined },
      { kind: "read", key: "chat.material.readingDone", assetType: "web_page", repeat: 2, count: undefined },
    ])
  })

  it("failed rows stay visible and break the run", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("ok1", { key: "chat.inspectingDone.transcript" }),
        read("bad", { key: "chat.inspecting.transcript", status: "failed" }),
        read("ok2", { key: "chat.inspectingDone.transcript" }),
        read("ok3", { key: "chat.inspectingDone.transcript" }),
      ]),
    )
    expect(units.map(unitId)).toEqual(["fold:ok1", "bad", "fold:ok2+ok3"])
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
      assistantMsg("checkpoint-1"),
      attempt("attempt-1", "cancelled"),
      assistantMsg("checkpoint-2"),
      attempt("attempt-2", "cancelled"),
      { ...assistantMsg("checkpoint-3"), streaming: true },
      attempt("attempt-3", "active"),
    ]
    const live = foldActivityUnits(buildConversationUnits(rows))
    expect(live.map(unitId)).toEqual([
      "checkpoint-1",
      "checkpoint-2",
      "checkpoint-3",
      "fold:",
    ])
    expect(live[3]).toMatchObject({ rowKey: "row-attempt-3", openTail: true })

    const accepted = rows.map((m) =>
      m.id === "row-attempt-3" ? attempt("attempt-3", "completed") : m,
    )
    const sealed = closeWorkSegment(accepted, new Set(["row-attempt-3"]), 35_000)
    const settled = foldActivityUnits(buildConversationUnits(sealed))
    expect(settled.map(unitId)).toEqual([
      "checkpoint-1",
      "checkpoint-2",
      "checkpoint-3",
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
          runId: "run-1",
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
        id: "checkpoint",
        role: "assistant",
        content: "",
        streaming: true,
      },
      read("after", { at: "2026-10-24T08:00:02Z" }),
    ]
    const keys = new Set(["row-before", "row-after"])
    const sealed = closeWorkSegment(rows, keys, 35_000, undefined, "checkpoint")
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
        ...assistantMsg("checkpoint"),
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

  it("failure-separated open fragments stay open; only the last current fragment receives the live seal", () => {
    const rows = [
      read("ok1"),
      read("bad", { status: "failed" }),
      read("ok2"),
    ]
    const before = foldActivityUnits(buildConversationUnits(rows))
    expect(foldOf(before[0]).openTail).toBe(true)
    expect(foldOf(before[2]).openTail).toBe(true)
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

  it("a checkpoint-promoted host keys by birthKey (the OverlayMessage render-key law)", () => {
    const row = { ...hosted("promoted#cp1", "a1"), birthKey: "promoted" }
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
