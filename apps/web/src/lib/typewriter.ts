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
import { sseProbe } from "@/lib/sse-probe" // TEMPORARY forensics — delete with the probe

export function createTypewriter(
  append: (text: string) => void,
  /** Fires on the busy↔idle edge (2026-09-09 thinking 门槛): while the
   * typewriter has anything left to say, the prose in motion IS the turn's
   * activity evidence and chrome status lines (the thinking row) must hide;
   * only when it runs dry does the turn need a status owner again. Idle is
   * reported after a short grace so natural burst gaps in the model's
   * output don't strobe the chrome. */
  onActiveChange?: (active: boolean) => void,
) {
  let buffer = ""
  let timer: ReturnType<typeof setInterval> | null = null
  let drainWaiters: (() => void)[] = []
  let active = false
  let idleTimer: ReturnType<typeof setTimeout> | null = null
  const IDLE_GRACE_MS = 400

  const setActive = (next: boolean) => {
    if (active === next) return
    active = next
    onActiveChange?.(next)
  }

  const markMaybeIdle = () => {
    if (buffer || idleTimer) return
    idleTimer = setTimeout(() => {
      idleTimer = null
      if (!buffer) setActive(false)
    }, IDLE_GRACE_MS)
  }

  const settleDrain = () => {
    if (buffer) return
    const waiters = drainWaiters
    if (waiters.length) sseProbe("tw.drain.done", { waiters: waiters.length })
    drainWaiters = []
    for (const resolve of waiters) resolve()
    markMaybeIdle()
  }

  const tick = () => {
    if (!buffer) return
    // Base pace ~2 chars per tick; a growing backlog releases faster to
    // catch up, so a long reply never lags far behind the model.
    const n = Math.max(2, Math.ceil(buffer.length / 10))
    append(buffer.slice(0, n))
    buffer = buffer.slice(n)
    settleDrain()
  }

  return {
    push(text: string) {
      if (idleTimer) {
        clearTimeout(idleTimer)
        idleTimer = null
      }
      buffer += text
      sseProbe("tw.push", { chars: text.length, buf: buffer.length })
      if (buffer) setActive(true)
      if (!timer) timer = setInterval(tick, 24)
    },
    /** Resolves once every buffered char has been released (flush resolves
     * too) — the zero-delta last gate awaits it before landing a dock, so
     * the prose visibly LEADS and the question follows (打字机律). */
    drain(): Promise<void> {
      if (!buffer) return Promise.resolve()
      sseProbe("tw.drain.wait", { buf: buffer.length })
      return new Promise((resolve) => {
        drainWaiters.push(resolve)
      })
    },
    /** Release everything remaining and stop the clock. */
    flush() {
      sseProbe("tw.flush", { rest: buffer.length })
      if (idleTimer) {
        clearTimeout(idleTimer)
        idleTimer = null
      }
      if (timer) {
        clearInterval(timer)
        timer = null
      }
      if (buffer) {
        const rest = buffer
        buffer = ""
        append(rest)
      }
      setActive(false)
      settleDrain()
    },
  }
}
