/** TEMPORARY forensic instrumentation (2026-10-15, mobile-tab SSE 取证):
 * client-side trace for the "DevTools mobile emulation + tab switch → no
 * reply" hunt. Every entry goes to console AND a localStorage ring buffer,
 * so the trace survives a repro run where DevTools was closed. Dump after a
 * repro with:  copy(localStorage.getItem("sse-probe-log"))
 *
 * DELETE this file and every sseProbe call site once the root cause is
 * pinned — the probe is evidence-gathering, never product code. */

const KEY = "sse-probe-log"
const MAX_CHARS = 120_000

export function sseProbe(tag: string, data?: Record<string, unknown>): void {
  if (typeof window === "undefined") return
  try {
    const line = JSON.stringify({
      t: new Date().toISOString(),
      vis: document.visibilityState,
      tag,
      ...data,
    })
    // eslint-disable-next-line no-console
    console.log("[sse-probe]", line)
    const raw = localStorage.getItem(KEY) ?? ""
    let next = raw ? `${raw}\n${line}` : line
    if (next.length > MAX_CHARS) next = next.slice(next.length - MAX_CHARS)
    localStorage.setItem(KEY, next)
  } catch {
    // The probe never breaks the app.
  }
}
