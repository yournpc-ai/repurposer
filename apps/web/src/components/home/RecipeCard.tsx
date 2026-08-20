"use client"

import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Maximize2, Volume2, VolumeX, Wand2 } from "lucide-react"

import type { RecipeCard as RecipeCardData } from "@/lib/recipes"

/**
 * One recipe card — poster-first state machine (ADR-046 D4):
 *   rest  = the poster (capability chip top-left, aspect badge bottom-left,
 *           NO autoplay — the gallery is still until asked);
 *   hover = the teaser plays WITH SOUND (2026-08-21 ruling — sound is the
 *           default, not a toggle away). The browser gesture policy is the
 *           only gate: an unmuted play() that rejects (no prior user
 *           activation) falls back to muted and the toggle reflects it —
 *           any click on the page (the toggle itself included) grants
 *           activation, so sound works from the next hover on. Hover also
 *           raises the ACTION TRIO (MiniMax anatomy): sound toggle takes
 *           the aspect badge's bottom-left slot, a white stadium Remix pill
 *           centers, an expand button sits bottom-right — Remix and expand
 *           open the same inspect overlay (no quick-launch, ADR-040);
 *   click = the RecipeInspectOverlay (the ONLY launch path — the launch
 *           zone lives inside; hover never launches anything).
 * The tile's aspect comes from the poster's real pixels (registry w/h), so
 * any-shaped asset fills exactly — no letterboxing, no forced 9:16 slot.
 * Reserved cards carry a Soon pill in the caption and never play.
 *
 * The caption stays UNDER the tile (title + promise — the dish explains
 * itself at rest, no hover needed to read it).
 */
export function RecipeCard({
  card,
  onInspect,
}: {
  card: RecipeCardData
  onInspect: (card: RecipeCardData) => void
}) {
  const { t } = useTranslation()
  const videoRef = useRef<HTMLVideoElement>(null)
  const live = card.status === "live"
  const playable = Boolean(card.preview.videoUrl)
  const [hovering, setHovering] = useState(false)
  // Sound: user intent (default ON) vs the EFFECTIVE audible state (the
  // policy fallback flips it until the first click anywhere).
  const [muteIntent, setMuteIntent] = useState(false)
  const [muted, setMuted] = useState(false)

  // Hover play: nothing loads at rest (preload="none"); the teaser loads on
  // first hover, pauses and hides on leave (the poster returns). Sound first,
  // muted fallback — React's `muted` prop is unreliable after mount
  // (attribute vs property), so drive it imperatively.
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (hovering && playable) {
      video.muted = muteIntent
      setMuted(muteIntent)
      video.play().catch(() => {
        // Autoplay policy (no activation yet) — retry muted; the toggle
        // shows the fallback. A later click unlocks sound.
        video.muted = true
        setMuted(true)
        video.play().catch(() => {
          // Codec edge — the poster simply stays.
        })
      })
    } else {
      video.pause()
    }
  }, [hovering, playable, muteIntent])

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
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      className={`group flex flex-col gap-2.5 outline-none ${live ? "cursor-pointer" : ""}`}
    >
      <div
        className="relative overflow-hidden rounded-lg bg-muted"
        style={{ aspectRatio: `${card.preview.w} / ${card.preview.h}` }}
      >
        {/* Rest layer: the poster (media content is its own separation —
            no ring, no shadow, no chrome). */}
        <img
          src={card.preview.posterUrl}
          alt={t(`recipes.${card.id}.title`)}
          loading="lazy"
          className="absolute inset-0 h-full w-full object-cover"
        />

        {/* Hover layer: the teaser (same ratio as the poster — exact fill).
            Mounts only for cards that have a preview video. */}
        {playable && (
          <video
            ref={videoRef}
            src={card.preview.videoUrl}
            className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-200 ${
              hovering ? "opacity-100" : "opacity-0"
            }`}
            preload="none"
            muted
            loop
            playsInline
          />
        )}

        {/* Capability chip (top-left): the card's first tag is its capability
            mark — the MiniMax ribbon role. On-media text is constant white
            (it follows the media, not the theme). */}
        {card.tags.length > 0 && (
          <span className="absolute left-2.5 top-2.5 rounded-md bg-black/35 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm">
            {t(`recipes.tags.${card.tags[0]}`)}
          </span>
        )}

        {/* Aspect badge (bottom-left): the output's shape, stated on the
            face (画幅跟源). Rest chrome — on hover its slot TRANSFORMS into
            the sound toggle (MiniMax anatomy: the badge is rest-only). */}
        <span
          className={`absolute bottom-2.5 left-2.5 rounded-md bg-black/35 px-1.5 py-0.5 text-[10px] tabular-nums text-white backdrop-blur-sm transition-opacity duration-200 ${
            hovering && playable ? "opacity-0" : "opacity-100"
          }`}
        >
          {card.aspect}
        </span>

        {/* Hover chrome (MiniMax anatomy, 2026-08-21 walkthrough): the scrim
            plus an action trio — sound toggle bottom-LEFT (takes the aspect
            badge's slot), a white stadium Remix pill at CENTER, an expand
            button bottom-RIGHT. Remix and expand both open the inspect
            overlay — the ONLY launch path (ADR-040); hover never launches. */}
        {playable && (
          <>
            <div
              className={`pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/45 to-transparent transition-opacity duration-200 ${
                hovering ? "opacity-100" : "opacity-0"
              }`}
            />
            <button
              type="button"
              aria-label={muted ? t("recipes.unmute") : t("recipes.mute")}
              tabIndex={hovering ? 0 : -1}
              onClick={(e) => {
                e.stopPropagation()
                setMuteIntent((v) => !v)
              }}
              className={`absolute bottom-2.5 left-2.5 flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-white backdrop-blur-sm transition-all duration-200 hover:bg-white/25 ${
                hovering
                  ? "translate-y-0 opacity-100"
                  : "pointer-events-none translate-y-1 opacity-0"
              }`}
            >
              {muted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
            </button>
            <button
              type="button"
              tabIndex={hovering ? 0 : -1}
              onClick={(e) => {
                e.stopPropagation()
                onInspect(card)
              }}
              className={`absolute left-1/2 top-1/2 flex h-10 -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 rounded-full bg-white/90 px-5 text-sm font-medium text-black shadow-lg transition-all duration-200 hover:bg-white ${
                hovering
                  ? "scale-100 opacity-100"
                  : "pointer-events-none scale-95 opacity-0"
              }`}
            >
              <Wand2 className="h-4 w-4" />
              {t("recipes.remix")}
            </button>
            <button
              type="button"
              aria-label={t("recipes.expand")}
              tabIndex={hovering ? 0 : -1}
              onClick={(e) => {
                e.stopPropagation()
                onInspect(card)
              }}
              className={`absolute bottom-2.5 right-2.5 flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-white backdrop-blur-sm transition-all duration-200 hover:bg-white/25 ${
                hovering
                  ? "translate-y-0 opacity-100"
                  : "pointer-events-none translate-y-1 opacity-0"
              }`}
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          </>
        )}
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
