"use client"

import { useTranslation } from "react-i18next"
import { Maximize2 } from "lucide-react"

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
 * Hover state machine (MiniMax anatomy, second pass 2026-08-23; Remix pill
 * retired 2026-08-31 — the whole card is clickable (cursor-pointer) and the
 * expand icon already affords the overlay, so the centered pill only
 * occluded the schematic, which IS the card face):
 *   rest  = the schematic (static, no chrome) — title + promise + input
 *           row always readable under the tile;
 *   hover = the schematic plays its process animation (see styles.css
 *           `rc-*` keyframes, gated by `.group:hover`); an expand
 *           icon-button sits top-right — the tile stays uncovered;
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
      {/* The tile — bg-card RAISED surface on the gray page (light 0.96 →
          white 1.0, dark 0.12 → 0.21 panel; the elevation fill step, ADR-046),
          no ring, no shadow. 2026-08-31 user ruling: the covers go white now
          that the page itself carries the gray underlay (was bg-inset well).
          16:10 carries the schematic; the inline SVG is the only content. */}
      <div className="relative aspect-[16/10] overflow-hidden rounded-lg bg-card text-foreground">
        {Cover ? (
          <Cover />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
            {card.id}
          </div>
        )}

        {/* Hover chrome — ONLY the expand icon top-right (2026-08-31 user
            ruling: cursor-pointer + this affordance express clickability;
            the retired centered Remix pill occluded the schematic, which IS
            the card face). Opens the same overlay as the card click
            (ADR-040). Reserved cards stay non-launchable: no chrome, no
            click. The chip uses the bg-accent token step on the white
            tile. */}
        {live && (
          <button
            type="button"
            tabIndex={-1}
            aria-label={t("recipes.expand")}
            onClick={(e) => {
              e.stopPropagation()
              onInspect(card)
            }}
            className="pointer-events-none absolute right-2.5 top-2.5 flex h-8 w-8 scale-90 items-center justify-center rounded-md bg-accent text-foreground opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:scale-100 group-hover:opacity-100"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
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
