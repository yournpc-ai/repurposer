"use client"

import { ArrowUp, Square } from "lucide-react"
import { IconButton, type IconButtonProps } from "@/components/ui/icon-button-clean"
import { Spinner } from "@/components/ui/spinner-clean"

type ComposerSendButtonProps = Omit<IconButtonProps, "icon"> & {
  generating?: boolean
  stop?: boolean
}

export function ComposerSendButton({ generating, stop, ...props }: ComposerSendButtonProps) {
  const icon = stop ? <Square fill="currentColor" /> : generating ? <Spinner /> : <ArrowUp />
  return <IconButton variant="primary" icon={icon} {...props} />
}
