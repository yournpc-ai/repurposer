import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"

/**
 * The one empty-page look: a quiet icon tile + title + description (+ an
 * optional primary action), centered in whatever room the page leaves it.
 * Pages render it inside a `flex-1` column so the block centers in the
 * viewport remainder below the page header — never a bordered box pinned
 * to the top.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-muted">
        <Icon className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="font-medium">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  )
}
