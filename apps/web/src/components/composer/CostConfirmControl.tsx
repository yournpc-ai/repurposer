"use client"

import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Bell, BellOff, Check, ChevronDown, Hand } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

/** Cost-confirmation strategy control (2026-09-23, UI ONLY — the behavior
 * is NOT wired this batch): a three-way preference for when the agent must
 * stop and confirm before a paid run deducts credits. The trigger is a
 * ghost h-9 pill (one height with the whole control row — the 2026-09-23
 * ruling), the popover's option rows mirror the PersonaPanel row anatomy
 * (icon + title + two-line desc + selected Check).
 *
 * The preference persists to localStorage and nothing reads it for behavior
 * yet — wiring it (auto-start below a threshold / never-ask) touches the
 * confirmed-scope doctrine (ADR-087/088/089) and is its own batch with an
 * ADR. The footnote says this to the user honestly. `useConfirmStrategy`
 * is exported for that future batch — no behavioral consumer exists today.
 *
 * SSR safety: the initial render is always the default strategy; the stored
 * value is read inside an effect only (never during SSR). */
export type ConfirmStrategy = "always" | "large" | "never"

const STORAGE_KEY = "repurposer-confirm-strategy"
const DEFAULT_STRATEGY: ConfirmStrategy = "large"

const STRATEGIES = [
  { id: "always", icon: Hand },
  { id: "large", icon: Bell },
  { id: "never", icon: BellOff },
] as const

function isConfirmStrategy(v: string | null): v is ConfirmStrategy {
  return v === "always" || v === "large" || v === "never"
}

export function useConfirmStrategy() {
  const [strategy, setStrategy] = useState<ConfirmStrategy>(DEFAULT_STRATEGY)
  useEffect(() => {
    try {
      const v = window.localStorage.getItem(STORAGE_KEY)
      if (isConfirmStrategy(v)) setStrategy(v)
    } catch {
      // storage unavailable (private mode) — the default rides
    }
  }, [])
  const select = (next: ConfirmStrategy) => {
    setStrategy(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // ignore — the in-memory choice still stands for this session
    }
  }
  return [strategy, select] as const
}

interface CostConfirmControlProps {
  /** home = "bottom" (the control row sits mid-viewport); the dock MUST pass
   * "top" — it lives at the viewport's bottom edge. */
  popoverSide?: "top" | "bottom"
  align?: "start" | "end"
  className?: string
}

export function CostConfirmControl({
  popoverSide = "bottom",
  align = "end",
  className,
}: CostConfirmControlProps) {
  const { t } = useTranslation()
  const [strategy, select] = useConfirmStrategy()
  const [open, setOpen] = useState(false)
  const CurrentIcon = STRATEGIES.find((s) => s.id === strategy)?.icon ?? Bell

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant="ghost"
            aria-label={t("composer.confirmStrategy.label")}
            className={cn(
              "h-9 shrink-0 gap-1.5 rounded-md px-2.5 text-xs text-muted-foreground hover:text-foreground",
              className,
            )}
          >
            <CurrentIcon className="size-4" />
            <span>{t(`composer.confirmStrategy.trigger.${strategy}`)}</span>
            <ChevronDown className="size-3.5" />
          </Button>
        }
      />
      <PopoverContent
        side={popoverSide}
        align={align}
        className="w-88 gap-0 p-1.5"
      >
        {STRATEGIES.map(({ id, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              select(id)
              setOpen(false)
            }}
            className={cn(
              "flex w-full items-start gap-3 rounded-md px-2 py-2.5 text-left transition-colors",
              strategy === id ? "bg-accent" : "hover:bg-accent/50",
            )}
          >
            <Icon className="mt-0.5 size-4.5 flex-none text-muted-foreground" />
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-medium text-foreground">
                {t(`composer.confirmStrategy.options.${id}.title`)}
              </span>
              <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">
                {t(`composer.confirmStrategy.options.${id}.desc`)}
              </span>
            </span>
            {strategy === id && (
              <Check className="mt-0.5 size-4 flex-none" />
            )}
          </button>
        ))}
        {/* Honesty footnote (same posture as the dock's disclaimer line):
            the control persists a preference only — behavior lands later. */}
        <div className="mt-1 border-t border-foreground/10 px-2 pb-1 pt-2">
          <p className="text-[11px] leading-snug text-meta-foreground">
            {t("composer.confirmStrategy.footnote")}
          </p>
        </div>
      </PopoverContent>
    </Popover>
  )
}
