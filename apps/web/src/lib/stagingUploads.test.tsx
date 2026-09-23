// @vitest-environment jsdom
/**
 * Regression: "chip shows 100% but Generate stays blocked by 'Files are
 * still uploading'" (Batch A acceptance finding, 2026-09-18).
 *
 * Browser-reproduced root cause: `putWithProgress` had no stall escape — a
 * PUT whose bytes all left (progress=1) but whose response never arrived
 * (a proxy stalling upload bodies) fired neither onload nor onerror, so the
 * lifecycle pinned at `{ status: "uploading", progress: 1 }` forever and the
 * launch guard (`staged.some(s => s.status !== "done")`) blocked Generate
 * with no retry affordance. Fix: the 30s silence watchdog in
 * putWithProgress. Secondary hardening in the same gate: probeMediaDims (the
 * Promise.all partner) now carries a timeout — a detached media element is
 * not guaranteed to fire loadedmetadata/error (jsdom proves the class).
 *
 * These five tests pin the lifecycle matrix:
 *   PUT ok + probe ok      → uploading → done (dims carried)
 *   PUT ok + probe timeout → uploading → done (dims undefined)
 *   PUT ok + probe error   → uploading → done (dims undefined)
 *   PUT fails              → uploading → error (retryable)
 *   PUT stalls (100% sent, response never arrives) → uploading → error
 *     (retryable) ← the browser-reproduced incident
 *
 * The probe-timeout case uses the REAL probeMediaDims: jsdom's detached
 * <video> never fires loadedmetadata/error, which is exactly the hang class.
 */
import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

// --- mock apiFetch: presign succeeds instantly ---------------------------
vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(async () => ({
    ok: true,
    json: async () => ({
      key: "staging/sess/xy_2_15s.mp4",
      upload_url: "https://storage.example/put",
    }),
  })),
}))

// --- probeMediaDims: real implementation by default, mockable per test ---
vi.mock("@/lib/stagedFiles", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/stagedFiles")>()
  return { ...actual, probeMediaDims: vi.fn(actual.probeMediaDims) }
})

import { probeMediaDims } from "@/lib/stagedFiles"
import { useStagingUploads } from "@/lib/stagingUploads"

const probeMock = vi.mocked(probeMediaDims)
const realProbe = probeMock.getMockImplementation()!

// --- fake XHR: progress to 100%, then a controllable response ------------
class FakeXHR {
  static instances: FakeXHR[] = []
  static respond: "ok" | "http500" | "networkError" | "stall" = "ok"
  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  ontimeout: (() => void) | null = null
  aborted = false
  status = 200
  open() {}
  setRequestHeader() {}
  abort() {
    this.aborted = true
  }
  send() {
    // All bytes handed to the socket — the chip renders "100%" from this…
    this.upload.onprogress?.({ lengthComputable: true, loaded: 100, total: 100 } as ProgressEvent)
    if (FakeXHR.respond === "stall") return // …then silence: no load, no error (the proxy stall)
    queueMicrotask(() => {
      if (FakeXHR.respond === "ok") this.onload?.()
      else if (FakeXHR.respond === "http500") {
        this.status = 500
        this.onload?.()
      } else this.onerror?.()
    })
  }
  constructor() {
    FakeXHR.instances.push(this)
  }
}

const videoFile = () => new File([new Uint8Array(100)], "xy_2_15s.mp4", { type: "video/mp4" })

async function flush() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 20))
  })
}

describe("useStagingUploads lifecycle", () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    probeMock.mockReset()
    FakeXHR.instances = []
    FakeXHR.respond = "ok"
  })

  it("PUT ok + probe ok → done with dims", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR)
    probeMock.mockResolvedValue({ width: 1920, height: 1080 })

    const { result } = renderHook(() => useStagingUploads())
    act(() => result.current.addFiles([videoFile()]))
    await flush()

    const item = result.current.staged[0]
    expect(item.status).toBe("done")
    expect(item.progress).toBe(1)
    expect(item.dims).toEqual({ width: 1920, height: 1080 })
    expect(result.current.staged.some((s) => s.status !== "done")).toBe(false)
  })

  it("PUT ok + probe never settles → timeout degrades to done (probe hang class)", async () => {
    vi.useFakeTimers()
    vi.stubGlobal("XMLHttpRequest", FakeXHR)
    // jsdom lacks object URLs; the real probe needs them.
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:fake"),
      revokeObjectURL: vi.fn(),
    })
    probeMock.mockImplementation(realProbe) // real hang: jsdom <video> never fires

    const { result } = renderHook(() => useStagingUploads())
    act(() => result.current.addFiles([videoFile()]))

    // Presign + PUT resolve; progress hits 1 while the probe hangs.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20)
    })
    expect(result.current.staged[0].progress).toBe(1)
    expect(result.current.staged[0].status).toBe("uploading") // the stuck window

    // The probe timeout must complete the lifecycle — 100% ⇒ done.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    const item = result.current.staged[0]
    expect(item.status).toBe("done")
    expect(item.dims).toBeUndefined()
    expect(result.current.staged.some((s) => s.status !== "done")).toBe(false)
  })

  it("PUT ok + probe error-degraded (undefined) → done", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR)
    probeMock.mockResolvedValue(undefined)

    const { result } = renderHook(() => useStagingUploads())
    act(() => result.current.addFiles([videoFile()]))
    await flush()

    expect(result.current.staged[0].status).toBe("done")
    expect(result.current.staged[0].dims).toBeUndefined()
  })

  it("PUT stalls at 100% (no load/error ever) → stall watchdog → error, retry recovers", async () => {
    vi.useFakeTimers()
    vi.stubGlobal("XMLHttpRequest", FakeXHR)
    probeMock.mockResolvedValue(undefined)
    FakeXHR.respond = "stall"

    const { result } = renderHook(() => useStagingUploads())
    act(() => result.current.addFiles([videoFile()]))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20)
    })
    // The exact user-visible stuck state: progress=100%, lifecycle uploading.
    expect(result.current.staged[0].progress).toBe(1)
    expect(result.current.staged[0].status).toBe("uploading")

    // The stall watchdog must end it as a retryable error — never forever.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000)
    })
    expect(result.current.staged[0].status).toBe("error")

    FakeXHR.respond = "ok"
    act(() => result.current.retryStaged(result.current.staged[0]))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20)
    })
    expect(result.current.staged[0].status).toBe("done")
  })

  it.each(["http500", "networkError"] as const)(
    "PUT fails (%s) → error (never a silent permanent uploading)",
    async (mode) => {
      vi.stubGlobal("XMLHttpRequest", FakeXHR)
      probeMock.mockResolvedValue(undefined)
      FakeXHR.respond = mode

      const { result } = renderHook(() => useStagingUploads())
      act(() => result.current.addFiles([videoFile()]))
      await flush()
      expect(result.current.staged[0].status).toBe("error")

      // Retry re-runs the upload; a later success completes the lifecycle.
      FakeXHR.respond = "ok"
      act(() => result.current.retryStaged(result.current.staged[0]))
      await flush()
      expect(result.current.staged[0].status).toBe("done")
    },
  )
})
