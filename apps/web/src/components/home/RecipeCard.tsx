"use client"

import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Volume2, VolumeX } from "lucide-react"

import type { RecipeCard as RecipeCardData } from "@/lib/recipes"

/**
 * One recipe card (RECIPES §7.3, 2026-08-10 caption form): a full-bleed
 * vertical (9:16) auto-playing teaser with an inverse sound toggle circle at
 * the top-right (one card sounds at a time — the parent owns `soundingId`),
 * and a caption UNDER the video — title + promise (the ElevenCreative card
 * anatomy: the dish explains itself beneath the teaser, no hover action).
 * Reserved cards carry a Soon pill in the caption — a promise is never
 * clickable before its capability is real.
 *
 * Every live-card click opens the RecipeInspectOverlay (the launch zone
 * lives inside; the composer keeps only the manual @-mention path).
 */
export function RecipeCard({
  card,
  sounding,
  onToggleSound,
  onInspect,
}: {
  card: RecipeCardData
  sounding: boolean
  onToggleSound: (id: string) => void
  onInspect: (card: RecipeCardData) => void
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
      onClick={() => live && onInspect(card)}
      onKeyDown={(e) => {
        if (live && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault() // Space would otherwise scroll the page
          onInspect(card)
        }
      }}
      className={`group flex flex-col gap-2.5 outline-none ${live ? "cursor-pointer" : ""}`}
    >
      <div className="relative aspect-[9/16] overflow-hidden rounded-lg bg-card shadow-lg edge-glow">
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

        {/* Top-right sound toggle: hover-revealed, one card sounds at a
            time. Rides a 300ms ease-out entrance. */}
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
      </div>

      {/* Caption: the dish explains itself — title + promise; reserved cards
          pin the Soon pill next to the title. */}
      <div className="px-0.5">
        <div className="flex items-center gap-1.5">
          <p className="text-sm font-medium">{t(`recipes.${card.id}.title`)}</p>
          {!live && (
            <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
              {t("recipes.soon")}
            </span>
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
          {t(`recipes.${card.id}.promise`)}
        </p>
      </div>
    </div>
  )
}
