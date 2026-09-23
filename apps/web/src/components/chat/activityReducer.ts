/** The turn's Activity Stream reducer pair (ADR-087 §3 Phase 2; extracted
 * from ChatDock as a PURE test seam, Phase 3 Batch A — 行为零变化).
 *
 * The wire is append-only: a status flip arrives as a NEW frame on the same
 * `activity_id`, so the list keeps the latest frame per id in ARRIVAL
 * (= seq) order. The block is per-turn (v1: no cross-session replay — the
 * contract's no-persistence line): the next turn starts from an empty list,
 * and a settling turn sweeps every still-active frame to the terminal
 * status (the client twin of the server's T16-B sweep — 假活跃禁令: a
 * settling turn never leaves an activity spinning forever). */

import type { ActivityFramePayload } from "@/lib/chat-stream"

/** The per-turn reset — a new turn's block starts empty (the previous
 * turn's stream settles in place below its bubble, it never carries over). */
export function resetActivities(): ActivityFramePayload[] {
  return []
}

/** Upsert one frame: idempotent by activity_id (a re-delivered frame
 * replaces, never duplicates); first sighting appends in arrival order.
 * S7/E7: the merged row keeps the FIRST-seen `at` as the activity's birth
 * moment (a settle frame's own `at` is its close time — the row never moves
 * in the timeline), while status / key / duration_ms take the latest. */
export function upsertActivityFrame(
  prev: ActivityFramePayload[],
  frame: ActivityFramePayload,
): ActivityFramePayload[] {
  const i = prev.findIndex((a) => a.activity_id === frame.activity_id)
  if (i === -1) return [...prev, frame]
  const next = [...prev]
  next[i] = { ...frame, at: prev[i].at ?? frame.at }
  return next
}

/** The defensive settle sweep: every still-active frame flips to the
 * turn's terminal status; already-terminal frames pass through untouched
 * (the sweep is zero-dangling, never a rewrite of settled history). */
export function sweepActivities(
  prev: ActivityFramePayload[],
  status: "completed" | "failed" | "cancelled",
): ActivityFramePayload[] {
  return prev.map((a) => (a.status === "active" ? { ...a, status } : a))
}
