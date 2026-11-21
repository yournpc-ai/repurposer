"use client"

import type { LucideIcon } from "lucide-react"
import { IconButton, type IconButtonProps } from "@/components/ui/icon-button-clean"

export function ComposerIconButton({ icon: Icon, ...props }: Omit<IconButtonProps, "icon"> & { icon: LucideIcon }) {
  return <IconButton {...props} icon={<Icon />} />
}
