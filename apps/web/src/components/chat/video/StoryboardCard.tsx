/** Storyboard presentation companion (Video Project phase B).
 *
 * The visible storyboard is the assistant's own Markdown overview, rendered
 * by Streamdown in the ordinary message row. This companion resolves the
 * SAVED version behind the block, preserves any real Generator previews, and
 * acknowledges presentation only after that prose has finished typing and
 * those previews are playable. The canonical DTO stays available to tools;
 * it is not re-rendered as a technical table for the user. */

import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import type { VideoStoryboardBlock } from "../historyReplay"

interface GeneratorPreview {
  clip_id: string
  video_url: string
  poster_url: string
}

interface VideoVersionRead {
  composition_id: string
  composition_version_id: string
  content_digest: string
  presentation_digest: string
  generator_previews?: GeneratorPreview[]
}

export function StoryboardCard({
  block,
  messageId,
  prosePresented,
  onRunStarted,
}: {
  block: VideoStoryboardBlock
  messageId: string
  /** The assistant's visible Markdown overview has finished its typewriter
   * release. Blocks are stamped after finalization on the live path; history
   * rows are already static. */
  prosePresented: boolean
  onRunStarted?: (id: string) => void
}) {
  const { t } = useTranslation()
  const [read, setRead] = useState<VideoVersionRead | null>(null)
  const [failed, setFailed] = useState(false)
  const [readyPreviews, setReadyPreviews] = useState<string[]>([])
  const [failedPreviews, setFailedPreviews] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    setRead(null)
    setFailed(false)
    setReadyPreviews([])
    setFailedPreviews([])
    apiFetch(
      `/api/v1/chat/video/versions/${block.composition_version_id}/storyboard`,
      { toast: false },
    )
      .then(async (res) => {
        if (!res.ok) throw new Error("Storyboard unavailable")
        const data = (await res.json()) as VideoVersionRead
        if (
          data.composition_id !== block.composition_id ||
          data.composition_version_id !== block.composition_version_id ||
          (block.content_digest != null && data.content_digest !== block.content_digest)
        ) {
          throw new Error("Storyboard identity mismatch")
        }
        if (!cancelled) setRead(data)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [block.composition_id, block.composition_version_id, block.content_digest])

  const previews = read?.generator_previews ?? []
  const previewsReady = previews.every((preview) => readyPreviews.includes(preview.clip_id))

  useEffect(() => {
    if (!read || !prosePresented || !previewsReady) return
    let cancelled = false
    void new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    ).then(async () => {
      if (cancelled || !messageId || !read.presentation_digest) return
      const response = await apiFetch(
        `/api/v1/chat/messages/${block.presented_message_id || messageId}/video-presentation`,
        {
          method: "POST",
          toast: false,
          body: {
            composition_version_id: block.composition_version_id,
            presentation_digest: read.presentation_digest,
          },
        },
      ).catch(() => {})
      if (response?.ok) {
        const result = await response.json()
        if (result.run_id && !cancelled) onRunStarted?.(result.run_id)
      }
    })
    return () => {
      cancelled = true
    }
  }, [
    read,
    prosePresented,
    previewsReady,
    messageId,
    block.presented_message_id,
    block.composition_version_id,
    onRunStarted,
  ])

  if (failed) {
    return (
      <p className="mt-1 text-xs text-muted-foreground">
        {t("chat.videoStoryboard.unavailable")}
      </p>
    )
  }
  if (!read || previews.length === 0) return null

  return (
    <div className="mt-1 max-w-lg">
      {previews.map((preview) => (
        <div key={preview.clip_id} className="mt-2">
          <p className="mb-1 text-xs text-meta">
            {t("chat.videoStoryboard.programPreview")}
          </p>
          <video
            className="w-full rounded-md bg-muted"
            controls
            playsInline
            preload="metadata"
            src={preview.video_url}
            poster={preview.poster_url}
            onCanPlay={() =>
              setReadyPreviews((current) =>
                current.includes(preview.clip_id) ? current : [...current, preview.clip_id],
              )
            }
            onError={() =>
              setFailedPreviews((current) =>
                current.includes(preview.clip_id) ? current : [...current, preview.clip_id],
              )
            }
          />
          {failedPreviews.includes(preview.clip_id) ? (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("chat.videoStoryboard.programPreviewError")}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  )
}
