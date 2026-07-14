"use client"

import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Copy, Download, Edit, ImageIcon, Play } from "lucide-react"
import { Link } from "@tanstack/react-router"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { apiPost, toAbsoluteUrl } from "@/lib/api"
import { formatDuration } from "@/lib/utils"

import type { Clip } from "@/lib/types"

interface ClipDetailModalProps {
  clip: Clip
  open: boolean
  onOpenChange: (open: boolean) => void
  onRegenerate?: () => void
}

export function ClipDetailModal({
  clip,
  open,
  onOpenChange,
  onRegenerate,
}: ClipDetailModalProps) {
  const { t } = useTranslation()
  const [clipState, setClipState] = useState<Clip>(clip)
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  // Keep modal state in sync when the parent re-renders with updated clip data
  // (e.g., render completion, chat edits).
  useEffect(() => {
    setClipState(clip)
  }, [clip])

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedKey(key)
      setTimeout(() => setCopiedKey(null), 1500)
    })
  }

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

  const handleGenerateCover = async () => {
    try {
      const res = await apiPost(`/api/v1/clips/${clipState.id}/cover`, {})
      if (!res.ok) throw new Error("Cover generation failed")
      const updated: Clip = await res.json()
      setClipState(updated)
      onRegenerate?.()
    } catch (e) {
      console.error("Cover generation failed", e)
    }
  }

  const formatTime = (seconds: number | null) => formatDuration(seconds, "")

  const transcript =
    (clipState.render_spec as { caption_track?: { start: number; end: number; text: string }[] } | null)
      ?.caption_track || []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl p-0">
        <DialogHeader className="sr-only">
          <DialogTitle>{clipState.title || clipState.hook}</DialogTitle>
        </DialogHeader>

        {/* Video player */}
        <div className="relative aspect-video w-full overflow-hidden rounded-t-lg bg-muted">
          {clipState.video_url ? (
            <video
              src={toAbsoluteUrl(clipState.video_url) || undefined}
              className="h-full w-full object-contain"
              controls
              playsInline
              preload="metadata"
              poster={clipState.cover_image_url ? toAbsoluteUrl(clipState.cover_image_url) || undefined : undefined}
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-muted-foreground">
              <Play className="h-10 w-10" />
              <p className="text-sm">{t("results.clipNotRendered")}</p>
            </div>
          )}
        </div>

        <div className="space-y-4 p-5">
          {/* Meta header */}
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1 space-y-1">
              {clipState.topic && (
                <Badge variant="secondary" className="text-xs">{clipState.topic}</Badge>
              )}
              <h2 className="text-lg font-medium">{clipState.title || clipState.hook}</h2>
            </div>
            <span className="shrink-0 text-sm text-muted-foreground">
              {formatTime(clipState.start_time)} - {formatTime(clipState.end_time)}
              {clipState.duration > 0 && ` · ${clipState.duration}s`}
            </span>
          </div>

          <Tabs defaultValue="publish">
            <TabsList variant="line" className="w-full">
              <TabsTrigger value="publish">{t("results.clipDetail.publishTab")}</TabsTrigger>
              <TabsTrigger value="transcript">{t("results.clipDetail.transcriptTab")}</TabsTrigger>
            </TabsList>

            <TabsContent value="publish" className="space-y-4 pt-2">
              <CopyField
                label={t("results.clipDetail.title")}
                value={clipState.title || ""}
                copied={copiedKey === "title"}
                onCopy={() => handleCopy(clipState.title || "", "title")}
              />
              <CopyField
                label={t("results.clipDetail.caption")}
                value={clipState.description || ""}
                copied={copiedKey === "caption"}
                onCopy={() => handleCopy(clipState.description || "", "caption")}
              />
              <CopyField
                label={t("results.clipDetail.hashtags")}
                value={(clipState.hashtags || []).map((h) => `#${h}`).join(" ")}
                copied={copiedKey === "hashtags"}
                onCopy={() =>
                  handleCopy((clipState.hashtags || []).map((h) => `#${h}`).join(" "), "hashtags")
                }
              />
            </TabsContent>

            <TabsContent value="transcript" className="pt-2">
              {transcript.length > 0 ? (
                <div className="max-h-60 space-y-2 overflow-y-auto pr-2">
                  {transcript.map((cue, i) => (
                    <div key={i} className="flex gap-3 text-sm">
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {formatTime(cue.start)}
                      </span>
                      <p className="leading-relaxed">{cue.text}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">{t("results.clipDetail.noTranscript")}</p>
              )}
            </TabsContent>
          </Tabs>

          <Separator />

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-9"
              onClick={handleDownload}
              disabled={!clipState.video_url}
            >
              <Download className="mr-2 h-4 w-4" />
              {t("results.clipDetail.download")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-9"
              render={
                <Link
                  to="/projects/$id/clips/$clipId"
                  params={{ id: clipState.project_id, clipId: clipState.id }}
                />
              }
            >
              <Edit className="mr-2 h-4 w-4" />
              {t("results.clipDetail.editClip")}
            </Button>
            {!clipState.cover_image_url && (
              <Button
                variant="outline"
                size="sm"
                className="h-9"
                onClick={handleGenerateCover}
              >
                <ImageIcon className="mr-2 h-4 w-4" />
                {t("results.clipDetail.generateCover")}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function CopyField({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string
  value: string
  copied: boolean
  onCopy: () => void
}) {
  const { t } = useTranslation()
  if (!value) return null
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs" onClick={onCopy}>
          <Copy className="h-3.5 w-3.5" />
          {copied ? t("chat.copied") : t("chat.copy")}
        </Button>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{value}</p>
    </div>
  )
}
