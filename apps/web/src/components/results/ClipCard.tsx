"use client"

import { useEffect, useRef, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Play } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Card } from "@/components/ui/card"
import { apiPost, downloadFile, toAbsoluteUrl } from "@/lib/api"
import { formatDuration, cn } from "@/lib/utils"

import { AssetActionBar } from "./AssetActionBar"
import { AssetChatModal } from "./AssetChatModal"
import { ClipDetailModal } from "./ClipDetailModal"
import { PublishDialog } from "@/components/publish/PublishDialog"

import type { Output } from "@/lib/types"

interface ClipCardProps {
  output: Output
  onRegenerate?: () => void
  isTopPick?: boolean
}

export function ClipCard({ output, onRegenerate, isTopPick }: ClipCardProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [chatOpen, setChatOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [clipState, setClipState] = useState<Output>(output)
  const [isRendering, setIsRendering] = useState(
    output.render_status === "pending" || output.render_status === "rendering"
  )
  const [renderError, setRenderError] = useState<string | null>(output.render_error)
  const [isPlaying, setIsPlaying] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)

  // Keep local state in sync if the parent re-renders with updated data.
  useEffect(() => {
    setClipState(output)
    setRenderError(output.render_error)
    setIsRendering(
      output.render_status === "pending" || output.render_status === "rendering"
    )
  }, [output])

  useEffect(() => {
    if (isPlaying && videoRef.current) {
      videoRef.current.play().catch(() => {
        // Autoplay blocked; keep controls visible so the user can start playback.
      })
    }
  }, [isPlaying])

  const videoUrl = clipState.files.video ?? null
  const title = clipState.publishing.title || clipState.payload.hook || ""
  const coverUrl = clipState.publishing.cover_image_url ?? null

  const handleDownload = () => {
    if (!videoUrl) return
    const filename = `${title || "clip"}.mp4`
    downloadFile(videoUrl, filename).catch((e) =>
      console.error("Download failed", e)
    )
  }

  const handleRegenerate = async () => {
    try {
      await apiPost(`/api/v1/outputs/${clipState.id}/regenerate`, {
        instruction: "Regenerate this clip",
      })
      onRegenerate?.()
    } catch (e) {
      console.error("Regenerate failed", e)
    }
  }

  const handleRender = async () => {
    setRenderError(null)
    setIsRendering(true)
    try {
      const res = await apiPost(`/api/v1/outputs/${clipState.id}/render`, {})
      if (!res.ok) {
        const detail = await res.json().catch(() => null)
        throw new Error(detail?.detail || "Render failed")
      }
      const updated: Output = await res.json()
      setClipState(updated)
    } catch (e) {
      setIsRendering(false)
      setRenderError(e instanceof Error ? e.message : "Render failed")
    }
  }

  const handleEdit = () => {
    navigate({
      to: "/projects/$id/clips/$clipId",
      params: { id: clipState.project_id, clipId: clipState.id },
    })
  }

  const thumbnailUrl = coverUrl
    ? toAbsoluteUrl(coverUrl)
    : videoUrl
      ? toAbsoluteUrl(videoUrl)
      : null

  return (
    <>
      <Card className="group flex flex-col gap-0 overflow-hidden ring-1 ring-border">
        {/* Thumbnail / player */}
        <div
          className={cn(
            "relative aspect-square w-full overflow-hidden bg-muted",
            !isRendering && "cursor-pointer"
          )}
          onClick={(e) => {
            if (isRendering) return
            const target = e.target as HTMLElement
            if (target.closest("[data-play-trigger]")) return
            if (!isPlaying) setDetailOpen(true)
          }}
        >
          {isRendering ? (
            <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-6 text-center">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
              <p className="text-sm text-muted-foreground">{t("chat.rendering")}</p>
            </div>
          ) : isPlaying && videoUrl ? (
            <video
              ref={videoRef}
              src={toAbsoluteUrl(videoUrl) || undefined}
              className="h-full w-full object-contain"
              controls
              autoPlay
              playsInline
              onEnded={() => setIsPlaying(false)}
              onPause={() => setIsPlaying(false)}
              onPlay={() => setIsPlaying(true)}
            />
          ) : thumbnailUrl ? (
            <>
              {coverUrl ? (
                <img
                  src={thumbnailUrl || undefined}
                  alt={title}
                  className="h-full w-full object-contain transition-transform group-hover:scale-105"
                />
              ) : (
                <video
                  src={thumbnailUrl || undefined}
                  className="h-full w-full object-contain transition-transform group-hover:scale-105"
                  preload="metadata"
                  muted
                />
              )}
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/20" />
              {typeof clipState.score?.value === "number" && (
                <div
                  className={cn(
                    "absolute left-2 top-2 z-20 rounded px-1.5 py-0.5 text-[10px] font-medium",
                    isTopPick
                      ? "bg-primary text-primary-foreground"
                      : "bg-black/70 text-white"
                  )}
                  title={clipState.score.reason ?? undefined}
                >
                  {isTopPick
                    ? `${t("results.topPick")} · ${clipState.score.value}`
                    : clipState.score.value}
                </div>
              )}
              <div className="absolute right-2 top-2 z-20 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
                {formatDuration(clipState.payload.duration ?? 0)}
              </div>
              <button
                type="button"
                data-play-trigger
                onClick={(e) => {
                  e.stopPropagation()
                  if (videoUrl) {
                    setIsPlaying(true)
                  } else {
                    handleRender()
                  }
                }}
                disabled={isRendering}
                className="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2"
              >
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-background/90 text-foreground opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                  {isRendering ? (
                    <span className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <Play className="h-5 w-5 fill-current" />
                  )}
                </span>
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                handleRender()
              }}
              disabled={isRendering}
              className="flex h-full w-full flex-col items-center justify-center gap-3 p-6 text-center transition-colors hover:bg-accent/50 disabled:cursor-not-allowed"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border">
                {isRendering ? (
                  <span className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                ) : (
                  <Play className="h-5 w-5 text-muted-foreground" />
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                {isRendering
                  ? t("chat.rendering")
                  : renderError
                    ? t("projectDetail.renderFailed")
                    : t("results.clipNotRendered")}
              </p>
            </button>
          )}
        </div>

        {/* Info */}
        <div className="flex flex-1 flex-col justify-between p-3">
          <div className="space-y-1">
            <h3 className="line-clamp-2 text-sm font-medium">
              {title}
            </h3>
          </div>

          <div className="mt-2">
            {!isRendering && (
              <AssetActionBar
                onEdit={handleEdit}
                onDownload={videoUrl ? handleDownload : undefined}
                onRegenerate={handleRegenerate}
                onChat={() => setChatOpen(true)}
                onPublish={videoUrl ? () => setPublishOpen(true) : undefined}
              />
            )}
          </div>
        </div>
      </Card>

      <AssetChatModal
        open={chatOpen}
        onOpenChange={setChatOpen}
        asset={clipState}
        assetType="clip"
        projectId={clipState.project_id}
        onUpdated={onRegenerate}
      />

      <ClipDetailModal
        output={clipState}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onRegenerate={onRegenerate}
      />

      <PublishDialog
        output={clipState}
        open={publishOpen}
        onOpenChange={setPublishOpen}
      />
    </>
  )
}
