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
  | { kind: "activityFold"; rows: ActivityRowFrame[] }

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

/** The fold key: consecutive SETTLED activity rows fold only when the user
 * would read them as the same act repeated — same kind, same copy key, same
 * named object (a beat's filename). Reading two different files never folds
 * into one row. */
function foldKeyOf(a: ActivityRowFrame): string {
  return `${a.kind}${a.key ?? ""}${a.name ?? ""}`
}

/** 折叠投影 (呈现层纯函数, ADR-108 §6): a run of ≥2 consecutive settled
 * activity rows sharing one fold key collapses into ONE aggregate row
 * (「已检索转写 ×N · 共 Xs」, expandable to the明细). Active rows never
 * fold (the now-line owns them — they never reach the walk anyway), and a
 * fold never crosses a message boundary. The折叠 is display-only: the
 * folded rows keep their own identities for the expanded view. */
export function foldActivityUnits(units: ConversationUnit[]): ConversationUnit[] {
  const out: ConversationUnit[] = []
  let run: ActivityRowFrame[] = []
  const flush = () => {
    if (run.length >= 2) {
      out.push({ kind: "activityFold", rows: run })
    } else if (run.length === 1) {
      out.push({ kind: "activity", activity: run[0] })
    }
    run = []
  }
  for (const unit of units) {
    // An active row is a hard boundary (进行态不折叠): it passes through
    // untouched and breaks any run in progress.
    if (unit.kind !== "activity" || unit.activity.status === "active") {
      flush()
      out.push(unit)
      continue
    }
    if (run.length > 0 && foldKeyOf(unit.activity) === foldKeyOf(run[0])) {
      run.push(unit.activity)
      continue
    }
    flush()
    run = [unit.activity]
  }
  flush()
  return out
}

/** The fold row's aggregate facts: the shared copy key (the rows all carry
 * the same one), the repeat count, and the summed duration whisper (rows
 * without a duration contribute nothing; null when no row carried one). */
export function foldSummary(rows: ActivityRowFrame[]): {
  key: string | null
  count: number
  totalMs: number | null
} {
  let totalMs: number | null = null
  for (const r of rows) {
    if (r.duration_ms != null) totalMs = (totalMs ?? 0) + r.duration_ms
  }
  return { key: rows[0]?.key ?? null, count: rows.length, totalMs }
}
