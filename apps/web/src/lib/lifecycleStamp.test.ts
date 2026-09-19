/** Stamp-consumption contract (Phase 3 Batch A 验收 ④: stamp missing ≠
 * ready; ADR-087 §2 + 判词 2). The P0 law: a missing lifecycle stamp is
 * "unknown" — loading, not ready — and no surface may take a lifecycle
 * decision on it. The retired `lifecycle ? … : true` fallbacks (ChatDock
 * ×4) read an absent frame as fully ready; these tests pin the tri-state so
 * the fallback can never reappear as an equality-true default. */

import { describe, expect, it } from "vitest"

import {
  confirmationReadyVerdict,
  isConfirmationReady,
  isPlanReady,
  planReadyVerdict,
} from "./lifecycleStamp"
import type { LifecycleStamp } from "./types"

function stamp(overrides: Partial<LifecycleStamp>): LifecycleStamp {
  return {
    state: "preparing",
    material_ready: false,
    plan_ready: false,
    confirmation_scope_ready: false,
    charge_semantics_ready: false,
    no_active_conflicting_run: false,
    confirmation_ready: false,
    blockers: [],
    charge: { known: null, deferred: false },
    ...overrides,
  }
}

describe("planReadyVerdict — tri-state", () => {
  it("present + true → ready", () => {
    expect(planReadyVerdict(stamp({ plan_ready: true }))).toBe("ready")
  })
  it("present + false → blocked (a named NOT-ready, not an absence)", () => {
    expect(planReadyVerdict(stamp({ plan_ready: false }))).toBe("blocked")
  })
  it("missing → unknown", () => {
    expect(planReadyVerdict(null)).toBe("unknown")
    expect(planReadyVerdict(undefined)).toBe("unknown")
  })
})

describe("confirmationReadyVerdict — tri-state", () => {
  it("present + true → ready", () => {
    expect(confirmationReadyVerdict(stamp({ confirmation_ready: true }))).toBe(
      "ready",
    )
  })
  it("present + false → blocked", () => {
    expect(confirmationReadyVerdict(stamp({ confirmation_ready: false }))).toBe(
      "blocked",
    )
  })
  it("missing → unknown", () => {
    expect(confirmationReadyVerdict(null)).toBe("unknown")
  })
})

describe("missing ≠ ready (判词 2 — the core inequality)", () => {
  it("isPlanReady: missing stamp is NOT ready", () => {
    expect(isPlanReady(null)).toBe(false)
    expect(isPlanReady(undefined)).toBe(false)
  })
  it("isConfirmationReady: missing stamp is NOT ready", () => {
    expect(isConfirmationReady(null)).toBe(false)
    expect(isConfirmationReady(undefined)).toBe(false)
  })
  it("unknown is a third state — neither ready nor a named block", () => {
    // The distinction the fallback erased: "unknown" must never collapse
    // onto either pole of a present stamp.
    expect(planReadyVerdict(null)).not.toBe("ready")
    expect(planReadyVerdict(null)).not.toBe("blocked")
  })
  it("the boolean helpers read ONLY the present-true pole", () => {
    expect(isPlanReady(stamp({ plan_ready: true }))).toBe(true)
    expect(isPlanReady(stamp({ plan_ready: false }))).toBe(false)
    expect(isConfirmationReady(stamp({ confirmation_ready: true }))).toBe(true)
    expect(isConfirmationReady(stamp({ confirmation_ready: false }))).toBe(false)
  })
})
