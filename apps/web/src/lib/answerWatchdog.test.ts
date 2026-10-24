/** armAnswerWatchdog — the answer turn's dead-stream watchdog (pure timing
 * machine, fake-timer driven): a dead pipe is declared only after the full
 * silence threshold, pokes reset the clock, the trip is one-shot, and a
 * disarmed watchdog never fires post-mortem. The state problem under test:
 * a silently dead answer stream used to leave chatBusy stuck forever (the
 * now-line shimmering, the composer dead) — this primitive is the fix's
 * only moving part. */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { armAnswerWatchdog } from "./answerWatchdog"

describe("armAnswerWatchdog", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("stays silent while frames keep arriving", () => {
    const w = armAnswerWatchdog(45_000, 10_000)
    for (let i = 0; i < 10; i++) {
      vi.advanceTimersByTime(20_000) // 20s of silence, then a frame
      w.poke()
    }
    expect(w.signal.aborted).toBe(false)
    w.disarm()
  })

  it("aborts after the full silence threshold", () => {
    const w = armAnswerWatchdog(45_000, 10_000)
    vi.advanceTimersByTime(44_999)
    expect(w.signal.aborted).toBe(false)
    vi.advanceTimersByTime(10_000)
    expect(w.signal.aborted).toBe(true)
  })

  it("a poke inside the window pushes the trip out", () => {
    const w = armAnswerWatchdog(45_000, 10_000)
    vi.advanceTimersByTime(40_000)
    w.poke() // a keepalive lands at 40s — the clock restarts
    vi.advanceTimersByTime(40_000)
    expect(w.signal.aborted).toBe(false)
    vi.advanceTimersByTime(10_000)
    expect(w.signal.aborted).toBe(true)
  })

  it("trips once — the interval never re-fires or leaks", () => {
    const w = armAnswerWatchdog(45_000, 10_000)
    vi.advanceTimersByTime(50_000)
    expect(w.signal.aborted).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
    vi.advanceTimersByTime(120_000)
    expect(w.signal.aborted).toBe(true) // still aborted, no re-entry
    expect(vi.getTimerCount()).toBe(0)
  })

  it("disarm before the deadline means never", () => {
    const w = armAnswerWatchdog(45_000, 10_000)
    vi.advanceTimersByTime(30_000)
    w.disarm()
    vi.advanceTimersByTime(120_000)
    expect(w.signal.aborted).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })
})
