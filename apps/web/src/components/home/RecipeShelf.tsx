"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronLeft, ChevronRight, Maximize2, Volume2, VolumeX } from "lucide-react"

import { Button, buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { ShelfDemo } from "./recipeFamilies"

/** Horizontal row of playable examples for one application. */
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
  items: readonly ShelfDemo[]
  onPrefill: (prefillKey: string) => void
  /** Index of the item that carries the `home-recipes` tour anchor (the
   * Ads family's first demo card — Tour skips the step when the anchor
   * renders nothing). Demo cards stamp the anchor on their primary Use-prompt
   * button, so the spotlight names the real click target. */
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
      <div className="relative w-full min-w-0 max-w-full overflow-hidden rounded-lg bg-card p-3.5 border border-subtle">
        <div
          ref={trackRef}
          className="flex w-full min-w-0 max-w-full gap-3 overflow-x-auto no-scrollbar"
        >
          {items.length === 0 && (
            <p className="flex min-h-24 w-full items-center justify-center px-4 text-center text-sm text-muted-foreground">
              {t("recipes.shelf.emptyDemo")}
            </p>
          )}
          {items.map((demo, index) => (
            <DemoCard
              key={demo.id}
              demo={demo}
              onSelect={() => onPrefill(`recipes.shelf.demos.${demo.id}.prompt`)}
              tourAnchor={index === tourAnchorIndex}
              soundActive={soundOwner === demo.id}
              onSoundStart={onSoundStart}
              onSoundStop={onSoundStop}
            />
          ))}
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
            className="absolute left-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-card text-foreground transition-colors hover:bg-accent"
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
            className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-card text-foreground transition-colors hover:bg-accent"
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

  // Visibility gate (home 内容扩展批): with three shelves stacked, offscreen
  // videos must not keep decoding — pause below the fold, resume the loop on
  // re-entry. Sound can't survive offscreen (a paused video is silent
  // anyway), so ownership releases on exit and a resume is always muted
  // (muted play() needs no user activation); hover/focus re-arms sound.
  useEffect(() => {
    const root = rootRef.current
    const video = videoRef.current
    if (!root || !video) return
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          void video.play().catch(() => {
            // A refused resume leaves the paused frame — hover re-arms it.
          })
        } else {
          video.pause()
          if (soundActive) muteSound()
        }
      },
      { threshold: 0 },
    )
    io.observe(root)
    return () => io.disconnect()
  }, [soundActive, muteSound])

  useEffect(
    () => () => {
      onSoundStop(demo.id)
    },
    [demo.id, onSoundStop],
  )

  return (
    <div
      ref={rootRef}
      className="relative aspect-video h-44 flex-none overflow-hidden rounded-lg bg-muted sm:h-60"
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
        className="block h-full w-full cursor-pointer text-left outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-foreground/60"
      >
        <video
          ref={videoRef}
          src={demo.url}
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
            <span
              aria-hidden
              className={cn(buttonVariants({ size: "lg" }), "h-9 px-3.5 text-sm font-normal")}
            >
              {t("recipes.shelf.usePrompt")}
            </span>
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
            className="absolute bottom-2 left-2 size-9 rounded-full"
          >
            {muted ? <VolumeX className="size-4.5" /> : <Volume2 className="size-4.5" />}
          </Button>
          {/* Decorative affordance — no zoom behavior; clicks stay with the
              card's single Use-prompt action. */}
          <div
            aria-hidden
            className="pointer-events-none absolute bottom-2 right-2 flex size-9 items-center justify-center rounded-full bg-secondary text-secondary-foreground"
          >
            <Maximize2 className="size-4.5" />
          </div>
        </>
      )}
    </div>
  )
}
