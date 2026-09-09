/** StatusLine — THE one live status row of the message flow (2026-09-09
 * user ruling): every transient "what's happening NOW" line in the flow is
 * this one component — the chat turn's thinking row (phases: Thinking… →
 * Creating your workflow…) and the run task list's dynamic narrative row
 * alike. LIVE BY DEFINITION: the label is always the CURRENT phase /
 * narrative from the world (never a frozen canned word — 二源律), and the
 * same row's terminal form (active=false) is its static receipt.
 *
 * Anatomy: [leading mark] [shimmer label] [trailing clock?] [chevron?] —
 * `onClick` makes the whole row the toggle (the run row's expand/collapse
 * anchor); `quiet` drops it into the run's text-xs register (the dock's
 * thinking row stays text-sm). */

import { ChevronDown, ChevronUp } from "lucide-react"

import { cn } from "@/lib/utils"

export function StatusLine({
  label,
  active = true,
  leading,
  trailing,
  onClick,
  open,
  quiet = false,
  className,
}: {
  /** The CURRENT phase / narrative (live) or the receipt title (terminal). */
  label: React.ReactNode
  /** Live rows shimmer; the terminal receipt renders static. */
  active?: boolean
  /** Status mark: the brand loader (dock thinking) / the live dot / ✓. */
  leading?: React.ReactNode
  /** The elapsed clock (run rows only — the dock's thinking row never races). */
  trailing?: React.ReactNode
  /** Present → the row is a button (the expand/collapse anchor). */
  onClick?: () => void
  /** Chevron state when clickable. */
  open?: boolean
  /** text-xs quiet register (the run's row); default text-sm (the dock). */
  quiet?: boolean
  className?: string
}) {
  const body = (
    <>
      {leading}
      <span className={cn("min-w-0 truncate", active && "shimmer")}>
        {label}
      </span>
      {trailing ? (
        <span className="shrink-0 tabular-nums">{trailing}</span>
      ) : null}
      {onClick ? (
        open ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronUp className="h-3 w-3 shrink-0" />
        )
      ) : null}
    </>
  )
  const classes = cn(
    "flex w-full items-center gap-2 text-muted-foreground",
    quiet ? "text-xs" : "text-sm",
    onClick && "rounded-md text-left transition-colors hover:bg-accent/50",
    className,
  )
  return onClick ? (
    <button type="button" onClick={onClick} className={classes}>
      {body}
    </button>
  ) : (
    <div className={classes}>{body}</div>
  )
}
