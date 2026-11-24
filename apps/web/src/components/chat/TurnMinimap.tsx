"use client"

import { useEffect, useState, type RefObject } from "react"
import { motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge-clean"
import { Tooltip } from "@/components/ui/tooltip-clean"
import { cn } from "@/lib/utils"

export interface TurnMinimapItem {
  id: string
  index: number
  preview: string
  versionLabel?: string | null
}

function truncatePreview(text: string, maxChars = 16): string {
  const clean = text.replace(/\s+/g, " ").trim()
  if (!clean) return "…"
  const chars = Array.from(clean)
  if (chars.length <= maxChars) return clean
  return `${chars.slice(0, maxChars).join("")}…`
}

export function TurnMinimap({
  turns,
  viewportRef,
  className,
}: {
  turns: TurnMinimapItem[]
  viewportRef: RefObject<HTMLDivElement | null>
  className?: string
}) {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const [activeId, setActiveId] = useState<string | null>(() => turns.at(-1)?.id ?? null)

  useEffect(() => {
    if (turns.length < 3) return
    setActiveId((prev) =>
      prev && turns.some((turn) => turn.id === prev) ? prev : (turns.at(-1)?.id ?? null),
    )
  }, [turns])

  useEffect(() => {
    if (turns.length < 3) return
    const root = viewportRef.current
    if (!root || typeof IntersectionObserver === "undefined") return
    const nodes = Array.from(root.querySelectorAll<HTMLElement>("[data-turn-minimap-id]"))
    if (nodes.length === 0) return

    const ratios = new Map<string, number>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).dataset.turnMinimapId
          if (!id) continue
          ratios.set(id, entry.isIntersecting ? entry.intersectionRatio : 0)
        }
        let bestId: string | null = null
        let bestRatio = 0
        for (const turn of turns) {
          const r = ratios.get(turn.id) ?? 0
          if (r > bestRatio) {
            bestRatio = r
            bestId = turn.id
          }
        }
        if (bestId) setActiveId(bestId)
      },
      { root, threshold: [0, 0.2, 0.5, 0.8, 1] },
    )
    for (const node of nodes) observer.observe(node)
    return () => observer.disconnect()
  }, [turns, viewportRef])

  if (turns.length < 3) return null

  const handleJump = (turnId: string) => {
    setActiveId(turnId)
    const root = viewportRef.current ?? document
    const escapedId =
      typeof CSS !== "undefined" && typeof CSS.escape === "function"
        ? CSS.escape(turnId)
        : turnId.replace(/"/g, '\\"')
    const target = root.querySelector<HTMLElement>(
      `[data-turn-minimap-id="${escapedId}"]`,
    )
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({
        behavior: prefersReducedMotion ? "auto" : "smooth",
        block: "start",
      })
    }
  }

  return (
    <motion.nav
      data-slot="turn-minimap"
      aria-label={t("chat.minimap.ariaLabel")}
      initial={prefersReducedMotion ? false : { opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "pointer-events-auto absolute left-2 top-1/2 z-10 hidden -translate-y-1/2 flex-col items-center gap-1.5 rounded-full border border-border/70 bg-background/85 px-1 py-2 shadow-xs backdrop-blur-sm md:flex",
        className,
      )}
    >
      {turns.map((turn) => {
        const active = turn.id === activeId
        const preview = truncatePreview(turn.preview)
        const label = turn.versionLabel
          ? `${t("chat.minimap.turnLabel", { index: turn.index })}: ${preview} (${turn.versionLabel})`
          : `${t("chat.minimap.turnLabel", { index: turn.index })}: ${preview}`
        return (
          <Tooltip
            key={turn.id}
            side="right"
            delay={120}
            content={
              <span className="inline-flex items-center gap-1.5">
                <span className="truncate">{preview}</span>
                {turn.versionLabel ? (
                  <Badge tone="info" size="sm">
                    {turn.versionLabel}
                  </Badge>
                ) : null}
              </span>
            }
          >
            <button
              type="button"
              aria-label={label}
              aria-current={active ? "true" : undefined}
              onClick={() => handleJump(turn.id)}
              className="group flex size-4 items-center justify-center rounded-full focus-visible:outline-2 focus-visible:outline-ring"
            >
              <motion.span
                animate={
                  prefersReducedMotion
                    ? undefined
                    : { scale: active ? 1.35 : 1 }
                }
                transition={{ type: "spring", stiffness: 420, damping: 32 }}
                className={cn(
                  "block rounded-full transition-colors",
                  active
                    ? "size-2 bg-foreground"
                    : "size-1.5 bg-muted-foreground/45 group-hover:bg-muted-foreground",
                )}
              />
            </button>
          </Tooltip>
        )
      })}
    </motion.nav>
  )
}
