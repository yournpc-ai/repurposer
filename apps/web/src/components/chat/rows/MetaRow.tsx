/** MetaRow — the gray system-layer row (一切入流, the Claude Code anatomy):
 * system facts (step ticks, the run recap, focus events) render IN the
 * message flow as muted meta text — never as separate chrome anywhere.
 * Over-long text clamps (`lines`) and toggles on click (ctrl+o, translated). */

import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Crosshair, TriangleAlert } from "lucide-react"

import { cn } from "@/lib/utils"

export function MetaRow({
  icon,
  children,
  shimmer = false,
  lines = 2,
}: {
  icon?: React.ReactNode
  children: string
  shimmer?: boolean
  lines?: 1 | 2
}) {
  // Char-length proxy (no DOM measurement): ~90 chars/line at text-xs in the
  // max-w-3xl column — short rows never grow a pointer cursor for nothing.
  const clampable = children.length > lines * 90
  const [expanded, setExpanded] = useState(false)
  const Text = clampable ? "button" : "span"
  return (
    <div className="flex min-w-0 items-start gap-2 text-xs leading-relaxed text-muted-foreground">
      {icon && <span aria-hidden="true" className="shrink-0 [&>svg]:size-4">{icon}</span>}
      <Text
        type={clampable ? "button" : undefined}
        aria-expanded={clampable ? expanded : undefined}
        onClick={clampable ? () => setExpanded((value) => !value) : undefined}
        className={cn("min-w-0 text-start", shimmer && "shimmer",
          clampable && !expanded && (lines === 1 ? "line-clamp-1" : "line-clamp-2"))}
      >
        {children}
      </Text>
    </div>
  )
}

/** A canvas focus event (D8 修订 — 焦点入流): the tail row = the PENDING
 * focus (consumed on send); the same row rides a user message as its
 * persisted prefix. */
export function FocusRow({ label }: { label: string }) {
  const { t } = useTranslation()
  return (
    <MetaRow icon={<Crosshair />}>
      {t("results.dock.focus", { name: label })}
    </MetaRow>
  )
}

/** A failed turn's system fact (turn.failed / transport error — e.g. the
 * provider's balance running out): the gray in-flow row is the ONLY surface,
 * never a toast (the Claude Code inline usage-limit row is the reference
 * anatomy — a turn failure is a fact of the conversation, not chrome). */
export function TurnErrorRow({ text }: { text: string }) {
  return (
    <MetaRow icon={<TriangleAlert />}>
      {text}
    </MetaRow>
  )
}
