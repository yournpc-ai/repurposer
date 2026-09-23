"use client"

import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Bell, BellOff, Check, ChevronDown, Hand } from "lucide-react"

import { apiGet, apiPut } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

/** Cost-confirmation strategy control (ADR-092, E5/E6 — 2026-09-24 集成批):
 * a three-way preference for when the agent's confirm beat escalates its
 * cost disclosure. The preference persists SERVER-SIDE (users.settings
 * JSONB via GET/PUT /auth/settings); localStorage degrades to the
 * first-visit / fetch-failure fallback (E5 裁决). The behavioral consumer
 * is the plan dock's disclosure tier (ChatDock): `never` = the estimate
 * slot as-is; `always` = the disclosure row + the priced CTA; `large` =
 * the same when the quote's high end crosses `threshold`
 * (billing.confirm_large_threshold, the configs public parameter — it
 * rides the settings GET so the tier needs ONE read).
 *
 * Module-level cache: the composer control and the dock both mount this
 * hook — one fetch per session, every mount reads the same truth, and a
 * `select` updates every subscriber optimistically.
 *
 * SSR safety: the initial render is always the default strategy; the stored
 * value is read inside an effect only (never during SSR). */
export type ConfirmStrategy = "always" | "large" | "never"

const STORAGE_KEY = "repurposer-confirm-strategy"
const DEFAULT_STRATEGY: ConfirmStrategy = "large"
const DEFAULT_THRESHOLD = 20

interface ConfirmStrategySettings {
  strategy: ConfirmStrategy
  threshold: number
}

let _cache: ConfirmStrategySettings | null = null
let _inflight: Promise<void> | null = null
const _listeners = new Set<() => void>()

function _emit() {
  for (const fn of _listeners) fn()
}

async function _fetchSettings() {
  try {
    const res = await apiGet("/auth/settings", { toast: false })
    if (!res.ok) return
    const data = (await res.json()) as {
      confirm_strategy?: string
      confirm_large_threshold?: number
    }
    const strategy = isConfirmStrategy(data.confirm_strategy ?? null)
      ? (data.confirm_strategy as ConfirmStrategy)
      : DEFAULT_STRATEGY
    const threshold =
      typeof data.confirm_large_threshold === "number"
        ? data.confirm_large_threshold
        : DEFAULT_THRESHOLD
    _cache = { strategy, threshold }
    try {
      window.localStorage.setItem(STORAGE_KEY, strategy)
    } catch {
      // storage unavailable — the server truth already landed
    }
    _emit()
  } catch {
    // network failure — localStorage / the default rides (E5 回退)
  }
}

function _ensureSettings() {
  if (_cache !== null || _inflight !== null) return
  _inflight = _fetchSettings().finally(() => {
    _inflight = null
  })
}

const STRATEGIES = [
  { id: "always", icon: Hand },
  { id: "large", icon: Bell },
  { id: "never", icon: BellOff },
] as const

function isConfirmStrategy(v: string | null): v is ConfirmStrategy {
  return v === "always" || v === "large" || v === "never"
}

export function useConfirmStrategy() {
  const [settings, setSettings] = useState<ConfirmStrategySettings>({
    strategy: DEFAULT_STRATEGY,
    threshold: DEFAULT_THRESHOLD,
  })
  useEffect(() => {
    // First paint rides the local fallback, then the server truth lands.
    try {
      const v = window.localStorage.getItem(STORAGE_KEY)
      if (isConfirmStrategy(v)) {
        setSettings((s) => (_cache ? s : { ...s, strategy: v }))
      }
    } catch {
      // storage unavailable (private mode) — the default rides
    }
    const sync = () => {
      if (_cache) setSettings(_cache)
    }
    _listeners.add(sync)
    sync()
    _ensureSettings()
    return () => {
      _listeners.delete(sync)
    }
  }, [])
  const select = (next: ConfirmStrategy) => {
    const previous = _cache
    _cache = { strategy: next, threshold: _cache?.threshold ?? DEFAULT_THRESHOLD }
    setSettings(_cache)
    _emit()
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // ignore — the in-memory choice still stands for this session
    }
    apiPut("/auth/settings", { confirm_strategy: next }, { toast: false }).then(
      (res) => {
        if (!res.ok && previous) {
          _cache = previous
          setSettings(previous)
          _emit()
        }
      },
      () => {
        if (previous) {
          _cache = previous
          setSettings(previous)
          _emit()
        }
      },
    )
  }
  return { strategy: settings.strategy, threshold: settings.threshold, select } as const
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
  const { strategy, select } = useConfirmStrategy()
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
