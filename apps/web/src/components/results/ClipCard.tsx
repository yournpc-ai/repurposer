"use client"

import { useEffect, useRef, useState } from "react"
import {
  Download,
  MoreHorizontal,
  Play,
  Send,
  Share2,
  MessageSquare,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { BrandLoader } from "@/components/BrandLoader"
import { ProcessingTile } from "@/components/ProcessingTile"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { apiPost, downloadFile, toAbsoluteUrl } from "@/lib/api"
import { formatDuration, formatRelativeTime, cn } from "@/lib/utils"

import { AssetChatModal } from "./AssetChatModal"
import { ClipDetailModal } from "./ClipDetailModal"
import { PublishDialog } from "@/components/publish/PublishDialog"

import type { Output } from "@/lib/types"

interface ClipCardProps {
  output: Output
  onRegenerate?: () => void
  isTopPick?: boolean
  /** Puts the results tour's data-tour anchors on this card (first ready clip only). */
  tourTargets?: boolean
}

export function ClipCard({ output, onRegenerate, isTopPick, tourTargets }: ClipCardProps) {
  const { t, i18n } = useTranslation()
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

  const handleShare = async () => {
    const url = toAbsoluteUrl(videoUrl)
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      toast.success(t("clipMenu.shareCopied"))
    } catch {
      toast.error(t("chat.failed"))
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

  const thumbnailUrl = coverUrl
    ? toAbsoluteUrl(coverUrl)
    : videoUrl
      ? toAbsoluteUrl(videoUrl)
      : null

  return (
    <>
      <Card className="group flex flex-col gap-0 overflow-hidden shadow-lg">
        {/* Thumbnail / player */}
        <div
          data-tour={tourTargets ? "results-video" : undefined}
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
            <div className="relative h-full w-full p-6 text-center">
              <ProcessingTile>
                <BrandLoader className="relative h-10 w-10" />
                <p className="relative text-sm text-muted-foreground">{t("chat.rendering")}</p>
              </ProcessingTile>
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
                  data-tour={tourTargets ? "results-score" : undefined}
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
                  <Play className="h-5 w-5 fill-current" />
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
                <Play className="h-5 w-5 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">
                {renderError
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

          {/* Bottom row: creation date on the left (Opus's "Expires" slot),
              "···" menu on the right. The editor entry is intentionally
              hidden — remix goes through chat. */}
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="truncate text-xs text-muted-foreground">
              {formatRelativeTime(clipState.created_at, i18n.language)}
            </span>
            {!isRendering && (
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("clipMenu.more")}
                      data-tour={tourTargets ? "results-menu" : undefined}
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  }
                />
                <DropdownMenuContent align="end" className="w-52">
                  <DropdownMenuGroup>
                    {videoUrl && (
                      <DropdownMenuItem onClick={handleDownload}>
                        <Download className="mr-2 h-4 w-4" />
                        {t("clipMenu.download")}
                      </DropdownMenuItem>
                    )}
                    {videoUrl && (
                      <DropdownMenuItem onClick={() => setPublishOpen(true)}>
                        <Send className="mr-2 h-4 w-4" />
                        {t("clipMenu.publishOnSocial")}
                      </DropdownMenuItem>
                    )}
                    {videoUrl && (
                      <DropdownMenuItem onClick={handleShare}>
                        <Share2 className="mr-2 h-4 w-4" />
                        {t("clipMenu.share")}
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={() => setChatOpen(true)}>
                      <MessageSquare className="mr-2 h-4 w-4" />
                      {t("clipMenu.remix")}
                    </DropdownMenuItem>
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>
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
      />

      <PublishDialog
        output={clipState}
        open={publishOpen}
        onOpenChange={setPublishOpen}
      />
    </>
  )
}
