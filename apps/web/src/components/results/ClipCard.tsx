import { useEffect, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Play } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiFetch, apiPost, toAbsoluteUrl } from "@/lib/api"

import { AssetActionBar } from "./AssetActionBar"
import { AssetChatModal } from "./AssetChatModal"

import type { Clip } from "@/lib/types"

interface ClipCardProps {
  clip: Clip
  onRegenerate?: () => void
}

export function ClipCard({ clip, onRegenerate }: ClipCardProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [chatOpen, setChatOpen] = useState(false)
  const [clipState, setClipState] = useState<Clip>(clip)
  const [isRendering, setIsRendering] = useState(
    clip.render_status === "pending" || clip.render_status === "rendering"
  )
  const [renderError, setRenderError] = useState<string | null>(clip.render_error)

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

  // Poll render status after the user queues a render.
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
    a.download = `${clipState.hook || "clip"}.mp4`
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

  return (
    <Card className="flex h-full overflow-hidden ring-1 ring-border shadow-xl">
      <div className="relative aspect-[9/16] overflow-hidden bg-muted">
        {clipState.video_url ? (
          <video
            src={toAbsoluteUrl(clipState.video_url) || undefined}
            className="absolute inset-0 h-full w-full object-cover"
            controls
            playsInline
            preload="metadata"
          />
        ) : (
          <button
            type="button"
            onClick={handleRender}
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

      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="font-medium">{clipState.hook}</h3>
            <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span>{clipState.duration}s</span>
              <span>·</span>
              <span>{clipState.music_mood}</span>
            </div>
          </div>
          <AssetActionBar
            onEdit={handleEdit}
            onDownload={clipState.video_url ? handleDownload : undefined}
            onRegenerate={handleRegenerate}
            onChat={() => setChatOpen(true)}
          />
        </div>

        {clipState.title_options.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {clipState.title_options.map((title, i) => (
              <Badge key={i} variant="secondary">
                {title}
              </Badge>
            ))}
          </div>
        )}
      </div>

      <AssetChatModal
        open={chatOpen}
        onOpenChange={setChatOpen}
        asset={clipState}
        assetType="clip"
        projectId={clipState.project_id}
        onUpdated={onRegenerate}
      />
    </Card>
  )
}
