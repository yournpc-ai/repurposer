"use client"

import { useEffect, useState } from "react"
import {
  FileText,
  Mic2,
  Video,
  Image as ImageIcon,
  type LucideIcon,
} from "lucide-react"

// Videos / audio / images / transcripts & docs — the three input tiers
// ("bring whatever you have"): recording, audio-only, or transcript + photos.
export const ASSETS_ACCEPT =
  ".mp4,.mov,.webm,.mp3,.wav,.m4a,.png,.jpg,.jpeg,.webp,.txt,.md,.pdf,.doc,.docx,.srt,.vtt"

/** Type glyph for a staged file (chips / panel rows). */
export function fileIconFor(file: File): LucideIcon {
  if (file.type.startsWith("video/")) return Video
  if (file.type.startsWith("audio/")) return Mic2
  if (file.type.startsWith("image/")) return ImageIcon
  return FileText
}

/** mm:ss for chip meta (durations under an hour; clips never exceed it). */
export function formatChipDuration(seconds: number): string {
  const total = Math.round(seconds)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, "0")}`
}

/** Human file size for panel row meta ("480 MB" / "12 KB"). */
export function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(bytes >= 100 * 1024 * 1024 ? 0 : 1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

/** Uppercase extension label for doc/slides chip meta ("PDF" / "DOCX"). */
export function fileFormatLabel(file: File): string {
  const ext = file.name.includes(".") ? file.name.split(".").pop()! : ""
  return ext ? ext.toUpperCase() : (file.type.split("/").pop() ?? "FILE").toUpperCase()
}

export interface StagedFileMeta {
  /** Video / audio only, seconds (probed via element metadata). */
  duration?: number
  /** Video (first frame) / image (the file itself) — object URL. */
  thumbUrl?: string
}

/** Probe budget (2026-09-18): dims are enrichment, never a blocker — beyond
 * this the probe degrades to undefined and the upload lifecycle completes. */
const PROBE_TIMEOUT_MS = 5000

/** One-shot media-pixel probe for the upload payload (2026-09-13 用户拍板 —
 * 产物卡跟源比例): the asset row is born with meta.width/height so the
 * canvas's frame law shapes its node from birth (the server chain-head probe
 * backfills API-path uploads). Video/image only; metadata-load cheap, every
 * failure degrades to undefined (the default strip), never an upload block.
 *
 * 2026-09-18 (Batch A 验收): a detached media element is NOT guaranteed to
 * fire loadedmetadata/error (undecodable container, …) — without the timeout
 * below this promise can stay pending forever, and since runUpload gates the
 * `done` transition on it (Promise.all), that would pin an upload at
 * "100% / uploading" and block Generate. The timeout is what makes "never an
 * upload block" true. */
export function probeMediaDims(
  file: File,
): Promise<{ width: number; height: number } | undefined> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const done = (dims: { width: number; height: number } | undefined) => {
      clearTimeout(timer)
      URL.revokeObjectURL(url)
      resolve(dims && dims.width > 0 && dims.height > 0 ? dims : undefined)
    }
    const timer = setTimeout(() => done(undefined), PROBE_TIMEOUT_MS)
    if (file.type.startsWith("image/")) {
      const el = new Image()
      el.onload = () =>
        done({ width: el.naturalWidth, height: el.naturalHeight })
      el.onerror = () => done(undefined)
      el.src = url
      return
    }
    if (file.type.startsWith("video/")) {
      const el = document.createElement("video")
      el.preload = "metadata"
      el.muted = true
      el.onloadedmetadata = () =>
        done({ width: el.videoWidth, height: el.videoHeight })
      el.onerror = () => done(undefined)
      el.src = url
      return
    }
    done(undefined)
  })
}

const keyOf = (file: File) => `${file.name}:${file.size}`

/** Client-side metadata probe for a staged file. Local and cheap: images
 * resolve instantly (object URL); video/audio read element metadata, and a
 * video also grabs its first frame for the chip's thumbnail sliver. Every
 * failure path falls back to the type icon — the chip never breaks on an
 * exotic codec. Object URLs are revoked on unmount / file change. */
export function useStagedFileMeta(file: File): StagedFileMeta {
  const [meta, setMeta] = useState<StagedFileMeta>({})

  useEffect(() => {
    let revoked = false
    const url = URL.createObjectURL(file)
    const finish = (m: StagedFileMeta) => {
      if (!revoked) setMeta(m)
    }

    if (file.type.startsWith("image/")) {
      finish({ thumbUrl: url })
      return () => {
        revoked = true
        URL.revokeObjectURL(url)
      }
    }

    if (file.type.startsWith("video/")) {
      const el = document.createElement("video")
      el.preload = "metadata"
      el.muted = true
      el.src = url
      el.onloadedmetadata = () => {
        const duration = Number.isFinite(el.duration) ? el.duration : undefined
        // Grab an early decodable frame as the thumbnail sliver (past the
        // all-black first frame many recordings open with).
        el.currentTime = Math.min(0.5, (duration ?? 0) / 10)
        el.onseeked = () => {
          try {
            const canvas = document.createElement("canvas")
            canvas.width = 48
            canvas.height = 48
            const ctx = canvas.getContext("2d")
            if (ctx && el.videoWidth > 0) {
              const scale = Math.max(48 / el.videoWidth, 48 / el.videoHeight)
              const w = el.videoWidth * scale
              const h = el.videoHeight * scale
              ctx.drawImage(el, (48 - w) / 2, (48 - h) / 2, w, h)
              finish({ duration, thumbUrl: canvas.toDataURL("image/jpeg", 0.6) })
              return
            }
          } catch {
            // fall through to duration-only
          }
          finish({ duration })
        }
      }
      el.onerror = () => finish({})
      return () => {
        revoked = true
        el.onloadedmetadata = null
        el.onseeked = null
        el.onerror = null
        el.src = ""
        URL.revokeObjectURL(url)
      }
    }

    if (file.type.startsWith("audio/")) {
      const el = document.createElement("audio")
      el.preload = "metadata"
      el.src = url
      el.onloadedmetadata = () =>
        finish({ duration: Number.isFinite(el.duration) ? el.duration : undefined })
      el.onerror = () => finish({})
      return () => {
        revoked = true
        el.onloadedmetadata = null
        el.onerror = null
        el.src = ""
        URL.revokeObjectURL(url)
      }
    }

    // Docs / slides / transcripts: no probe — the chip shows the format label.
    URL.revokeObjectURL(url)
    return undefined
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyOf(file)])

  return meta
}
