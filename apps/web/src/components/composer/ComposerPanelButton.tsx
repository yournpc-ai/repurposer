"use client"

import { useId, type ReactNode } from "react"
import type { AppIcon } from "@/components/ui/icons"

import { Popover } from "@/components/ui/popover-clean"
import { Tooltip } from "@/components/ui/tooltip-clean"
import { ComposerIconButton } from "@/components/composer/ComposerIconButton"

interface ComposerPanelButtonProps {
  icon: AppIcon
  label: string
  open: boolean
  onOpenChange: (open: boolean) => void
  tooltipSide?: "top" | "bottom"
  popoverSide?: "top" | "bottom"
  align?: "start" | "center" | "end"
  tabIndex?: number
  "data-tour"?: string
  children: ReactNode
}

export function ComposerPanelButton({
  icon,
  label,
  open,
  onOpenChange,
  tooltipSide = "top",
  popoverSide = "bottom",
  align = "start",
  tabIndex,
  "data-tour": dataTour,
  children,
}: ComposerPanelButtonProps) {
  const panelId = useId()
  return (
    <span className="inline-flex">
      <Tooltip content={label} side={tooltipSide} disabled={open}>
        <ComposerIconButton
          label={label}
          icon={icon}
          title=""
          className="rounded-full"
          tabIndex={tabIndex}
          data-tour={dataTour}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          onClick={() => onOpenChange(!open)}
        />
      </Tooltip>
      <Popover
        id={panelId}
        aria-label={label}
        open={open}
        onClose={() => onOpenChange(false)}
        side={popoverSide}
        align={align}
        width="22rem"
      >
        {children}
      </Popover>
    </span>
  )
}
