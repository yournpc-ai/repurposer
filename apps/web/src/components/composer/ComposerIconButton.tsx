"use client"

import { forwardRef, type ComponentProps } from "react"
import type { LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

/** Composer leaf — the bottom-row circle icon button, shared by the home
 * composer and the chat dock (2026-09-23 unification; previously two copies
 * with diverging sizes: home h-8, dock h-9). The whole control row is one
 * height now (h-9 / 36px — the 2026-09-23 ruling retiring the 2026-08-31
 * "one quiet register below the send" size gap): send, circle buttons and
 * the cost-confirm pill all share it, so hover backgrounds align on the
 * row's top/bottom edges by construction.
 *
 * Rail margins (the glyph-edge alignment law) are injected by the shells via
 * className — never baked in here. Tooltip/Popover composition is NOT built
 * in either: bare buttons (dock attach/history/hide) use this directly, the
 * button+tooltip+panel trinity is ComposerPanelButton. Rest props and ref
 * are forwarded verbatim — base-ui's PopoverTrigger/TooltipTrigger `render`
 * chain merges its handlers onto this element. */
interface ComposerIconButtonProps
  extends Omit<ComponentProps<typeof Button>, "children"> {
  icon: LucideIcon
  /** aria-label; the shells reuse it as the tooltip copy. */
  label: string
}

export const ComposerIconButton = forwardRef<
  HTMLButtonElement,
  ComposerIconButtonProps
>(function ComposerIconButton(
  { icon: Icon, label, className, ...props },
  ref,
) {
  return (
    <Button
      ref={ref}
      variant="ghost"
      size="icon"
      aria-label={label}
      className={cn(
        "h-9 w-9 shrink-0 rounded-full text-muted-foreground hover:text-foreground",
        className,
      )}
      {...props}
    >
      <Icon className="size-4.5" />
    </Button>
  )
})
