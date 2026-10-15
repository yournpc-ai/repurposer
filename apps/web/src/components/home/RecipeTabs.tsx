"use client"

import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronLeft, ChevronRight } from "lucide-react"

import type { ResolvedFamily } from "./recipeFamilies"

/**
 * 两级 tab (D5, prototype 屏①): 一级 = family pill 轨 (stadium pills on a
 * muted track — the rounded-full law's gallery-pill exception register;
 * active = solid foreground pill, inactive = quiet text, hover bg-accent),
 * 二级 = 下划线文本 tab (2px foreground indicator under the active label) —
 * ANCHORS into the active family's stacked sub sections, not filters: the
 * route renders every sub's shelves and owns the scroll-to + scroll spy.
 *
 * The component is fully controlled — the route owns the selection
 * (active family + per-family sub memory, prototype parity) so the shelf
 * section below reads the same pair. A family with a SINGLE sub skips the
 * subrow entirely: an underline communicates selection among siblings, and
 * with one sibling it is pure noise.
 *
 * Mobile overflow: when the pill lane is wider than its container, the edge
 * chevrons render as IN-LANE flex-none slots (dedicated lanes, never
 * overlays) — the pills' scroll lane lives strictly BETWEEN them, so a pill
 * never renders under a chevron (Pexo mobile parity: arrow slots + scroll
 * lane are separate boxes). BOTH chevrons stay visible for as long as the
 * lane overflows at all (constant affordance — they never vanish
 * mid-scroll; a tap at the edge simply clamps). The end FADES stay
 * directional — an end fades ONLY while there is more to scroll to in that
 * direction, and the mask applies to the scroll lane only (chevron slots
 * never fade).
 * SSR and the first paint render the no-overflow form; measurement lives in
 * an effect and re-runs on family set / language (t identity) changes.
 */
export function RecipeTabs({
  families,
  activeFamilyId,
  activeSubId,
  onSelectFamily,
  onSelectSub,
}: {
  families: ResolvedFamily[]
  activeFamilyId: string
  activeSubId: string | null
  onSelectFamily: (familyId: string) => void
  onSelectSub: (familyId: string, subId: string) => void
}) {
  const { t } = useTranslation()
  const active = families.find((f) => f.id === activeFamilyId)

  const trackRef = useRef<HTMLDivElement>(null)
  const [overflow, setOverflow] = useState({ any: false, left: false, right: false })
  useEffect(() => {
    const el = trackRef.current
    if (!el) return
    const update = () =>
      setOverflow({
        any: el.scrollWidth - el.clientWidth > 8,
        left: el.scrollLeft > 8,
        right: el.scrollWidth - el.clientWidth - el.scrollLeft > 8,
      })
    update()
    el.addEventListener("scroll", update, { passive: true })
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => {
      el.removeEventListener("scroll", update)
      ro.disconnect()
    }
  }, [families, t])
  const trackMask =
    overflow.left && overflow.right
      ? "linear-gradient(to right, transparent, black 32px, black calc(100% - 32px), transparent)"
      : overflow.right
        ? "linear-gradient(to right, black calc(100% - 32px), transparent)"
        : overflow.left
          ? "linear-gradient(to right, transparent, black 32px)"
          : undefined

  return (
    <div className="flex flex-col items-center gap-5">
      {/* 一级 pill 轨 — the track is a recessed muted lane; pills ride it.
          Text stays regular weight (pill law — 不加粗). The overflow
          chevrons are flex-none in-lane slots with the pills' scroll lane
          between them (never absolute overlays — a pill never slides under
          an arrow). h-9 = the pills' height, one shared center line. */}
      <div className="inline-flex max-w-full items-center gap-1 rounded-full bg-muted p-1">
        {overflow.any && (
          <button
            type="button"
            aria-hidden={true}
            tabIndex={-1}
            onClick={() =>
              trackRef.current?.scrollBy({
                left: -trackRef.current.clientWidth * 0.6,
                behavior: "smooth",
              })
            }
            className="flex h-9 w-8 flex-none items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent active:bg-accent"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        )}
        <div
          ref={trackRef}
          className="inline-flex min-w-0 items-center gap-1 overflow-x-auto no-scrollbar"
          style={
            trackMask
              ? { maskImage: trackMask, WebkitMaskImage: trackMask }
              : undefined
          }
        >
          {families.map((family) => {
            const Icon = family.icon
            const on = family.id === activeFamilyId
            return (
              <button
                key={family.id}
                type="button"
                onClick={() => onSelectFamily(family.id)}
                className={`flex h-9 flex-none items-center gap-1.5 rounded-full px-4 text-sm transition-colors ${
                  on
                    ? "bg-foreground text-background"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                }`}
              >
                {Icon && <Icon className="h-4 w-4" />}
                {t(`recipes.shelf.families.${family.id}`)}
              </button>
            )
          })}
        </div>
        {overflow.any && (
          <button
            type="button"
            aria-hidden={true}
            tabIndex={-1}
            onClick={() =>
              trackRef.current?.scrollBy({
                left: trackRef.current.clientWidth * 0.6,
                behavior: "smooth",
              })
            }
            className="flex h-9 w-8 flex-none items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent active:bg-accent"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* 二级下划线子 tab — only when the family actually has siblings to
          choose among. */}
      {active && active.subs.length > 1 && (
        <div className="flex max-w-full items-center justify-center gap-8 overflow-x-auto no-scrollbar">
          {active.subs.map((sub) => {
            const on = sub.id === activeSubId
            return (
              <button
                key={sub.id}
                type="button"
                onClick={() => onSelectSub(active.id, sub.id)}
                className={`relative flex-none pb-2 text-sm transition-colors ${
                  on ? "text-foreground" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t(`recipes.shelf.subs.${sub.id}`)}
                {on && (
                  <span className="absolute bottom-0 left-1/2 h-0.5 w-5 -translate-x-1/2 bg-foreground" />
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
