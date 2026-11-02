"use client"

import { mentionTypeDef, type ChatMention } from "@/lib/mentions"

/** One @-entity as a visible inline chip: registry icon + label, with no
 * separate close chrome. In the editor it is deleted as message content. */
export function MentionChip({ mention }: { mention: ChatMention }) {
  const Icon = mentionTypeDef(mention.type)?.icon
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-xs text-foreground">
      {Icon ? <Icon className="size-3 text-muted-foreground" /> : null}
      <span className="max-w-[160px] truncate">{mention.label}</span>
      {/* 选区引用: the pinned passage shows as a muted snippet — the chip
          says WHICH PART, not just which product (display-truncated only). */}
      {mention.quote ? (
        <span className="max-w-[140px] truncate text-muted-foreground">
          “{mention.quote.replace(/\s+/g, " ").trim()}”
        </span>
      ) : null}
    </span>
  )
}
