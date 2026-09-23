"use client"

import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { ComposerIconButton } from "@/components/composer/ComposerIconButton"

/** Composer leaf — the circle button + function tooltip + frosted panel
 * trinity (absorbs the structure HomeComposer repeated three times:
 * Assets / Persona / Models). The base-ui render chain (Tooltip >
 * TooltipTrigger render={PopoverTrigger render={button}}) is load-bearing —
 * do not "simplify" it; the triggers merge their handlers through exactly
 * this nesting. Stateless buttons (2026-08-30 ruling): no count, no value
 * text — the selection is read inside each frosted panel. */
interface ComposerPanelButtonProps {
  icon: LucideIcon
  /** aria-label AND tooltip copy. */
  label: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
  tooltipSide?: "top" | "bottom"
  popoverSide?: "top" | "bottom"
  align?: "start" | "center" | "end"
  /** Panel width — the composer panels unified on w-88 (2026-09-23; the
   * Assets panel's w-80 was the outlier). */
  panelWidth?: string
  /** Panels carrying their own full padding system (e.g. ModelsPanel) pass
   * this to strip the Popover base's gap-4 p-2.5 (CreditsPill precedent). */
  unpadded?: boolean
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
  panelWidth = "w-88",
  unpadded,
  tabIndex,
  "data-tour": dataTour,
  children,
}: ComposerPanelButtonProps) {
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <Tooltip>
        <TooltipTrigger
          render={
            <PopoverTrigger
              render={
                <ComposerIconButton
                  icon={icon}
                  label={label}
                  tabIndex={tabIndex}
                  data-tour={dataTour}
                />
              }
            />
          }
        />
        <TooltipContent side={tooltipSide}>{label}</TooltipContent>
      </Tooltip>
      <PopoverContent
        side={popoverSide}
        align={align}
        className={cn(panelWidth, unpadded && "gap-0 p-0")}
      >
        {children}
      </PopoverContent>
    </Popover>
  )
}
