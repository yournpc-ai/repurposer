"use client"

import { ArrowUp, Square } from "@/components/ui/icons"
import { IconButton, type IconButtonProps } from "@/components/ui/icon-button-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { cn } from "@/lib/utils"

type ComposerSendButtonProps = Omit<IconButtonProps, "icon"> & {
  generating?: boolean
  stop?: boolean
}

export function ComposerSendButton({
  generating,
  stop,
  className,
  style,
  ...props
}: ComposerSendButtonProps) {
  const icon = stop ? (
    <Square fill="currentColor" strokeWidth={0} className="size-3" />
  ) : generating ? (
    <Spinner />
  ) : (
    <ArrowUp className="size-4" />
  )
  return (
    <IconButton
      variant={stop ? "secondary" : "primary"}
      icon={icon}
      data-stop={stop ? "" : undefined}
      className={cn(
        "rounded-full",
        stop && "hover:bg-destructive/15!",
        className,
      )}
      style={{
        ["--radius" as string]: "9999px",
        ["--size" as string]: "32px",
        ...(stop
          ? {
              ["--ui-icbc-icon" as string]: "#ef4444",
              ["--ui-icbc-ink" as string]: "#ef4444",
            }
          : {}),
        ...style,
      }}
      {...props}
    />
  )
}
