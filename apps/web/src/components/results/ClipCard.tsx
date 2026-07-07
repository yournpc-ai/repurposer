import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Play } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { apiPost, toAbsoluteUrl } from "@/lib/api"

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

  const handleDownload = () => {
    const url = toAbsoluteUrl(clip.video_url)
    if (!url) return
    const a = document.createElement("a")
    a.href = url
    a.download = `${clip.hook || "clip"}.mp4`
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  const handleRegenerate = async () => {
    try {
      await apiPost(`/api/v1/clips/${clip.id}/regenerate`, {
        instruction: "Regenerate this clip",
      })
      onRegenerate?.()
    } catch (e) {
      console.error("Regenerate failed", e)
    }
  }

  const handleEdit = () => {
    navigate({
      to: "/projects/$id/clips/$clipId",
      params: { id: clip.project_id, clipId: clip.id },
    })
  }

  return (
    <Card className="overflow-hidden ring-1 ring-border shadow-xl">
      <div className="relative aspect-[9/16] bg-muted">
        {clip.video_url ? (
          <video
            src={toAbsoluteUrl(clip.video_url) || undefined}
            className="h-full w-full object-cover"
            controls
            preload="metadata"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border">
              <Play className="h-5 w-5 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">
              {t("results.clipNotRendered")}
            </p>
          </div>
        )}
      </div>

      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="font-medium">{clip.hook}</h3>
            <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span>{clip.duration}s</span>
              <span>·</span>
              <span>{clip.music_mood}</span>
            </div>
          </div>
          <AssetActionBar
            onEdit={handleEdit}
            onDownload={clip.video_url ? handleDownload : undefined}
            onRegenerate={handleRegenerate}
            onChat={() => setChatOpen(true)}
          />
        </div>

        {clip.title_options.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {clip.title_options.map((title, i) => (
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
        asset={clip}
        assetType="clip"
        projectId={clip.project_id}
        onUpdated={onRegenerate}
      />
    </Card>
  )
}
