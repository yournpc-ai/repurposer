"use client"

import { useTranslation } from "react-i18next"
import { Maximize2, Wand2 } from "lucide-react"

import { recipeCovers } from "@/components/recipes/covers"
import type { RecipePublic } from "@/lib/recipes"

/**
 * One recipe card (recipe-gallery-v2, ADR-048): the card is a STATIC
 * process schematic at rest and a re-triggered schematic animation on
 * hover. The card face holds no real material — no video, no poster, no
 * audio. The schema cover is a single inline SVG, three grayscale tiers
 * only (currentColor + opacity), and the same `transform-box: fill-box`
 * CSS keyframes that drive the v2 demo (`docs/tasks/recipe-gallery-v2-covers.html`).
 *
 * Hover state machine (MiniMax anatomy, second pass 2026-08-23):
 *   rest  = the schematic (static, no chrome) — title + promise + input
 *           row always readable under the tile;
 *   hover = the schematic plays its process animation (see styles.css
 *           `rc-*` keyframes, gated by `.group:hover`); a white stadium
 *           Remix pill (`Wand2` + label) centers, an expand icon-button
 *           sits top-right — both open the same inspect overlay (no
 *           quick-launch, ADR-040);
 *   click = the RecipeInspectOverlay (the ONLY launch path).
 *
 * Color law: the cover's `text-foreground` color governs the schematic;
 * `prefers-reduced-motion` disables every animation (the rest geometry
 * remains legible on its own).
 */
export function RecipeCard({
  card,
  onInspect,
}: {
  card: RecipePublic
  onInspect: (card: RecipePublic) => void
}) {
  const { t } = useTranslation()
  const Cover = recipeCovers[card.id]
  const live = card.status === "live"

  return (
    <div
      role={live ? "button" : undefined}
      tabIndex={live ? 0 : undefined}
      onClick={() => live && onInspect(card)}
      onKeyDown={(e) => {
        if (live && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault() // Space would otherwise scroll the page
          onInspect(card)
        }
      }}
      className={`group flex flex-col gap-2.5 outline-none ${
        live ? "cursor-pointer" : ""
      }`}
    >
      {/* The tile — bg-inset well, no ring, no shadow (fill-first, ADR-046).
          16:10 carries the schematic; the inline SVG is the only content. */}
      <div className="relative aspect-[16/10] overflow-hidden rounded-lg bg-inset text-foreground">
        {Cover ? (
          <Cover />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
            {card.id}
          </div>
        )}

        {/* Hover chrome — stadium Remix pill centered, expand icon
            top-right. Both open the overlay (ADR-040). Kept off the card
            at rest (the schematic IS the card face). Reserved cards stay
            non-launchable: no hover chrome, no click. */}
        {live && (
          <>
            <button
              type="button"
              tabIndex={-1}
              aria-hidden
              onClick={(e) => {
                e.stopPropagation()
                onInspect(card)
              }}
              className="pointer-events-none absolute left-1/2 top-1/2 flex h-9 -translate-x-1/2 -translate-y-1/2 scale-95 items-center gap-1.5 rounded-full bg-white/90 px-5 text-sm font-medium text-black opacity-0 transition-all duration-200 hover:bg-white group-hover:pointer-events-auto group-hover:scale-100 group-hover:opacity-100"
            >
              <Wand2 className="h-4 w-4" />
              {t("recipes.remix")}
            </button>
            <button
              type="button"
              tabIndex={-1}
              aria-label={t("recipes.expand")}
              onClick={(e) => {
                e.stopPropagation()
                onInspect(card)
              }}
              className="pointer-events-none absolute right-2.5 top-2.5 flex h-8 w-8 scale-90 items-center justify-center rounded-md bg-white/15 text-foreground opacity-0 backdrop-blur-sm transition-all duration-200 hover:bg-white/25 group-hover:pointer-events-auto group-hover:scale-100 group-hover:opacity-100"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          </>
        )}
      </div>

      {/* Three rows under the tile, grid-aligned across the row (consistent
          baseline across cards): title (with optional Soon pill for
          reserved) / promise (2-line clamp) / input scenario row (single-
          line meta, tracked uppercase — `text-meta` only sets color +
          uppercase + tracking, the size must come from a utility class,
          otherwise it falls back to 16px). */}
      <div className="px-0.5">
        <div className="flex items-center gap-1.5">
          <p className="text-sm font-medium">{t(`recipes.${card.id}.title`)}</p>
          {!live && (
            <span className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {t("recipes.soon")}
            </span>
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 min-h-10 text-xs leading-relaxed text-muted-foreground">
          {t(`recipes.${card.id}.promise`)}
        </p>
        <p className="mt-1 truncate text-[10.5px] leading-snug tracking-[0.06em] text-meta">
          {t(`recipes.${card.id}.inputScenario`)}
        </p>
      </div>
    </div>
  )
}
