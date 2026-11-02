import type { ChatMention } from "@/lib/mentions"
import type { ChatAttachment } from "@/lib/types"
import type { SkillOption, SkillReference } from "@/lib/skills"

export interface FirstMessageHandoff {
  text: string
  mentions?: ChatMention[]
  skill?: SkillReference
  /** Presentational metadata for the same reference; never sent as a second
   * server binding. Keeps the Home chip's name intact across navigation. */
  skillOption?: SkillOption
  personaId?: string
  attachments?: ChatAttachment[]
}

export interface MessageAttachmentAsset {
  id: string
  type: string
  file_url: string | null
  stream_url?: string | null
  title: string | null
  processing_status: "pending" | "processing" | "completed" | "failed"
}

/** ChatAttachment's wire vocabulary is narrower than AssetType. */
export function chatAttachmentType(
  assetType: string,
): ChatAttachment["type"] {
  return assetType === "image" || assetType === "video" || assetType === "audio"
    ? assetType
    : "file"
}

export function chatAttachmentFromAsset(
  asset: {
    id: string
    type: string
    file_url?: string | null
    stream_url?: string | null
    title?: string | null
  },
  fallback: { name: string; size?: number },
): ChatAttachment {
  return {
    id: asset.id,
    name: asset.title || fallback.name,
    type: chatAttachmentType(asset.type),
    url: asset.stream_url ?? asset.file_url ?? undefined,
    size: fallback.size,
    status: "uploaded",
  }
}

export type MessageAttachment = Omit<ChatAttachment, "status"> & {
  status?: ChatAttachment["status"]
}

/** Live optimistic bubbles and static history read the same attachment shape. */
export function messageAssetsFromAttachments(
  attachments: readonly MessageAttachment[],
): MessageAttachmentAsset[] {
  return attachments.map((attachment) => ({
    id: attachment.id,
    type: attachment.type,
    file_url: attachment.url ?? null,
    stream_url: attachment.url ?? null,
    title: attachment.name,
    processing_status: attachment.status === "failed" ? "failed" : "completed",
  }))
}
