"use client"

import { useCallback, useMemo, useState } from "react"

import { apiFetch } from "@/lib/api"
import { probeMediaDims } from "@/lib/stagedFiles"

/**
 * useStagingUploads — the pre-project upload staging lifecycle (Product Flow
 * Alignment Batch A, contract docs/tasks/product-flow-alignment.md §5).
 *
 * One hook instance = one staging session (a client-generated session id
 * riding the storage key). Picked files upload IMMEDIATELY, direct-to-storage
 * (`POST /uploads/staging/upload-url` → PUT with real progress), while the
 * user is still writing the prompt; Generate only attaches the already-
 * uploaded keys (`POST /projects/{id}/assets/from-staging`, in the launcher).
 * The × gesture deletes the staged object best-effort; anything orphaned is
 * the server reaper's job (24h TTL). The chip anatomy mirrors the chat
 * dock's StagedUpload law: picked → uploading (spinner + %) → done / error
 * (retry or remove) — nothing is consumed until send.
 */
export interface StagingUpload {
  localId: string
  file: File
  status: "uploading" | "done" | "error"
  /** 0..1 while uploading (XHR progress events; fetch has none). */
  progress: number
  /** Staging object key — present once done, rides the attach payload. */
  key?: string
  /** Client-probed pixels (产物卡跟源比例) — rides the attach payload. */
  dims?: { width: number; height: number }
}

/** Silence budget (2026-09-18, Batch A 验收发现): a PUT whose bytes all left
 * (progress=100%) but whose RESPONSE never arrives — e.g. a proxy that stalls
 * upload bodies — fired neither onload nor onerror and pinned the lifecycle
 * at `uploading`/100% forever, blocking Generate with no escape. Any progress
 * event re-arms the watchdog; 30s of total silence means the wire is dead. */
const PUT_STALL_TIMEOUT_MS = 30_000

/** Direct-to-storage PUT with real upload progress (fetch streams lack it). */
function putWithProgress(
  url: string,
  file: File,
  onProgress: (ratio: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    let settled = false
    const stall = () => {
      if (settled) return
      settled = true
      xhr.abort()
      reject(new Error("Upload stalled (no response)"))
    }
    let watchdog = setTimeout(stall, PUT_STALL_TIMEOUT_MS)
    const rearm = () => {
      clearTimeout(watchdog)
      watchdog = setTimeout(stall, PUT_STALL_TIMEOUT_MS)
    }
    const finish = (fn: () => void) => () => {
      if (settled) return
      settled = true
      clearTimeout(watchdog)
      fn()
    }
    xhr.open("PUT", url)
    if (file.type) xhr.setRequestHeader("Content-Type", file.type)
    xhr.upload.onprogress = (e) => {
      rearm()
      if (e.lengthComputable && e.total > 0) onProgress(e.loaded / e.total)
    }
    xhr.onload = finish(() =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`Upload failed (HTTP ${xhr.status})`)),
    )
    xhr.onerror = finish(() => reject(new Error("Upload failed")))
    xhr.send(file)
  })
}

export function useStagingUploads() {
  // One session per composer/overlay instance; regenerated on remount. SSR
  // safe: Node's global crypto provides randomUUID, and the id never
  // reaches the HTML.
  const sessionId = useMemo(() => crypto.randomUUID(), [])
  const [staged, setStaged] = useState<StagingUpload[]>([])

  const runUpload = useCallback(
    async (localId: string, material: File) => {
      try {
        const urlRes = await apiFetch("/api/v1/uploads/staging/upload-url", {
          method: "POST",
          body: {
            session_id: sessionId,
            filename: material.name,
            content_type: material.type || undefined,
          },
          toast: false,
        })
        if (!urlRes.ok) throw new Error("Failed to get upload URL")
        const { key, upload_url } = (await urlRes.json()) as {
          key: string
          upload_url: string
        }

        // The PUT (progress-reporting) and the pixel probe ride the same
        // beat — attach later births the asset row with its real dims
        // (产物卡跟源比例, 2026-09-13).
        const [, dims] = await Promise.all([
          putWithProgress(upload_url, material, (ratio) =>
            setStaged((prev) =>
              prev.map((s) => (s.localId === localId ? { ...s, progress: ratio } : s)),
            ),
          ),
          probeMediaDims(material),
        ])

        setStaged((prev) =>
          prev.map((s) =>
            s.localId === localId ? { ...s, status: "done", progress: 1, key, dims } : s,
          ),
        )
      } catch {
        setStaged((prev) =>
          prev.map((s) =>
            // A removal mid-flight must not resurrect the chip.
            s.localId === localId && s.status !== "done" ? { ...s, status: "error" } : s,
          ),
        )
      }
    },
    [sessionId],
  )

  const addFiles = useCallback(
    (picked: File[]) => {
      if (picked.length === 0) return
      const additions: StagingUpload[] = []
      setStaged((prev) => {
        const existing = new Set(prev.map((s) => `${s.file.name}:${s.file.size}`))
        for (const file of picked) {
          if (existing.has(`${file.name}:${file.size}`)) continue
          additions.push({ localId: crypto.randomUUID(), file, status: "uploading", progress: 0 })
        }
        return [...prev, ...additions]
      })
      for (const s of additions) void runUpload(s.localId, s.file)
    },
    [runUpload],
  )

  /** × : drop the chip; an already-uploaded object is deleted best-effort
   * (staged ≠ attached — it must not linger past its TTL). */
  const removeStaged = useCallback((item: StagingUpload) => {
    setStaged((prev) => prev.filter((s) => s.localId !== item.localId))
    if (item.key) {
      void apiFetch(`/api/v1/uploads/staging?key=${encodeURIComponent(item.key)}`, {
        method: "DELETE",
        toast: false,
      }).catch(() => {})
    }
  }, [])

  const retryStaged = useCallback(
    (item: StagingUpload) => {
      setStaged((prev) =>
        prev.map((s) =>
          s.localId === item.localId ? { ...s, status: "uploading", progress: 0 } : s,
        ),
      )
      void runUpload(item.localId, item.file)
    },
    [runUpload],
  )

  /** Send consumes (chip law ②): clear local state after a successful
   * attach — the objects are now asset-referenced, so the reaper skips them. */
  const clearStaged = useCallback(() => setStaged([]), [])

  return { staged, addFiles, removeStaged, retryStaged, clearStaged }
}
