import { useCallback, useEffect, useState } from "react"
import { ArrowUpRight, FileText, Film } from "@/components/ui/icons"
import { useTranslation } from "react-i18next"

import { useOptionalWorkbench } from "@/components/workbench/WorkbenchContext"
import { apiFetch } from "@/lib/api"
import { formatTimestamp } from "@/lib/utils"
import type { VideoStoryboardBlock, VideoScrubTarget } from "../timeline/types"
import { presentationAckReady } from "../timeline/reveal"
import { CompositionPreview, type VideoPreviewRead } from "./preview/CompositionPreview"
import { sameScrubTarget } from "./preview/previewSpec"
import { TextSizeScrubInput, type ScrubVersionRead } from "./TextSizeScrubInput"

const SHOW_TEXT_SIZE_SCRUB = false

interface VideoVersionRead extends ScrubVersionRead {
  composition_id: string
  composition_version_id: string
  version?: number
  content_digest: string
  presentation_digest: string
  video_preview?: VideoPreviewRead
  scrub?: VideoScrubTarget
  scenes?: { scene_id?: string }[]
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
  const workbench = useOptionalWorkbench()
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
          // When hosted inside the Studio Workbench, the chat stream displays a
          // clean artifact entrance card (never a duplicate inline player), so
          // a ready preview DTO satisfies the presentation ACK immediately.
          setPreviewReady(
            data.video_preview === undefined ||
              (workbench != null && data.video_preview.status === "ready"),
          )
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
    workbench,
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

  // Inside the Studio Workbench shell, render an Antigravity-style artifact
  // entrance card instead of duplicating an inline video player in chat.
  if (workbench && read.video_preview) {
    if (read.video_preview.status === "pending_media") {
      return (
        <p className="mt-2 text-xs text-muted-foreground">
          {t("chat.videoStoryboard.pendingMedia")}
        </p>
      )
    }
    if (read.video_preview.status === "unavailable") {
      return (
        <p className="mt-2 text-xs text-muted-foreground">
          {t("chat.videoStoryboard.previewError")}
        </p>
      )
    }

    const comp = workbench.workbench?.compositions.find(
      (c) => c.composition_id === read.composition_id,
    )
    const verMeta = comp?.versions.find(
      (v) => v.version_id === read.composition_version_id,
    )
    const compName = comp?.name || t("workbench.tabs.player")
    const versionNumber = verMeta?.version ?? read.version ?? block.version
    const sceneCount = (read.storyboard?.scenes ?? read.scenes ?? []).length
    const scrubRange =
      block.scrub?.kind === "range"
        ? { start: block.scrub.start_seconds, end: block.scrub.end_seconds }
        : null
    const metaParts = [
      versionNumber != null ? `v${versionNumber}` : null,
      scrubRange
        ? `${formatTimestamp(scrubRange.start)}–${formatTimestamp(scrubRange.end)}`
        : verMeta?.duration_seconds
          ? `${Math.round(verMeta.duration_seconds * 10) / 10}s`
          : null,
      sceneCount > 0 ? `${sceneCount} ${t("workbench.player.scenesHeading")}` : null,
    ].filter(Boolean)

    return (
      <div className="mt-2 flex max-w-md items-center gap-2 rounded-lg border border-subtle bg-card px-3 py-2.5 shadow-resting transition-colors hover:bg-accent">
        <button
          type="button"
          onClick={() =>
            workbench.openArtifact({
              key: `version:${read.composition_version_id}`,
              kind: "version",
              versionId: read.composition_version_id,
              title: compName,
              ...(scrubRange
                ? {
                    startSeconds: scrubRange.start,
                    endSeconds: scrubRange.end,
                  }
                : {}),
            })
          }
          className="flex min-w-0 flex-1 items-center gap-2.5 text-left focus-visible:outline-2 focus-visible:outline-ring"
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-foreground">
            <Film className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-foreground">
              {compName}
            </span>
            <span className="block truncate text-xs text-muted-foreground">
              {metaParts.length > 0
                ? metaParts.join(" · ")
                : t("workbench.storyboard.cardSubtitle")}
            </span>
          </span>
          <span className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
            <span>{t("workbench.storyboard.openRightAction")}</span>
            <ArrowUpRight className="size-3.5" />
          </span>
        </button>
        <button
          type="button"
          title={t("workbench.storyboard.openAction")}
          aria-label={t("workbench.storyboard.openAction")}
          onClick={() =>
            workbench.openArtifact({
              key: `storyboard:${read.composition_version_id}`,
              kind: "storyboard",
              versionId: read.composition_version_id,
              title: t("workbench.storyboard.tabTitle", { name: compName }),
            })
          }
          className="flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
        >
          <FileText className="size-4" />
        </button>
      </div>
    )
  }

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
