import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { apiFetch } from "@/lib/api"
import type { VideoStoryboardBlock, VideoScrubTarget } from "../timeline/types"
import { presentationAckReady } from "../timeline/reveal"
import { CompositionPreview, type VideoPreviewRead } from "./preview/CompositionPreview"
import { TextSizeScrubInput, type ScrubVersionRead } from "./TextSizeScrubInput"

interface VideoVersionRead extends ScrubVersionRead {
  composition_id: string
  composition_version_id: string
  content_digest: string
  presentation_digest: string
  video_preview?: VideoPreviewRead
  scrub?: VideoScrubTarget
}

export function StoryboardCard({
  block,
  messageId,
  prosePresented,
  allowPresentationAck,
  onRunStarted,
  onReady,
}: {
  block: VideoStoryboardBlock
  messageId: string
  /** The assistant's visible Markdown overview has finished its typewriter
   * release. Blocks are stamped after finalization on the live path; history
   * rows are already static. */
  prosePresented: boolean
  /** Live first presentation, or the server's exact pending/authorized
   * delayed-start recovery. Ordinary history passes false. */
  allowPresentationAck: boolean
  onRunStarted?: (id: string) => void
  onReady?: (ready: boolean) => void
}) {
  const { t } = useTranslation()
  const [activeVersionId, setActiveVersionId] = useState(block.composition_version_id)
  const [read, setRead] = useState<VideoVersionRead | null>(null)
  const [failed, setFailed] = useState(false)
  const [previewReady, setPreviewReady] = useState(!block.scrub)
  const [textSizeDraft, setTextSizeDraft] = useState<{
    clipId: string
    fontSize: number
  } | null>(null)
  const handleDraftChange = useCallback((draft: { clipId: string; fontSize: number } | null) => {
    setTextSizeDraft(draft)
  }, [])
  const handleApplied = useCallback((versionId: string) => {
    setTextSizeDraft(null)
    setRead(null)
    setPreviewReady(true)
    setActiveVersionId(versionId)
  }, [])

  useEffect(() => {
    let cancelled = false
    const scrub = activeVersionId === block.composition_version_id ? block.scrub : undefined
    setRead(null)
    setFailed(false)
    setPreviewReady(!scrub)
    const query = scrub ? `?scrub=${encodeURIComponent(JSON.stringify(scrub))}` : ""
    apiFetch(
      `/api/v1/chat/video/versions/${activeVersionId}/storyboard${query}`,
      { toast: false },
    )
      .then(async (res) => {
        if (!res.ok) throw new Error("Storyboard unavailable")
        const data = (await res.json()) as VideoVersionRead
        if (
          data.composition_id !== block.composition_id ||
          data.composition_version_id !== activeVersionId ||
          (
            activeVersionId === block.composition_version_id &&
            block.content_digest != null &&
            data.content_digest !== block.content_digest
          ) ||
          JSON.stringify(data.scrub ?? null) !== JSON.stringify(scrub ?? null)
        ) {
          throw new Error("Storyboard identity mismatch")
        }
        if (!cancelled) {
          setRead(data)
          setPreviewReady(data.video_preview === undefined)
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [
    activeVersionId,
    block.composition_id,
    block.composition_version_id,
    block.content_digest,
    block.scrub,
  ])

  useEffect(() => {
    onReady?.(failed || read !== null)
  }, [failed, onReady, read])

  useEffect(() => {
    if (
      activeVersionId !== block.composition_version_id ||
      !read ||
      !presentationAckReady({
        allowed: allowPresentationAck,
        dtoReady: read !== null,
        prosePresented,
        previewsReady: previewReady,
      })
    ) return
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
    activeVersionId,
    read,
    previewReady,
    prosePresented,
    allowPresentationAck,
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
  if (!read) return null
  return (
    <>
      {read.video_preview && (
        <CompositionPreview
          preview={read.video_preview}
          identity={{
            composition_id: read.composition_id,
            composition_version_id: read.composition_version_id,
            content_digest: read.content_digest,
          }}
          textSizeDraft={textSizeDraft}
          onReady={() => setPreviewReady(true)}
          onError={() => setPreviewReady(false)}
        />
      )}
      {read.is_current === false &&
        read.current_version_id &&
        read.current_version_id !== read.composition_version_id && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2"
            onClick={() => handleApplied(read.current_version_id!)}
          >
            {t("chat.videoStoryboard.scrub.openCurrent")}
          </Button>
        )}
      <TextSizeScrubInput
        read={read}
        onDraftChange={handleDraftChange}
        onApplied={handleApplied}
      />
    </>
  )
}
