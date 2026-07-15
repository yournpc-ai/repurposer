"use client"

import { useEffect, useRef, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Play } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiFetch, apiPost, toAbsoluteUrl } from "@/lib/api"
import { formatDuration } from "@/lib/utils"

import { AssetActionBar } from "./AssetActionBar"
import { AssetChatModal } from "./AssetChatModal"
import { ClipDetailModal } from "./ClipDetailModal"

import type { Clip } from "@/lib/types"

interface ClipCardProps {
  clip: Clip
  onRegenerate?: () => void
}

export function ClipCard({ clip, onRegenerate }: ClipCardProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [chatOpen, setChatOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [clipState, setClipState] = useState<Clip>(clip)
  const [isRendering, setIsRendering] = useState(
    clip.render_status === "pending" || clip.render_status === "rendering"
  )
  const [renderError, setRenderError] = useState<string | null>(clip.render_error)
  const [isPlaying, setIsPlaying] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)

  // Keep local state in sync if the parent re-renders with updated data.
  useEffect(() => {
    setClipState(clip)
    setRenderError(clip.render_error)
    if (!isRendering) {
      setIsRendering(
        clip.render_status === "pending" || clip.render_status === "rendering"
      )
    }
  }, [clip, isRendering])

  useEffect(() => {
    if (isPlaying && videoRef.current) {
      videoRef.current.play().catch(() => {
        // Autoplay blocked; keep controls visible so the user can start playback.
      })
    }
  }, [isPlaying])
  useEffect(() => {
    if (!isRendering) return

    const poll = async () => {
      try {
        const res = await apiFetch(`/api/v1/clips/${clipState.id}`)
        if (!res.ok) return
        const updated: Clip = await res.json()
        setClipState(updated)
        if (updated.video_url || updated.render_status === "failed") {
          setIsRendering(false)
        }
        if (updated.render_error) {
          setRenderError(updated.render_error)
        }
      } catch {
        // Ignore polling errors; the user can retry.
      }
    }

    poll()
    const interval = setInterval(poll, 2500)
    return () => clearInterval(interval)
  }, [isRendering, clipState.id])

  const handleDownload = () => {
    const url = toAbsoluteUrl(clipState.video_url)
    if (!url) return
    const a = document.createElement("a")
    a.href = url
    a.download = `${clipState.title || clipState.hook || "clip"}.mp4`
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  const handleRegenerate = async () => {
    try {
      await apiPost(`/api/v1/clips/${clipState.id}/regenerate`, {
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
      const res = await apiPost(`/api/v1/clips/${clipState.id}/render`, {})
      if (!res.ok) {
        const detail = await res.json().catch(() => null)
        throw new Error(detail?.detail || "Render failed")
      }
      const updated: Clip = await res.json()
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

  const thumbnailUrl = clipState.cover_image_url
    ? toAbsoluteUrl(clipState.cover_image_url)
    : clipState.video_url
      ? toAbsoluteUrl(clipState.video_url)
      : null

  return (
    <>
      <Card className="group flex flex-col overflow-hidden ring-1 ring-border shadow-xl">
        {/* Thumbnail / player */}
        <div
          className="relative aspect-square w-full cursor-pointer overflow-hidden bg-muted"
          onClick={(e) => {
            const target = e.target as HTMLElement
            if (target.closest("[data-play-trigger]")) return
            if (!isPlaying) setDetailOpen(true)
          }}
        >
          {isPlaying && clipState.video_url ? (
            <video
              ref={videoRef}
              src={toAbsoluteUrl(clipState.video_url) || undefined}
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
              {clipState.cover_image_url ? (
                <img
                  src={thumbnailUrl || undefined}
                  alt={clipState.title || clipState.hook}
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
              <div className="absolute right-2 top-2 z-20 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
                {formatDuration(clipState.duration)}
              </div>
              <button
                type="button"
                data-play-trigger
                onClick={(e) => {
                  e.stopPropagation()
                  if (clipState.video_url) {
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
            {clipState.topic ? (
              <Badge variant="secondary" className="text-[10px]">{clipState.topic}</Badge>
            ) : (
              <Badge variant="outline" className="text-[10px]">{clipState.music_mood}</Badge>
            )}
            <h3 className="line-clamp-2 text-sm font-medium">
              {clipState.title || clipState.hook}
            </h3>
          </div>

          <div className="mt-2">
            <AssetActionBar
              onEdit={handleEdit}
              onDownload={clipState.video_url ? handleDownload : undefined}
              onRegenerate={handleRegenerate}
              onChat={() => setChatOpen(true)}
            />
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
        clip={clipState}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onRegenerate={onRegenerate}
      />
    </>
  )
}
