/** Lifecycle stamp consumption (ADR-087 §2 + Phase 3 判词 2, 2026-09-19) —
 * the ONE predicate family every client surface reads. The stamp is the
 * server-named lifecycle projection; clients never derive lifecycle from
 * artifact existence, and — the P0 ruling this module pins — a MISSING stamp
 * is never read as ready. The retired `lifecycle ? … : true` fallbacks were
 * a hidden Lifecycle Authority: an absent frame silently defaulted every
 * gate open. The tri-state makes the third case explicit:
 *
 *   stamp present, flag true  → "ready"
 *   stamp present, flag false → "blocked" (the server named a NOT-ready —
 *                               `blockers` carries the reason channel)
 *   stamp missing / null      → "unknown" — loading / pre-first-fetch frame;
 *                               NO lifecycle decision is taken on it
 *
 * Surfaces consume the boolean helpers; the verdicts exist so the contract
 * tests can prove missing ≠ ready (and so a future loading affordance has
 * the third state to read). */

import type { LifecycleStamp } from "./types"

export type StampVerdict = "ready" | "blocked" | "unknown"

/** PLAN_READY — drives the review surfaces (desktop canvas flip, confirm
 * pill, mobile plan card; ADR-087 §2 Presentation mapping). */
export function planReadyVerdict(
  stamp: LifecycleStamp | null | undefined,
): StampVerdict {
  if (!stamp) return "unknown"
  return stamp.plan_ready ? "ready" : "blocked"
}

/** CONFIRMATION_READY — drives Confirm enablement only (the four conjuncts
 * stay server-side; the client reads the rollup, never re-derives them). */
export function confirmationReadyVerdict(
  stamp: LifecycleStamp | null | undefined,
): StampVerdict {
  if (!stamp) return "unknown"
  return stamp.confirmation_ready ? "ready" : "blocked"
}

/** The consumption form: ready ONLY on a present stamp's true. */
export function isPlanReady(stamp: LifecycleStamp | null | undefined): boolean {
  return planReadyVerdict(stamp) === "ready"
}

export function isConfirmationReady(
  stamp: LifecycleStamp | null | undefined,
): boolean {
  return confirmationReadyVerdict(stamp) === "ready"
}
