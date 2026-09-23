"use client"

import { forwardRef, type ComponentProps } from "react"
import { ArrowUp } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

/** Composer leaf — THE send button, shared by the home composer and the
 * chat dock (2026-09-23 unification; previously two copies whose glyphs
 * even differed: home size-5, dock h-4.5 w-4.5). One size for the whole
 * control row (h-9 / 36px), one glyph size (size-4.5, matching the circle
 * icon buttons), one spinner recipe. The two shells keep their own disabled
 * logic (home: launching only; dock: empty-text-no-attachments / uploads in
 * flight) and pass the verdict in — the leaf owns no policy. The dock's
 * stop button is a separate control (secondary variant), not this leaf. */
interface ComposerSendButtonProps
  extends Omit<ComponentProps<typeof Button>, "children"> {
  /** Spinner state (launch/stream in flight). */
  generating?: boolean
  /** aria-label (chat.send / composer send copy). */
  label: string
}

export const ComposerSendButton = forwardRef<
  HTMLButtonElement,
  ComposerSendButtonProps
>(function ComposerSendButton(
  { generating, label, className, ...props },
  ref,
) {
  return (
    <Button
      ref={ref}
      size="icon"
      aria-label={label}
      className={cn("h-9 w-9 shrink-0 rounded-full transition-colors", className)}
      {...props}
    >
      {generating ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        <ArrowUp className="size-4.5" />
      )}
    </Button>
  )
})
