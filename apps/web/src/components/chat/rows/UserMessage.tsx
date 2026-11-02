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

import {
  Attachment,
  AttachmentContent,
  AttachmentDescription,
  AttachmentGroup,
  AttachmentMedia,
  AttachmentTitle,
} from "@/components/ui/attachment"
import { Bubble, BubbleContent, BubbleGroup } from "@/components/ui/bubble"
import { Message, MessageContent } from "@/components/ui/message"
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
    <Message align="end">
      <MessageContent>
        {text || skill ? (
          <BubbleGroup>
            <Bubble variant="muted" align="end">
              <BubbleContent className="rounded-2xl px-4 py-2 text-sm">
                <p className="whitespace-pre-wrap">
                  {skill ? <SkillChip option={skill} className="mr-1 align-middle" /> : null}
                  {text}
                </p>
              </BubbleContent>
            </Bubble>
          </BubbleGroup>
        ) : null}
        {assets && assets.length > 0 ? (
          <>
            {/* Media assets ride as MEDIA messages (2026-09-25 用户拍板,
                the shadcn message-attachment composition): Attachment
                vertical + AttachmentMedia "media" — a video plays inline
                (native controls, natural aspect), an image shows at
                viewing size. Non-visual assets (audio / files) stay chips
                below. */}
            {assets.map((asset) => {
              const mediaUrl =
                asset.stream_url ??
                (asset.file_url?.startsWith("http") ? asset.file_url : null)
              if (!mediaUrl) return null
              if (asset.type === "video") {
                return (
                  <div key={asset.id} className="flex justify-end">
                    {/* Compact in the flow (2026-09-28 user ruling): once
                        the canvas is live the SAME video sits there at full
                        card size — the message copy is a reference, not the
                        viewing seat, so it steps down (was w-72 like the
                        image). */}
                    <Attachment orientation="vertical" className="w-56 max-w-full">
                      <AttachmentMedia variant="media">
                        <video src={mediaUrl} controls playsInline preload="metadata" />
                      </AttachmentMedia>
                    </Attachment>
                  </div>
                )
              }
              if (asset.type === "image") {
                return (
                  <div key={asset.id} className="flex justify-end">
                    <Attachment orientation="vertical" className="w-72 max-w-full">
                      <AttachmentMedia variant="media">
                        <img src={mediaUrl} alt={asset.title ?? ""} />
                      </AttachmentMedia>
                    </Attachment>
                  </div>
                )
              }
              return null
            })}
            {assets.some((a) => a.type !== "video" && a.type !== "image") && (
            <AttachmentGroup className="justify-end">
            {assets
              .filter((a) => a.type !== "video" && a.type !== "image")
              .map((asset) => {
              const Icon = assetTypeIcon(asset.type)
              const typeLabel = t(`generationOverlay.assetTypes.${asset.type}`, {
                defaultValue: asset.type,
              })
              return (
                <Attachment
                  key={asset.id}
                  size="sm"
                  // An archived message is a historical record — it never
                  // animates. Live processing/uploading states (which make
                  // AttachmentTitle shimmer) belong to the composer, not the
                  // flow; only a genuine failure stays visible, statically.
                  state={asset.processing_status === "failed" ? "error" : "done"}
                >
                  {/* Video/image ride as media messages above (2026-09-25
                      用户拍板) — the chip family is audio / files only, so
                      the sliver slot is always the type icon. */}
                  <AttachmentMedia variant="icon">
                    <Icon />
                  </AttachmentMedia>
                  <AttachmentContent>
                    <AttachmentTitle>
                      {asset.title || assetFilename(asset.file_url) || typeLabel}
                    </AttachmentTitle>
                    <AttachmentDescription>{typeLabel}</AttachmentDescription>
                  </AttachmentContent>
                </Attachment>
              )
            })}
          </AttachmentGroup>
            )}
          </>
        ) : null}
      </MessageContent>
    </Message>
  )
}
