/** User message — the only bubbled element in the flow (rounded, muted).
 * An attachment-only message (files dropped into the chat) skips the text
 * bubble and shows just the chips. */

import { useTranslation } from "react-i18next"
import {
  FileText,
  Image as ImageIcon,
  Mic2,
  Video,
} from "lucide-react"

import { Card, CardHeader } from "@/components/ui/card-clean"
import { SkillChip } from "@/components/composer/SkillChip"
import type { SkillOption } from "@/lib/skills"
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
}: {
  text: string
  assets?: ProjectAsset[]
  skill?: SkillOption
}) {
  const { t } = useTranslation()
  return (
    <div className="ui-th-user">
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
    </div>
  )
}
