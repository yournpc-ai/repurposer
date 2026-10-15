/** The conversation timeline layer (ADR-108 数组位置律): the persisted
 * array's order IS the render order — this module MAPS rows to units and
 * never re-sorts (no timestamps, no walk keys, no anchors). Pure, no React
 * (the vitest seam); ChatDock composes the units, this module owns the
 * SHAPE (message vs activity vs fold) and the folding projection. */

import type { ActivityRowFrame, OverlayMessage } from "@/components/chat/historyReplay"

/** One unit of the conversation timeline: a message or one activity row. */
export type ConversationUnit =
  | { kind: "message"; message: OverlayMessage }
  | { kind: "activity"; activity: ActivityRowFrame }
  | { kind: "activityFold"; rows: ActivityRowFrame[]; elapsedMs: number | null }

/** The draft span never enters the flow (2026-09-28 user ruling —
 * 落定即退役): the docked plan card IS the settled evidence. The server
 * never persists draft/run spans (activity.py's frame_persistence), so this
 * filter is the defensive twin for legacy/migrated rows. */
export function isDraftSpanRow(a: ActivityRowFrame): boolean {
  return a.kind === "draft" && (a.key ?? "").startsWith("chat.activity.")
}

/** The run span's settle (「已开工」) is the same hollow shape (落定即退役
 * 同律): the start speech and the RunTaskList receipt are the evidence. */
export function isRunSpanRow(a: ActivityRowFrame): boolean {
  return a.kind === "run" && (a.key ?? "").startsWith("chat.activity.")
}

/** Array map (ADR-108): each message row maps to ONE unit in place —
 * activity-carrying rows become activity units at their array position.
 * An ACTIVE activity never renders in the walk (the now-line owns it —
 * 合一律); draft/run span rows stay retired. */
export function buildConversationUnits(
  messages: OverlayMessage[],
): ConversationUnit[] {
  const units: ConversationUnit[] = []
  for (const m of messages) {
    const a = m.activity
    if (a === undefined) {
      units.push({ kind: "message", message: m })
      continue
    }
    if (a.status === "active") continue // the now-line owns the live row
    if (isDraftSpanRow(a) || isRunSpanRow(a)) continue // 落定即退役
    units.push({ kind: "activity", activity: a })
  }
  return units
}

/** 折叠投影 (呈现层纯函数, ADR-110 段聚合——Claude Code 式坍缩 +
 * Flora 解剖): 两条消息之间 2+ 条连续 COMPLETED 落定活动行折成一条
 * 聚合行「工作了 2m 7s」——折叠态只说总耗时这一个事实(分解一击可达,
 * 永不带 fragment 摘要)。单行段不包折叠壳:一条「已读网页 · 48s」直接
 * 说,不套「工作了 5s」的壳。failed/cancelled rows never fold: they
 * pass through as their own rows (the ✗ strike-through is the failure
 * signal) and break the run. Active rows are hard boundaries too
 * (进行态不折叠 — the now-line owns them; they never reach the walk
 * anyway). The fold never crosses a message boundary. Display-only: the
 * folded rows keep their identities for the expanded view; the persisted
 * array is untouched. */
export function foldActivityUnits(units: ConversationUnit[]): ConversationUnit[] {
  const out: ConversationUnit[] = []
  let run: ActivityRowFrame[] = []
  const flush = (boundaryAt?: string) => {
    if (run.length === 1) {
      out.push({ kind: "activity", activity: run[0] })
    } else if (run.length > 0) {
      out.push({
        kind: "activityFold",
        rows: run,
        elapsedMs: foldElapsedMs(run, boundaryAt),
      })
    }
    run = []
  }
  for (const unit of units) {
    if (unit.kind === "activity" && unit.activity.status === "completed") {
      run.push(unit.activity)
      continue
    }
    // The segment's wall clock ends at the NEXT row — the turn's prose
    // (an assistant message) or a neighbouring non-completed activity.
    // A USER message is no honest segment end: after a failed turn the
    // user may return hours later, and their message's stamp would
    // fabricate a multi-hour "工作了 3 小时" lie. A run-carrying
    // assistant message is no honest end either (ADR-110 修订): when a
    // run intervenes between the segment and its boundary (material beats,
    // then the delivery prose at run completion), the prose's stamp would
    // stretch the fold's clock over the whole run — duplicating the
    // receipt row's own total. The run's span belongs to the receipt; the
    // fold falls back to the last row's own end.
    const boundaryAt =
      unit.kind === "message"
        ? unit.message.role === "assistant" && !unit.message.runId
          ? unit.message.at
          : undefined
        : unit.kind === "activity"
          ? unit.activity.at
          : unit.rows[0]?.at
    flush(boundaryAt)
    out.push(unit)
  }
  flush()
  return out
}

/** The aggregate row's total elapsed (段墙钟, ADR-110): first row's birth
 * → the segment's end — the following assistant row's stamp when there is
 * one (the prose's arrival closes the work segment — the CC "Thought for
 * Xs" anatomy), else the last row's own end (live tail: the prose hasn't
 * arrived yet). Falls back to the summed row durations; null when nothing
 * measurable exists. */
function foldElapsedMs(
  rows: ActivityRowFrame[],
  boundaryAt?: string,
): number | null {
  const start = Date.parse(rows[0]?.at ?? "")
  if (!Number.isNaN(start)) {
    if (boundaryAt) {
      const end = Date.parse(boundaryAt)
      if (!Number.isNaN(end) && end > start) return end - start
    }
    const last = rows[rows.length - 1]
    const lastAt = Date.parse(last?.at ?? "")
    if (!Number.isNaN(lastAt)) {
      const lastEnd = lastAt + (last.duration_ms ?? 0)
      if (lastEnd > start) return lastEnd - start
    }
  }
  let sum = 0
  let any = false
  for (const r of rows) {
    if (r.duration_ms != null) {
      sum += r.duration_ms
      any = true
    }
  }
  return any ? sum : null
}

/** The fold's expanded category rows (ADR-110 修订 — 归档归类目):
 * rows sharing one copy key AND asset type merge across the WHOLE segment
 * into ONE ×N category line (the Flora anatomy — 已读网页 ×3), order =
 * first appearance. Instance names are the live phase's speech; the
 * archive speaks categories. A milestone row whose count IS its content
 * (the explore family's artifact counts — count without total) never
 * merges: two rows can't speak one honest count, so each rides as its own
 * entry. Progress beats (count+total = the N/M reading progress) merge
 * and drop the numbering — a settled row has no progress to report. */
export interface FoldCategory {
  kind: ActivityRowFrame["kind"]
  key: string | null
  /** Merge identity member: same key but different asset types are
   * different categories (web_page beats share the base reading key with
   * file beats — the verb fork predates the type). */
  assetType?: string
  repeat: number
  /** A milestone row's own artifact count (merged categories: undefined). */
  count?: number
}

/** The aggregate row's expanded categories (ADR-110 修订). */
export function foldCategories(rows: ActivityRowFrame[]): FoldCategory[] {
  const cats: FoldCategory[] = []
  for (const r of rows) {
    const mergeable = r.count == null || r.total != null
    const hit = mergeable
      ? cats.find(
          (c) =>
            c.key === r.key &&
            c.assetType === r.assetType &&
            c.count === undefined,
        )
      : undefined
    if (hit) {
      hit.repeat += 1
      continue
    }
    cats.push({
      kind: r.kind,
      key: r.key,
      assetType: r.assetType,
      repeat: 1,
      count: mergeable ? undefined : (r.count ?? undefined),
    })
  }
  return cats
}

/** The settled surface's category-form key (归档归类目 — 实例名归 live
 * 期): the material reading family's keys interpolate the file's name
 * (`读完 {{name}}`) — the name is the live phase's speech. Settled rows
 * drop the instance name and speak the category, remapping to the
 * name-free `chat.materialCategory` family. The verb fork follows the
 * key's own _video/_audio suffix; web_page rides the beat's asset_type
 * (its row key falls to the base form — the fork predates the web_page
 * type). Every other family is already category-shaped (inspectingDone /
 * explore interpolate no name). */
export function activityCategoryKey(
  key: string | null,
  assetType?: string | null,
): string | null {
  if (key == null) return null
  const m = /^chat\.material\.readingDone(?:Progress)?(_video|_audio)?$/.exec(key)
  if (!m) return key
  const typed = m[1] ?? (assetType === "web_page" ? "_webPage" : "")
  return `chat.materialCategory.reading${typed}`
}
