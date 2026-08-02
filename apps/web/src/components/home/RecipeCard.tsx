"use client"

import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Volume2, VolumeX, Wand2 } from "lucide-react"

import type { RecipeCard as RecipeCardData } from "@/lib/recipes"

/**
 * One recipe card (RECIPES §7.3, Opus-style gallery): a full-bleed vertical
 * (9:16) auto-playing preview with the recipe type at the top-left, an
 * inverse sound toggle circle at the top-right (one card sounds at a time —
 * the parent owns `soundingId`), and a hover-revealed bottom action — Remix
 * for live cards, a Soon pill for reserved (a promise is never clickable
 * before its capability is real). No promise copy on hover (2026-08-02).
 *
 * Remix (2026-08-01, docs/tasks/recipe-mention.md): inserts a recipe mention
 * chip into the composer — the pinned task book resolves server-side, never
 * from a client-built prior.
 */
export function RecipeCard({
  card,
  sounding,
  onToggleSound,
  onSelect,
}: {
  card: RecipeCardData
  sounding: boolean
  onToggleSound: (id: string) => void
  onSelect: (card: RecipeCardData) => void
}) {
  const { t } = useTranslation()
  const videoRef = useRef<HTMLVideoElement>(null)
  const live = card.status === "live"

  // React's `muted` prop is unreliable after mount (attribute vs property) —
  // drive it imperatively so the sound toggle always lands.
  useEffect(() => {
    if (videoRef.current) videoRef.current.muted = !sounding
  }, [sounding])

  return (
    <div
      role={live ? "button" : undefined}
      tabIndex={live ? 0 : undefined}
      onClick={() => live && onSelect(card)}
      onKeyDown={(e) => {
        if (live && (e.key === "Enter" || e.key === " ")) onSelect(card)
      }}
      className="group relative aspect-[9/16] overflow-hidden rounded-lg bg-card shadow-lg edge-glow dark:shadow-none"
    >
      <video
        ref={videoRef}
        src={card.preview.videoUrl}
        poster={card.preview.posterUrl}
        className="h-full w-full object-cover"
        autoPlay
        muted
        loop
        playsInline
      />

      {/* Top-left: recipe type; top-right: sound toggle. One overlay family
          (white/15 frosted) across title / volume / bottom actions, both
          chips h-9 so they sit on the same line. The volume rides the same
          300ms ease-out entrance as the bottom panel (stays visible while
          this card is the one sounding). */}
      <span className="absolute left-3 top-3 flex h-9 items-center rounded-md bg-white/15 px-2 text-sm font-medium text-white backdrop-blur-sm">
        {t(`recipes.${card.id}.title`)}
      </span>

      <button
        type="button"
        aria-label={sounding ? t("recipes.mute") : t("recipes.unmute")}
        onClick={(e) => {
          e.stopPropagation()
          onToggleSound(card.id)
        }}
        className={`absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-white backdrop-blur-sm transition-all duration-300 ease-out hover:bg-white/25 ${
          sounding
            ? "translate-y-0 opacity-100"
            : "pointer-events-none -translate-y-1 opacity-0 group-hover:pointer-events-auto group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:translate-y-0 group-focus-within:opacity-100"
        }`}
      >
        {sounding ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
      </button>

      {/* Hover: the centered action rises from the bottom (Remix for live
          cards, a Soon pill for reserved) over a barely-there scrim — no
          promise copy, no heavy backdrop */}
      <div className="absolute inset-x-0 bottom-0 flex translate-y-full justify-center bg-gradient-to-t from-black/40 via-black/15 to-transparent p-3 pt-8 transition-transform duration-300 ease-out group-hover:translate-y-0 group-focus-within:translate-y-0">
        {live ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onSelect(card)
            }}
            className="flex items-center gap-1.5 rounded-md bg-white/15 px-3 py-1.5 text-sm text-white backdrop-blur-sm transition-colors hover:bg-white/25"
          >
            <Wand2 className="h-3.5 w-3.5" />
            {t("recipes.remix")}
          </button>
        ) : (
          <span className="inline-flex items-center rounded-md bg-white/15 px-2.5 py-1 text-xs text-white/80 backdrop-blur-sm">
            {t("recipes.soon")}
          </span>
        )}
      </div>
    </div>
  )
}
