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
  buildConversationUnits,
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

  it("a lone settled row passes through as its OWN row (单行段不包折叠壳)", () => {
    const units = foldActivityUnits(
      buildConversationUnits([msg("user"), read("r1"), assistantMsg("reply")]),
    )
    expect(units.map(unitId)).toEqual(["user", "r1", "reply"])
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

  it("failed/cancelled rows never fold — they stay visible and break the run", () => {
    const units = foldActivityUnits(
      buildConversationUnits([
        read("ok1", { key: "chat.inspectingDone.transcript" }),
        read("bad", { key: "chat.inspecting.transcript", status: "failed" }),
        read("ok2", { key: "chat.inspectingDone.transcript" }),
        read("ok3", { key: "chat.inspectingDone.transcript" }),
      ]),
    )
    // The broken segments each pass through / fold on their own sides of
    // the failed row (ok1 is a lone row → passthrough; ok2+ok3 fold).
    expect(units.map(unitId)).toEqual(["ok1", "bad", "fold:ok2+ok3"])
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

  it("no boundary and no stamps → the summed durations; nothing measurable → null", () => {
    const withDurations = foldActivityUnits(
      buildConversationUnits([
        read("r1", { duration_ms: 400 }),
        read("r2", { duration_ms: 600 }),
      ]),
    )
    expect(foldOf(withDurations[0]).elapsedMs).toBe(1000)
    const bare = foldActivityUnits(
      buildConversationUnits([read("r1"), read("r2")]),
    )
    expect(foldOf(bare[0]).elapsedMs).toBeNull()
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
