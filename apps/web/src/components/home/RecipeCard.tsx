"use client"

import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Volume2, VolumeX, Wand2 } from "lucide-react"

import type { RecipeCard as RecipeCardData } from "@/lib/recipes"

/**
 * One recipe card (RECIPES §7.3, Opus-style gallery): a full-bleed vertical
 * (9:16) auto-playing preview with the recipe type at the top-left, an
 * inverse sound toggle circle at the top-right (one card sounds at a time —
 * the parent owns `soundingId`), and a hover-revealed bottom panel carrying
 * the promise + the Remix action (reserved cards show a Soon pill instead —
 * a promise is never clickable before its capability is real).
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

      {/* Top-left: recipe type */}
      <span className="absolute left-3 top-3 text-sm font-medium text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]">
        {t(`recipes.${card.id}.title`)}
      </span>

      {/* Top-right: inverse sound toggle */}
      <button
        type="button"
        aria-label={sounding ? t("recipes.mute") : t("recipes.unmute")}
        onClick={(e) => {
          e.stopPropagation()
          onToggleSound(card.id)
        }}
        className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-black/60 text-white backdrop-blur-sm transition-colors hover:bg-black/80"
      >
        {sounding ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
      </button>

      {/* Hover: promise + action rise from the bottom */}
      <div className="absolute inset-x-0 bottom-0 translate-y-full bg-gradient-to-t from-black/80 via-black/50 to-transparent p-3 pt-10 transition-transform duration-300 ease-out group-hover:translate-y-0 group-focus-within:translate-y-0">
        <p className="mb-2.5 text-sm leading-snug text-white/90">
          {t(`recipes.${card.id}.promise`)}
        </p>
        {live ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onSelect(card)
            }}
            className="flex items-center gap-1.5 rounded-md bg-white/90 px-3 py-1.5 text-sm text-black transition-colors hover:bg-white"
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
