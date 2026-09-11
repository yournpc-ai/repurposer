"use client"

import { X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { mentionTypeDef, type ChatMention } from "@/lib/mentions"

/**
 * 提及 chip (MentionChip) — one @-entity as a visible inline chip: registry
 * icon + label + × (chip three laws, docs/tasks/recipe-mention.md §2.4:
 * visible / consumed on send / × purifies). Reads the registry only; with no
 * `onRemove` it renders as a static tag (message bubbles, 期 2).
 */
export function MentionChip({
  mention,
  onRemove,
}: {
  mention: ChatMention
  onRemove?: () => void
}) {
  const Icon = mentionTypeDef(mention.type)?.icon
  const { t } = useTranslation()
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-xs text-foreground">
      {Icon ? <Icon className="h-3 w-3 text-muted-foreground" /> : null}
      <span className="max-w-[160px] truncate">{mention.label}</span>
      {/* 选区引用: the pinned passage shows as a muted snippet — the chip
          says WHICH PART, not just which product (display-truncated only). */}
      {mention.quote ? (
        <span className="max-w-[140px] truncate text-muted-foreground">
          “{mention.quote.replace(/\s+/g, " ").trim()}”
        </span>
      ) : null}
      {onRemove ? (
        <button
          type="button"
          aria-label={t("mentions.remove")}
          onMouseDown={(e) => e.preventDefault() /* keep textarea focus */}
          onClick={onRemove}
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="h-3 w-3" />
        </button>
      ) : null}
    </span>
  )
}
