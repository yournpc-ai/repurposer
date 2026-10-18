"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronLeft, ChevronRight, Maximize2, Volume2, VolumeX } from "lucide-react"

import { RecipeCard } from "@/components/home/RecipeCard"
import { Button } from "@/components/ui/button"
import type { ShelfDemo, ShelfItem } from "./recipeFamilies"

/**
 * 横滑货架 (D5, prototype 屏① .shelf): one shelf = a title + a white
 * container (bg-card, 发丝线, rounded-lg — in-flow surface, NO shadow)
 * holding a horizontal scroll track (no-scrollbar). Cards:
 * - recipe items reuse RecipeCard (the schematic cover + three text rows);
 * - demo items are real rendered videos, autoplay loop/muted; hover/focus
 *   shows the action veil and claims the home-global sound singleton.
 *
 * Click 唯一归宿 = composer 预填 (D5 禁则 8): every card hands its
 * `prefillKey` up; the shelf itself never navigates and never opens any
 * template-editing surface.
 *
 * The ‹ › pagers are honest chrome (禁死按钮): each renders ONLY while there
 * is more to page to in its direction, one viewport-ish step per click.
 * Circular icon buttons = the rounded-full law's first exception; same-fill
 * boundary on the white shelf = the hairline ring's legal seat.
 */
export function RecipeShelf({
  title,
  items,
  onPrefill,
  tourAnchorIndex,
  soundOwner,
  onSoundStart,
  onSoundStop,
}: {
  title: string
  items: ShelfItem[]
  onPrefill: (prefillKey: string) => void
  /** Index of the item that carries the `home-recipes` tour anchor (the
   * Ads family's launch-film demo card — Tour skips the step when the
   * anchor renders nothing). Demo cards stamp the anchor on their primary
   * Use-prompt button, so the spotlight names the real click target. */
  tourAnchorIndex?: number
  /** Home-global audible demo id. Videos keep playing when ownership moves;
   * only their sound is revoked. */
  soundOwner: string | null
  onSoundStart: (id: string) => void
  onSoundStop: (id: string) => void
}) {
  const { t } = useTranslation()
  const trackRef = useRef<HTMLDivElement>(null)
  const [canPageBack, setCanPageBack] = useState(false)
  const [canPageForward, setCanPageForward] = useState(false)

  // SSR-safe: measurement lives in an effect; the first paint simply has
  // no pager (it appears once the track reports overflow).
  useEffect(() => {
    const el = trackRef.current
    if (!el) return
    const update = () => {
      setCanPageBack(el.scrollLeft > 8)
      setCanPageForward(el.scrollWidth - el.clientWidth - el.scrollLeft > 8)
    }
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
    <section className="w-full min-w-0 max-w-full">
      <h3 className="mb-2.5 text-base font-medium">{title}</h3>
      <div className="relative w-full min-w-0 max-w-full overflow-hidden rounded-lg bg-card p-3.5 ring-1 ring-foreground/10">
        <div
          ref={trackRef}
          className="flex w-full min-w-0 max-w-full gap-3 overflow-x-auto no-scrollbar"
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
              // data-tour mirror of the recipe branch — tour step 3 anchors
              // the Ads family's launch-film demo card (home 默认 tab
              // 旗舰). Demo cards put the anchor on the primary Use-prompt
              // button, not the decorative wrapper.
              <div key={item.demo.id} className="flex-none">
                <DemoCard
                  demo={item.demo}
                  onSelect={() => onPrefill(item.prefillKey)}
                  tourAnchor={index === tourAnchorIndex}
                  soundActive={soundOwner === item.demo.id}
                  onSoundStart={onSoundStart}
                  onSoundStop={onSoundStop}
                />
              </div>
            ),
          )}
        </div>
        {canPageBack && (
          <button
            type="button"
            aria-label={t("recipes.shelf.previousPage")}
            onClick={() =>
              trackRef.current?.scrollBy({
                left: -(trackRef.current.clientWidth ?? 320) * 0.85,
                behavior: "smooth",
              })
            }
            className="absolute left-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-card text-foreground ring-1 ring-foreground/10 transition-colors hover:bg-accent"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
        )}
        {canPageForward && (
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

/** One MG demo card: the real render IS the card face. Rest = autoplaying
 * muted loop with no chrome; hover/focus = a translucent gray veil with the
 * card's one action (use the prompt), sound, and a decorative expand mark.
 * Claiming sound unmutes this card and mutes the previous owner WITHOUT
 * pausing it. If the browser refuses unmuted hover playback, the card falls
 * back to muted autoplay and the sound button's real click can unlock audio. */
function DemoCard({
  demo,
  onSelect,
  tourAnchor = false,
  soundActive,
  onSoundStart,
  onSoundStop,
}: {
  demo: ShelfDemo
  onSelect: () => void
  /** Tour step 3 anchors this card's always-rendered primary select button —
   * the visible Use-prompt overlay only mounts on hover/focus. */
  tourAnchor?: boolean
  soundActive: boolean
  onSoundStart: (id: string) => void
  onSoundStop: (id: string) => void
}) {
  const { t } = useTranslation()
  const rootRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [controlsVisible, setControlsVisible] = useState(false)
  const [muted, setMuted] = useState(true)

  const muteSound = useCallback(() => {
    const video = videoRef.current
    if (video) video.muted = true
    setMuted(true)
    onSoundStop(demo.id)
  }, [demo.id, onSoundStop])

  const enableSound = useCallback(async () => {
    const video = videoRef.current
    if (!video) return
    onSoundStart(demo.id)
    video.volume = 1
    video.muted = false
    // Always re-assert play() after unmuting: if the browser treats the
    // hover unmute as blocked audible autoplay and pauses the loop, this is
    // the one place that can catch it. A rejected attempt falls back to the
    // muted loop; a real click on the sound button supplies activation.
    try {
      await video.play()
    } catch {
      video.muted = true
      setMuted(true)
      try {
        await video.play()
      } catch {
        // The paused frame is preferable to a broken hover.
      }
      onSoundStop(demo.id)
      return
    }
    setMuted(video.muted)
    if (video.muted) onSoundStop(demo.id)
  }, [demo.id, onSoundStart, onSoundStop])

  const deactivate = useCallback(() => {
    setControlsVisible(false)
    muteSound()
  }, [muteSound])

  const handleSelect = useCallback(() => {
    deactivate()
    onSelect()
  }, [deactivate, onSelect])

  const toggleSound = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    if (video.muted) void enableSound()
    else muteSound()
  }, [enableSound, muteSound])

  // Losing the home-global sound ownership revokes ONLY the sound — the
  // muted autoplay loop continues behind the next card's audio.
  useEffect(() => {
    if (soundActive) return
    const video = videoRef.current
    if (video) video.muted = true
    setMuted(true)
  }, [soundActive])

  useEffect(
    () => () => {
      onSoundStop(demo.id)
    },
    [demo.id, onSoundStop],
  )

  return (
    <div
      ref={rootRef}
      className={`relative h-60 flex-none overflow-hidden rounded-lg ${
        demo.orientation === "vertical" ? "aspect-[3/4]" : "aspect-video"
      }`}
      onPointerEnter={(event) => {
        if (event.pointerType !== "mouse") return
        setControlsVisible(true)
        void enableSound()
      }}
      onPointerLeave={() => {
        // Keyboard focus keeps the controls reachable; sound still leaves
        // with the pointer while the video keeps playing.
        if (rootRef.current?.contains(document.activeElement)) {
          muteSound()
          return
        }
        deactivate()
      }}
      onFocus={() => {
        setControlsVisible(true)
        void enableSound()
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          deactivate()
      }}
    >
      <button
        type="button"
        onClick={handleSelect}
        aria-label={t("recipes.shelf.usePrompt")}
        data-tour={tourAnchor ? "home-recipes" : undefined}
        className="block h-full w-full cursor-pointer text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
      >
        <video
          ref={videoRef}
          src={demo.url}
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          onVolumeChange={(event) => setMuted(event.currentTarget.muted)}
          className="h-full w-full object-cover"
        />
      </button>

      {controlsVisible && (
        <>
          <div
            aria-hidden
            className="media-scrim pointer-events-none absolute inset-0 rounded-[inherit]"
          />
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <Button
              type="button"
              variant="secondary"
              size="lg"
              onClick={handleSelect}
              className="pointer-events-auto h-9 px-3.5 text-sm font-normal ring-1 ring-foreground/10"
            >
              {t("recipes.shelf.usePrompt")}
            </Button>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="icon-lg"
            aria-label={muted ? t("recipes.shelf.playSound") : t("recipes.shelf.mute")}
            aria-pressed={!muted}
            onClick={(event) => {
              event.stopPropagation()
              toggleSound()
            }}
            className="absolute bottom-2 left-2 size-9 rounded-full ring-1 ring-foreground/10"
          >
            {muted ? <VolumeX className="size-4.5" /> : <Volume2 className="size-4.5" />}
          </Button>
          {/* Decorative affordance — no zoom behavior; clicks stay with the
              card's single Use-prompt action. */}
          <div
            aria-hidden
            className="pointer-events-none absolute bottom-2 right-2 flex size-9 items-center justify-center rounded-full bg-secondary text-secondary-foreground ring-1 ring-foreground/10"
          >
            <Maximize2 className="size-4.5" />
          </div>
        </>
      )}
    </div>
  )
}
