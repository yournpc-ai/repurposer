"use client"

import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Copy, Download, Edit, ImageIcon, Play } from "lucide-react"
import { Link } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { apiPost, downloadFile, toAbsoluteUrl } from "@/lib/api"
import { formatDuration, cn } from "@/lib/utils"

import type { Output } from "@/lib/types"

interface ClipDetailModalProps {
  output: Output
  open: boolean
  onOpenChange: (open: boolean) => void
  onRegenerate?: () => void
}

export function ClipDetailModal({
  output,
  open,
  onOpenChange,
  onRegenerate,
}: ClipDetailModalProps) {
  const { t } = useTranslation()
  const [clipState, setClipState] = useState<Output>(output)
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  // Keep modal state in sync when the parent re-renders with updated clip data
  // (e.g., render completion, chat edits).
  useEffect(() => {
    setClipState(output)
  }, [output])

  const videoUrl = clipState.files.video ?? null
  const title = clipState.publishing.title || clipState.payload.hook || ""
  const description = clipState.publishing.description ?? null
  const hashtags = clipState.publishing.hashtags ?? []
  const topic = clipState.publishing.topic ?? null
  const coverUrl = clipState.publishing.cover_image_url ?? null
  const duration = clipState.payload.duration ?? 0
  const startTime = clipState.source_ref?.start_seconds ?? null
  const endTime = clipState.source_ref?.end_seconds ?? null

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedKey(key)
      setTimeout(() => setCopiedKey(null), 1500)
    })
  }

  const handleDownload = () => {
    if (!videoUrl) return
    const filename = `${title || "clip"}.mp4`
    downloadFile(videoUrl, filename).catch((e) =>
      console.error("Download failed", e)
    )
  }

  const handleGenerateCover = async () => {
    try {
      const res = await apiPost(`/api/v1/outputs/${clipState.id}/cover`, {})
      if (!res.ok) throw new Error("Cover generation failed")
      const updated: Output = await res.json()
      setClipState(updated)
      onRegenerate?.()
    } catch (e) {
      console.error("Cover generation failed", e)
    }
  }

  const formatTime = (seconds: number | null) => formatDuration(seconds, "")

  const aspect =
    (clipState.render_spec as { aspect?: string } | null)?.aspect || "9:16"
  const isLandscape = aspect === "16:9"
  const aspectRatio =
    aspect === "1:1" ? "1 / 1" : aspect === "16:9" ? "16 / 9" : "9 / 16"

  const transcript =
    (clipState.render_spec as { caption_track?: { start: number; end: number; text: string }[] } | null)
      ?.caption_track || []

  // Word-level captions are grouped into sentence-level lines for readable transcript browsing.
  const transcriptLines = transcript.reduce<
    { start: number; end: number; text: string }[]
  >((lines, cue) => {
    const text = cue.text.trim()
    if (!text) return lines

    const last = lines[lines.length - 1]
    const endsSentence = /[.!?。！？]$/.test(text)

    if (!last || endsSentence || last.text.length > 120) {
      lines.push({ start: cue.start, end: cue.end, text })
    } else {
      last.end = cue.end
      last.text += ` ${text}`
    }

    return lines
  }, [])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[calc(100%-2rem)] overflow-hidden p-0 sm:max-w-3xl"
        style={{ width: "auto" }}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <div
          className={`flex max-h-[85vh] ${
            isLandscape ? "flex-col" : "flex-col md:flex-row"
          }`}
        >
          {/* Video player */}
          <div
            className={cn(
              "relative overflow-hidden bg-muted",
              isLandscape
                ? "w-full"
                : "w-full md:w-auto md:max-h-[75vh]",
              aspect === "1:1" && "md:max-h-[55vh]"
            )}
            style={{ aspectRatio: aspectRatio }}
          >
            {videoUrl ? (
              <video
                src={toAbsoluteUrl(videoUrl) || undefined}
                className="h-full w-full object-contain"
                controls
                playsInline
                preload="metadata"
                poster={coverUrl ? toAbsoluteUrl(coverUrl) || undefined : undefined}
              />
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-muted-foreground">
                <Play className="h-10 w-10" />
                <p className="text-sm">{t("results.clipNotRendered")}</p>
              </div>
            )}
          </div>

          {/* Info panel */}
          <div
            className={cn(
              "flex min-w-0 flex-col gap-4 overflow-y-auto p-5",
              isLandscape
                ? "w-full"
                : "w-full md:w-[320px] lg:w-[360px]"
            )}
          >
            {/* Meta header */}
            <div className="flex flex-col gap-1">
              <h2 className="text-lg font-medium leading-tight">{title}</h2>
              <span className="text-xs text-muted-foreground">
                {formatTime(startTime)} - {formatTime(endTime)}
                {duration > 0 && ` · ${duration}s`}
              </span>
            </div>

            {/* Recommendation score + reason */}
            {typeof clipState.score?.value === "number" && (
              <div className="flex flex-col gap-1 rounded-md bg-muted p-3">
                <span className="text-xs font-medium">
                  {t("results.scoreLabel")} · {clipState.score.value}
                </span>
                {clipState.score.reason && (
                  <p className="text-xs text-muted-foreground">
                    {t("results.scoreReason")}: {clipState.score.reason}
                  </p>
                )}
              </div>
            )}

            <Tabs defaultValue="social" className="w-full">
              <TabsList variant="line" className="w-full">
                <TabsTrigger value="social">{t("results.clipDetail.socialCaptionTab")}</TabsTrigger>
                <TabsTrigger value="topic">Topic</TabsTrigger>
                <TabsTrigger value="transcript">{t("results.clipDetail.transcriptTab")}</TabsTrigger>
              </TabsList>

              <TabsContent value="social" className="space-y-4 pt-3">
                <CopyField
                  label={t("results.clipDetail.title")}
                  value={clipState.publishing.title || ""}
                  copied={copiedKey === "title"}
                  onCopy={() => handleCopy(clipState.publishing.title || "", "title")}
                />
                <CopyField
                  label={t("results.clipDetail.caption")}
                  value={description || ""}
                  copied={copiedKey === "caption"}
                  onCopy={() => handleCopy(description || "", "caption")}
                />
                <CopyField
                  label={t("results.clipDetail.hashtags")}
                  value={hashtags.map((h) => `#${h}`).join(" ")}
                  copied={copiedKey === "hashtags"}
                  onCopy={() =>
                    handleCopy(hashtags.map((h) => `#${h}`).join(" "), "hashtags")
                  }
                />
              </TabsContent>

              <TabsContent value="topic" className="pt-3">
                {topic ? (
                  <p className="text-sm leading-relaxed text-foreground">{topic}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">No topic available.</p>
                )}
              </TabsContent>

              <TabsContent value="transcript" className="pt-3">
                {transcriptLines.length > 0 ? (
                  <div className="max-h-52 space-y-2 overflow-y-auto pr-2">
                    {transcriptLines.map((line, i) => (
                      <div key={i} className="flex items-baseline gap-3 text-sm">
                        <span className="shrink-0 pt-0.5 text-xs text-muted-foreground">
                          {formatTime(line.start)} - {formatTime(line.end)}
                        </span>
                        <p className="leading-relaxed">{line.text}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">{t("results.clipDetail.noTranscript")}</p>
                )}
              </TabsContent>
            </Tabs>

            <div className="mt-auto flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-9"
                onClick={handleDownload}
                disabled={!videoUrl}
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
              {!coverUrl && (
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
