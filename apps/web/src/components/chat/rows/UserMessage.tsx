/** User message — the only bubbled element in the flow (rounded, muted).
 * An attachment-only message (files dropped into the chat) skips the text
 * bubble and shows just the chips. */

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  Check,
  Copy,
  FileText,
  Image as ImageIcon,
  Mic2,
  Undo2,
  Video,
} from "@/components/ui/icons"

import { Card, CardHeader } from "@/components/ui/card-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Tooltip } from "@/components/ui/tooltip-clean"
import { SkillChip } from "@/components/composer/SkillChip"
import type { SkillOption } from "@/lib/skills"
import { cn } from "@/lib/utils"
import { formatRelativeTime } from "@/lib/workbench"
import type { ProjectAsset } from "../timeline/types"

export function assetTypeIcon(type: string) {
  switch (type) {
    case "video":
      return Video
    case "audio":
      return Mic2
    case "image":
    case "slides":
      return ImageIcon
    default:
      return FileText
  }
}

function assetFilename(fileUrl: string | null): string {
  if (!fileUrl) return ""
  return fileUrl.split("/").pop() || fileUrl
}

export function UserBubble({
  text,
  assets,
  skill,
  createdAt,
  onUndo,
}: {
  text: string
  assets?: ProjectAsset[]
  skill?: SkillOption
  createdAt?: string
  onUndo?: () => void
}) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const copyTimerRef = useRef<number | null>(null)
  const [nowMs, setNowMs] = useState<number | null>(null)

  useEffect(() => {
    if (!createdAt) return
    setNowMs(Date.now())
    const timer = window.setInterval(() => {
      setNowMs(Date.now())
    }, 30_000)
    return () => window.clearInterval(timer)
  }, [createdAt])

  useEffect(() => {
    return () => {
      if (copyTimerRef.current != null) window.clearTimeout(copyTimerRef.current)
    }
  }, [])

  const handleCopy = useCallback(async () => {
    if (!text.trim()) return
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      toast.success(t("chat.feedback.copied"))
      if (copyTimerRef.current != null) window.clearTimeout(copyTimerRef.current)
      copyTimerRef.current = window.setTimeout(() => setCopied(false), 1800)
    } catch {
      toast.error(t("common.requestFailed"))
    }
  }, [text, t])

  const relativeTime =
    createdAt && nowMs != null ? formatRelativeTime(createdAt, t, nowMs) : ""
  const exactTime = createdAt
    ? (() => {
        const parsed = Date.parse(createdAt)
        return Number.isNaN(parsed) ? undefined : new Date(parsed).toLocaleString()
      })()
    : undefined
  const showActionRow = Boolean(relativeTime || text.trim())

  return (
    <div className="ui-th-user group/user-msg">
      {(text || skill) && (
        <p className="ui-th-user__bubble" dir="auto">
          {skill && <SkillChip option={skill} className="mr-1 align-middle" />}
          {text}
        </p>
      )}
      {assets?.map((asset) => {
        const mediaUrl = asset.stream_url ?? (asset.file_url?.startsWith("http") ? asset.file_url : null)
        if (asset.type === "video") {
          return mediaUrl && <video key={asset.id} className="max-h-80 w-56 max-w-full rounded-lg" src={mediaUrl} controls playsInline preload="metadata" />
        }
        if (asset.type === "image") {
          return mediaUrl && <img key={asset.id} className="max-h-80 max-w-full rounded-lg object-contain" width={288} src={mediaUrl} alt={asset.title ?? ""} />
        }
        return null
      })}
      {assets?.some((asset) => asset.type !== "video" && asset.type !== "image") && (
        <ul className="ui-th-user__files">
          {assets.filter((asset) => asset.type !== "video" && asset.type !== "image").map((asset) => {
            const Icon = assetTypeIcon(asset.type)
            const typeLabel = t(`generationOverlay.assetTypes.${asset.type}`, { defaultValue: asset.type })
            return (
              <Card as="li" key={asset.id}>
                <CardHeader
                  titleAs="p"
                  title={asset.title || assetFilename(asset.file_url) || typeLabel}
                  description={asset.processing_status === "failed" ? t("chat.failed") : typeLabel}
                  icon={<Icon />}
                />
              </Card>
            )
          })}
        </ul>
      )}
      {showActionRow ? (
        <div
          data-slot="user-message-action-bar"
          className={cn(
            "flex items-center justify-end gap-0.5 text-muted-foreground transition-opacity duration-150",
            !copied &&
              "opacity-0 group-hover/user-msg:opacity-100 group-has-[:focus-visible]/user-msg:opacity-100",
          )}
        >
          {relativeTime ? (
            <span
              className="mr-1 select-none text-[11px] tabular-nums text-muted-foreground/75"
              title={exactTime}
            >
              {relativeTime}
            </span>
          ) : null}
          {text.trim() ? (
            <Tooltip content={copied ? t("chat.feedback.copied") : t("chat.userActions.copy")} side="bottom">
              <IconButton
                size="sm"
                variant="ghost"
                icon={copied ? <Check className="size-3.5 text-foreground" /> : <Copy className="size-3.5" />}
                label={copied ? t("chat.feedback.copied") : t("chat.userActions.copy")}
                onClick={() => { void handleCopy() }}
              />
            </Tooltip>
          ) : null}
          <Tooltip
            content={onUndo ? t("chat.userActions.undo") : t("chat.userActions.undoSoon")}
            side="bottom"
          >
            <span className="inline-flex">
              <IconButton
                size="sm"
                variant="ghost"
                disabled={!onUndo}
                icon={<Undo2 className="size-3.5" />}
                label={onUndo ? t("chat.userActions.undo") : t("chat.userActions.undoSoon")}
                onClick={onUndo}
              />
            </span>
          </Tooltip>
        </div>
      ) : null}
    </div>
  )
}
