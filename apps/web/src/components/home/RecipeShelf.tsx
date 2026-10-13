"use client"

import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronRight } from "lucide-react"

import { RecipeCard } from "@/components/home/RecipeCard"
import type { ShelfDemo, ShelfItem } from "./recipeFamilies"

/**
 * 横滑货架 (D5, prototype 屏① .shelf): one shelf = a title + a white
 * container (bg-card, 发丝线, rounded-lg — in-flow surface, NO shadow)
 * holding a horizontal scroll track (no-scrollbar). Cards:
 * - recipe items reuse RecipeCard (the schematic cover + three text rows);
 * - demo items are real rendered videos, autoplay loop/muted (MG 族货架).
 *
 * Click 唯一归宿 = composer 预填 (D5 禁则 8): every card hands its
 * `prefillKey` up; the shelf itself never navigates and never opens any
 * template-editing surface.
 *
 * The › pager is honest chrome (禁死按钮): it renders ONLY while there is
 * more to page to (scrollable AND not at the end), one viewport-ish step
 * per click. Circular icon button = the rounded-full law's first exception;
 * same-fill boundary on the white shelf = the hairline ring's legal seat.
 */
export function RecipeShelf({
  title,
  items,
  onPrefill,
  tourAnchorIndex,
}: {
  title: string
  items: ShelfItem[]
  onPrefill: (prefillKey: string) => void
  /** Index of the item that carries the `home-recipes` tour anchor (the
   * fifth recipe card — Tour skips the step when fewer render). */
  tourAnchorIndex?: number
}) {
  const { t } = useTranslation()
  const trackRef = useRef<HTMLDivElement>(null)
  const [canPage, setCanPage] = useState(false)

  // SSR-safe: measurement lives in an effect; the first paint simply has
  // no pager (it appears once the track reports overflow).
  useEffect(() => {
    const el = trackRef.current
    if (!el) return
    const update = () =>
      setCanPage(el.scrollWidth - el.clientWidth - el.scrollLeft > 8)
    update()
    el.addEventListener("scroll", update, { passive: true })
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => {
      el.removeEventListener("scroll", update)
      ro.disconnect()
    }
  }, [items])

  return (
    <section>
      <h3 className="mb-2.5 text-base font-medium">{title}</h3>
      <div className="relative rounded-lg bg-card p-3.5 ring-1 ring-foreground/10">
        <div
          ref={trackRef}
          className="flex gap-3 overflow-x-auto no-scrollbar"
        >
          {items.map((item, index) =>
            item.kind === "recipe" ? (
              <div
                key={item.card.id}
                data-tour={index === tourAnchorIndex ? "home-recipes" : undefined}
                className="w-56 flex-none sm:w-64"
              >
                <RecipeCard card={item.card} onSelect={() => onPrefill(item.prefillKey)} />
              </div>
            ) : (
              <DemoCard
                key={item.demo.id}
                demo={item.demo}
                onSelect={() => onPrefill(item.prefillKey)}
              />
            ),
          )}
        </div>
        {canPage && (
          <button
            type="button"
            aria-label={t("recipes.shelf.nextPage")}
            onClick={() =>
              trackRef.current?.scrollBy({
                left: (trackRef.current.clientWidth ?? 320) * 0.85,
                behavior: "smooth",
              })
            }
            className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-card text-foreground ring-1 ring-foreground/10 transition-colors hover:bg-accent"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        )}
      </div>
    </section>
  )
}

/** One MG demo card: the real render IS the card face (loop/muted, no
 * chrome, no caption — prototype .vcard). Media-tile law: rest = the
 * video's own fill separates it from the shelf; hover = the media-list
 * interaction ring (ring-foreground/30), never a bg seat. */
function DemoCard({
  demo,
  onSelect,
}: {
  demo: ShelfDemo
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`relative flex-none cursor-pointer overflow-hidden rounded-lg hover:ring-1 hover:ring-foreground/30 ${
        demo.orientation === "vertical"
          ? "aspect-[3/4] w-44"
          : "aspect-video w-72"
      }`}
    >
      <video
        src={demo.url}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        className="h-full w-full object-cover"
      />
    </button>
  )
}
