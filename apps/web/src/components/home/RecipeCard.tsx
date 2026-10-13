"use client"

import { useTranslation } from "react-i18next"

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
 * Click contract (D5, flora-parity-ui 批 — 卡片点击唯一归宿 = composer
 * 预填, 永不是模板编辑器): a live card's click hands the card up for a
 * composer prefill — the recipe's behavioral payload is its prompt
 * template alone (配方 = 提示词, ADR-040), and the composer's send path is
 * the only launch path. The inspect overlay is retired. Reserved cards
 * stay non-launchable (Soon pill, no click, no chrome).
 *
 * Color law: the cover's `text-foreground` color governs the schematic;
 * `prefers-reduced-motion` disables every animation (the rest geometry
 * remains legible on its own).
 */
export function RecipeCard({
  card,
  onSelect,
}: {
  card: RecipePublic
  onSelect: (card: RecipePublic) => void
}) {
  const { t } = useTranslation()
  const Cover = recipeCovers[card.id]
  const live = card.status === "live"

  return (
    <div
      role={live ? "button" : undefined}
      tabIndex={live ? 0 : undefined}
      onClick={() => live && onSelect(card)}
      onKeyDown={(e) => {
        if (live && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault() // Space would otherwise scroll the page
          onSelect(card)
        }
      }}
      className={`group flex flex-col gap-2.5 outline-none ${
        live ? "cursor-pointer" : ""
      }`}
    >
      {/* The tile — white card on the white shelf, separated by the base
          hairline alone (no shadow: in-flow surface). 16:10 carries the
          schematic; the inline SVG is the only content. Hover plays the
          schematic's process animation (styles.css `rc-*` keyframes, gated
          by `.group:hover`) — the tile carries no chrome. */}
      <div className="relative aspect-[16/10] overflow-hidden rounded-lg bg-card text-foreground ring-1 ring-foreground/10">
        {Cover ? (
          <Cover />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
            {card.id}
          </div>
        )}
      </div>

      {/* Three rows under the tile: title (with optional Soon pill for
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
        <p className="mt-1.5 line-clamp-2 min-h-10 text-xs leading-relaxed text-muted-foreground">
          {t(`recipes.${card.id}.promise`)}
        </p>
        <p className="mt-2 truncate text-[10.5px] leading-snug tracking-[0.06em] text-meta">
          {t(`recipes.${card.id}.inputScenario`)}
        </p>
      </div>
    </div>
  )
}
