"use client"

import type { AppIcon } from "@/components/ui/icons"
import { IconButton, type IconButtonProps } from "@/components/ui/icon-button-clean"
import { cn } from "@/lib/utils"

export function ComposerIconButton({
  icon: Icon,
  variant = "secondary",
  className,
  style,
  ...props
}: Omit<IconButtonProps, "icon"> & { icon: AppIcon }) {
  return (
    <IconButton
      variant={variant}
      {...props}
      className={cn("rounded-full", className)}
      style={{
        ["--radius" as string]: "9999px",
        ["--size" as string]: "32px",
        ...style,
      }}
      icon={<Icon className="size-4" />}
    />
  )
}
