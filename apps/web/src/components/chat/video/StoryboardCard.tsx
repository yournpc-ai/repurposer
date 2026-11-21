import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button-clean"
import { apiFetch } from "@/lib/api"
import type { VideoStoryboardBlock, VideoScrubTarget } from "../timeline/types"
import { presentationAckReady } from "../timeline/reveal"
import { CompositionPreview, type VideoPreviewRead } from "./preview/CompositionPreview"
import { sameScrubTarget } from "./preview/previewSpec"
import { TextSizeScrubInput, type ScrubVersionRead } from "./TextSizeScrubInput"

const SHOW_TEXT_SIZE_SCRUB = false

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
  onReady,
}: {
  block: VideoStoryboardBlock
  messageId: string
  /** The assistant's visible Markdown overview has finished its typewriter
   * release. Blocks are stamped after finalization on the live path; history
   * rows are already static. */
  prosePresented: boolean
  /** The live card or the current incomplete presentation restored from history. */
  allowPresentationAck: boolean
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
          !sameScrubTarget(data.scrub, scrub) ||
          (scrub && !data.video_preview)
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
      block.scrub?.kind === "range" ||
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
      await apiFetch(
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
  ])

  if (failed) {
    return (
      <p role="status" className="mt-1 text-xs text-muted-foreground">
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
          onReady={() => setPreviewReady(read.video_preview?.status === "ready")}
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
      {SHOW_TEXT_SIZE_SCRUB && (
        <TextSizeScrubInput
          read={read}
          onDraftChange={handleDraftChange}
          onApplied={handleApplied}
        />
      )}
    </>
  )
}
