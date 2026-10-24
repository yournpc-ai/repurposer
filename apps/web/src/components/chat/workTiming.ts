import { useEffect, useState } from "react"

/** Ticking clock shared by chat and run work segments. Null until mounted so
 * SSR and the first client render agree; the caller decides which live phase
 * needs a ticking display. */
export function useNow(live: boolean): number | null {
  const [now, setNow] = useState<number | null>(null)
  useEffect(() => {
    if (!live) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [live])
  return now
}

/** "1m 6s" / "45s" / "1h 3m" — the shared elapsed shorthand for work
 * segments. Sub-second visible work reads as "1s" rather than pretending
 * the row never existed. */
export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (ms > 0 && s === 0) return "1s"
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}
