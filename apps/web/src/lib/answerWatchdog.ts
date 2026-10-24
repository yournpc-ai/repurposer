/** The answer turn's dead-stream watchdog (extracted pure seam, 2026-10-22 —
 * the chat turn's machinery twin, minimal form): the answer endpoint shares
 * the server's keepalive guarantee (the SSE pump's bare-{} thinking frame at
 * least every 15s), so a long total frame silence is a dead pipe by
 * construction — never a slow model. Answer turns (option click / freeform /
 * the Start pill) have no user stop and no reconcile — without this a
 * silently dead pipe left chatBusy stuck forever (the now-line shimmering,
 * the composer dead until a manual refresh).
 *
 * Pure timing machine: the caller owns the thresholds (the chat turn's
 * dead-stream constants — the server guarantee is one seat) and wires
 * `signal` into streamAnswer, `poke` into every frame handler (keepalives
 * included — a long LLM window's ONLY frames are the bare thinking beats),
 * and `disarm` into the turn's finally. One-shot, mirroring the chat
 * watchdog: death is declared once — re-firing only re-aborts a corpse and
 * leaks the interval. */

export interface AnswerWatchdog {
  /** Aborts the answer stream on declared death (streamAnswer's `signal`). */
  signal: AbortSignal
  /** Every received frame resets the silence clock. */
  poke: () => void
  /** The turn's finally disarms — a settled turn never trips post-mortem. */
  disarm: () => void
}

export function armAnswerWatchdog(deadMs: number, tickMs: number): AnswerWatchdog {
  const ctrl = new AbortController()
  let lastFrameAt = Date.now()
  const id = setInterval(() => {
    if (Date.now() - lastFrameAt > deadMs) {
      clearInterval(id) // one-shot — the chat watchdog's same law
      ctrl.abort()
    }
  }, tickMs)
  return {
    signal: ctrl.signal,
    poke: () => {
      lastFrameAt = Date.now()
    },
    disarm: () => clearInterval(id),
  }
}
