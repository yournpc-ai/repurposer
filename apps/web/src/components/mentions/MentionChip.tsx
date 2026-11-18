"use client"

import { useTranslation } from "react-i18next"

import { mentionTypeDef, type ChatMention } from "@/lib/mentions"
import { formatMediaTimeMs } from "@/lib/mediaRegionSelection"
import { cn } from "@/lib/utils"

export const MENTION_CHIP_CLASS_NAME =
  "mx-0.5 inline-flex items-baseline gap-0.5 rounded-md bg-muted px-1 text-foreground"

/** One @-entity as a visible inline chip: registry icon + label, with no
 * separate close chrome. In the editor it is deleted as message content. */
export function MentionChip({ mention }: { mention: ChatMention }) {
  const { t } = useTranslation()
  const Icon = mentionTypeDef(mention.type)?.icon
  return (
    <span className={cn(MENTION_CHIP_CLASS_NAME, "items-center gap-1 px-1.5 py-0.5 text-xs")}>
      {Icon ? <Icon className="size-3 text-muted-foreground" /> : null}
      <span className="max-w-[160px] truncate">{mention.label}</span>
      {/* 选区引用: the pinned passage shows as a muted snippet — the chip
          says WHICH PART, not just which product (display-truncated only). */}
      {mention.quote ? (
        <span className="max-w-[140px] truncate text-muted-foreground">
          “{mention.quote.replace(/\s+/g, " ").trim()}”
        </span>
      ) : null}
      {mention.region ? (
        <span className="shrink-0 text-muted-foreground">
          {t("mentions.regionChip", {
            time: formatMediaTimeMs(mention.region.mediaTimeMs),
            width: mention.region.sourceRect.width,
            height: mention.region.sourceRect.height,
          })}
        </span>
      ) : null}
    </span>
  )
}
