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

/** 折叠投影 (呈现层纯函数, ADR-110 段聚合 — the Claude Code collapse):
 * EVERY run of consecutive COMPLETED settled activity rows between two
 * messages collapses into ONE aggregate summary row (「工作了 1m 32s ·
 * 已理解素材 · 找到 12 段候选」) — cross-key, single-row segments included
 * (全收). failed/cancelled rows never fold: they pass through as their own
 * rows (the ✗ strike-through is the failure signal) and break the run.
 * Active rows are hard boundaries too (进行态不折叠 — the now-line owns
 * them; they never reach the walk anyway). The fold never crosses a
 * message boundary. Display-only: the folded rows keep their identities
 * for the expanded view; the persisted array is untouched. */
export function foldActivityUnits(units: ConversationUnit[]): ConversationUnit[] {
  const out: ConversationUnit[] = []
  let run: ActivityRowFrame[] = []
  const flush = (boundaryAt?: string) => {
    if (run.length > 0) {
      out.push({
        kind: "activityFold",
        rows: run,
        elapsedMs: foldElapsedMs(run, boundaryAt),
      })
      run = []
    }
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
    // fabricate a multi-hour "工作了 3 小时" lie.
    const boundaryAt =
      unit.kind === "message"
        ? unit.message.role === "assistant"
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

/** One aggregate fragment: CONSECUTIVE rows sharing one fold identity
 * (key + named object) merge into a ×N repeat; a lone row speaks with its
 * own interpolation (the milestone's artifact count / the beat's
 * filename). Order = first appearance — chronology is the truth. */
export interface FoldFragment {
  key: string | null
  repeat: number
  /** The lone row's own artifact count (dropped on merge — two merged
   * rows can't speak one honest count). */
  count?: number
  name?: string
  total?: number
}

/** The aggregate row's ordered fragments (ADR-110). */
export function foldSummary(rows: ActivityRowFrame[]): FoldFragment[] {
  const fragments: FoldFragment[] = []
  for (const r of rows) {
    const last = fragments[fragments.length - 1]
    if (last && last.key === r.key && last.name === r.name) {
      last.repeat += 1
      last.count = undefined
      continue
    }
    fragments.push({
      key: r.key,
      repeat: 1,
      count: r.count ?? undefined,
      name: r.name,
      total: r.total,
    })
  }
  return fragments
}
