/** The shared moment-ordering layer (iter-3 S7, E7): the runStreamUnits
 * ordering law generalized to EVERY mixed timeline — messages × activity
 * rows sort by real moments into one walk, on and off a run. Pure, no React
 * (the vitest seam); ChatDock composes the units, this module owns the
 * ORDER (the stream never scrambles — #5 时序拍板's non-run twin). */

import type { ActivityFramePayload } from "@/lib/chatStreamFrames"
import type { OverlayMessage } from "@/components/chat/historyReplay"

/** One timed entry: `t` is epoch ms (Number.POSITIVE_INFINITY = undated —
 * an optimistic send / a pre-S7 frame is chronologically NOW and lands at
 * the end of the dated walk); `order` is the emission sequence, the stable
 * tiebreak that keeps same-moment entries in arrival order. */
export interface MomentEntry<U> {
  t: number
  order: number
  unit: U
}

/** ISO → epoch ms; missing/unparseable = undated (+∞), never a guess. */
export function momentOf(iso: string | null | undefined): number {
  const t = iso ? Date.parse(iso) : NaN
  return Number.isNaN(t) ? Number.POSITIVE_INFINITY : t
}

/** The ONE sort: real moment first, arrival order as the tiebreak. */
export function orderMoments<U>(entries: MomentEntry<U>[]): U[] {
  return [...entries]
    .sort((a, b) => a.t - b.t || a.order - b.order)
    .map((entry) => entry.unit)
}

/** One unit of the non-run conversation timeline: a message or one activity
 * row (the retired fixed bottom block's rows, now flowing at their real
 * moments). */
export type ConversationUnit =
  | { kind: "message"; message: OverlayMessage }
  | { kind: "activity"; activity: ActivityFramePayload }

/** The non-run timeline (S7: messages.at × activity.at 单流穿插): messages
 * and the turn's activity rows interleave by real moment. Messages claim
 * the lower order numbers (they predate the turn's work); a same-moment tie
 * lands the message first. The activity row's `at` is its BIRTH (the
 * reducer preserves the first-seen stamp) — a settled row never moves. */
export function buildConversationUnits(
  messages: OverlayMessage[],
  activities: ActivityFramePayload[],
): ConversationUnit[] {
  const entries: MomentEntry<ConversationUnit>[] = []
  let order = 0
  for (const m of messages) {
    entries.push({ t: momentOf(m.at), order: order++, unit: { kind: "message", message: m } })
  }
  for (const a of activities) {
    entries.push({ t: momentOf(a.at), order: order++, unit: { kind: "activity", activity: a } })
  }
  return orderMoments(entries)
}
