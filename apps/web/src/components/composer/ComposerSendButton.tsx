"use client"

import { ArrowUp, Square } from "lucide-react"
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
    <Square fill="currentColor" className="size-3.5" />
  ) : generating ? (
    <Spinner />
  ) : (
    <ArrowUp className="size-4" />
  )
  return (
    <IconButton
      variant="primary"
      icon={icon}
      className={cn("rounded-full", className)}
      style={{
        ["--radius" as string]: "9999px",
        ["--size" as string]: "32px",
        ...style,
      }}
      {...props}
    />
  )
}
