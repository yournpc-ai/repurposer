/** Typewriter pacing for streamed chat prose (2026-08-05 manual-test fix).
 *
 * Reasoning models deliver a short plan echo in one or two coarse chunks
 * right before the terminal frame, so appending raw deltas reads as "the
 * whole reply popped in at once". This buffers incoming deltas and releases
 * them on a steady cadence, speeding up automatically when the backlog
 * grows; `flush()` at the turn's terminal frame (or abort/failure) releases
 * everything remaining — the envelope stays authoritative, pacing only
 * changes HOW the preview appears.
 *
 * Client-side only: use inside event handlers / effects, never during SSR.
 */
export function createTypewriter(append: (text: string) => void) {
  let buffer = ""
  let timer: ReturnType<typeof setInterval> | null = null

  const tick = () => {
    if (!buffer) return
    // Base pace ~2 chars per tick; a growing backlog releases faster to
    // catch up, so a long reply never lags far behind the model.
    const n = Math.max(2, Math.ceil(buffer.length / 10))
    append(buffer.slice(0, n))
    buffer = buffer.slice(n)
  }

  return {
    push(text: string) {
      buffer += text
      if (!timer) timer = setInterval(tick, 24)
    },
    /** Release everything remaining and stop the clock. */
    flush() {
      if (timer) {
        clearInterval(timer)
        timer = null
      }
      if (buffer) {
        const rest = buffer
        buffer = ""
        append(rest)
      }
    },
  }
}
