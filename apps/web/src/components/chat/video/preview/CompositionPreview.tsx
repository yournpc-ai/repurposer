import { useCallback, useEffect, useId, useMemo, useState } from "react"
import { Maximize2 } from "@/components/ui/icons"

import { useTranslation } from "react-i18next"

import { IconButton } from "@/components/ui/icon-button-clean"

import { RemotionPreviewAdapter } from "./RemotionPreviewAdapter"
import { parseScopedPreviewSpec, previewWithTextFontSize, type VideoScrubScope } from "./previewSpec"

export interface CompositionPreviewSelection {
  id: string
  slotId: string
  spec: ReturnType<typeof parseScopedPreviewSpec>
}

export interface VideoPreviewRead {
  status: "ready" | "pending_media" | "unavailable"
  video_spec?: unknown
  scope?: VideoScrubScope
}

export function CompositionPreview({
  preview,
  identity,
  onReady,
  onError,
  onOpenPreview,
  activePreviewId,
  textSizeDraft,
}: {
  preview: VideoPreviewRead
  identity: {
    composition_id: string
    composition_version_id: string
    content_digest: string
  }
  onOpenPreview?: (selection: CompositionPreviewSelection) => void
  activePreviewId?: string | null
  textSizeDraft?: { clipId: string; fontSize: number } | null
  onReady: () => void
  onError: () => void
}) {
  const { t } = useTranslation()
  const slotId = useId()
  const expanded = activePreviewId === slotId
  const [runtimeFailed, setRuntimeFailed] = useState(false)
  const handleError = useCallback(() => {
    setRuntimeFailed(true)
    onError()
  }, [onError])
  useEffect(() => {
    setRuntimeFailed(false)
  }, [identity.composition_version_id, identity.content_digest])
  const spec = useMemo(() => {
    if (preview.status !== "ready") return null
    try {
      const parsed = parseScopedPreviewSpec(preview.video_spec, preview.scope, identity)
      return textSizeDraft
        ? previewWithTextFontSize(parsed, textSizeDraft.clipId, textSizeDraft.fontSize)
        : parsed
    } catch {
      return null
    }
  }, [identity, preview, textSizeDraft])

  useEffect(() => {
    if (preview.status === "pending_media") onReady()
    if (preview.status === "unavailable" || (preview.status === "ready" && !spec)) handleError()
  }, [handleError, onReady, preview.status, spec])

  if (preview.status === "pending_media") {
    return (
      <p className="mt-2 text-xs text-muted-foreground">
        {t("chat.videoStoryboard.pendingMedia")}
      </p>
    )
  }
  if (preview.status === "unavailable" || runtimeFailed || !spec) {
    return (
      <p className="mt-2 text-xs text-muted-foreground">
        {t("chat.videoStoryboard.previewError")}
      </p>
    )
  }
  return (
    <div className="mt-2 max-w-lg">
      <div className="relative" data-preview-slot={slotId}>
        {!expanded && <RemotionPreviewAdapter spec={spec} onReady={onReady} onError={handleError} />}
        {expanded && <div style={{ aspectRatio: spec.width / spec.height }} />}
        {onOpenPreview && <IconButton
          variant="secondary"
          icon={<Maximize2 />}
          style={{ position: "absolute", top: 8, right: 8 }}
          label={t("common.preview")}
          onClick={() => onOpenPreview({ id: identity.composition_version_id, slotId, spec })}
        />}
      </div>
    </div>
  )
}
