import { motion, useScroll, useTransform } from "motion/react"
import { ArrowDown, ChevronsLeftRight, Volume2, VolumeX } from "lucide-react"
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react"
import { useTranslation } from "react-i18next"

import ComparisonSlider from "@/components/landing/ComparisonSlider"
import { useReducedMotion } from "@/components/landing/motion"
import { RECIPE_ASSETS } from "@/lib/recipes.assets"
import { cn } from "@/lib/utils"

/**
 * Before/after showcase — a REAL recipe pair from the demo tree, not a mock:
 * left is the raw 16:9 interview recording (comparison-source, cut from
 * demo/uploads/xy_1.mp4), right is the same interview's 9:16 reframe rendered
 * by our own Remotion pipeline (comparison-after: reframe-preview passed
 * through a hand-written clip-spec — real ASR captions with the
 * karaoke-highlight preset + title, burned in by packages/clip's <Clip>).
 * Dragging the divider is the user performing the transformation themselves.
 * Both assets are content-hashed (immutable URLs, shared cache with the
 * recipe cards).
 */
const BEFORE_VIDEO = RECIPE_ASSETS["comparison-source.mp4"]
const AFTER_VIDEO = RECIPE_ASSETS["comparison-after.mp4"]
const MAX_WIDTH = 1440

const PEEK_VISIBLE = 50
const PEEK_WIDTH = 400
const PEEK_HEIGHT = 260
/** Frame stops this far below the viewport top: the header gets 64px and the
 * caption line gets the freed strip between header and frame. */
const NAV_OFFSET = 144
const BOTTOM_GAP = 24
const GROWTH_END = 0.55
const PLAY_AT = 0.35

/** Matches the horizontal padding of sections below: px-5 / sm:px-8 / lg:px-10 */
function sectionPadding(viewportWidth: number): number {
  if (viewportWidth >= 1024) return 40
  if (viewportWidth >= 640) return 32
  return 20
}

function PaneVideo({
  videoRef,
  src,
  className,
}: {
  videoRef?: RefObject<HTMLVideoElement | null>
  src: string
  className?: string
}): ReactNode {
  return (
    <video
      ref={videoRef}
      className={cn("pointer-events-none", className)}
      src={src}
      muted
      loop
      playsInline
      preload="metadata"
      aria-hidden="true"
    />
  )
}

const PANE_CHIP_STYLE =
  "inline-flex items-center gap-1.5 rounded-md bg-black/55 px-3 py-1.5 text-xs font-medium whitespace-nowrap text-white/90 backdrop-blur-sm"

function paneChipClass(position: string): string {
  return cn("pointer-events-none absolute z-10", PANE_CHIP_STYLE, position)
}

/** A spec attribute stacked under a pane label — same chip as the label,
 * one comma-split attribute per row (user copy 2026-08-02: 横屏/双人/… vs
 * 本人竖屏镜头/有字幕/…). */
function PaneTagStack({
  tags,
  className,
}: {
  tags: string[]
  className: string
}): ReactNode {
  return (
    <div className={cn("pointer-events-none absolute z-10 flex flex-col gap-1.5", className)}>
      {tags.map((tag) => (
        <span key={tag} className={PANE_CHIP_STYLE}>
          {tag}
        </span>
      ))}
    </div>
  )
}

/**
 * The comparison peeks out from under the hero and grows to section width as
 * you scroll. Playback is gated on visibility + scroll progress; dragging is
 * handed to the user only once the frame has fully grown (before that the
 * sticky layer stays pointer-transparent). Reduced motion gets a static,
 * draggable-on-demand layout.
 */
export function VideoShowcase(): ReactNode {
  const { t } = useTranslation()
  const beforeTags = t("landing.comparison.beforeTags", {
    returnObjects: true,
  }) as string[]
  const afterTags = t("landing.comparison.afterTags", {
    returnObjects: true,
  }) as string[]
  const prefersReducedMotion = useReducedMotion()
  const sectionRef = useRef<HTMLElement>(null)
  const beforeVideoRef = useRef<HTMLVideoElement>(null)
  const afterVideoRef = useRef<HTMLVideoElement>(null)
  const railsVideoRef = useRef<HTMLVideoElement>(null)
  const [viewport, setViewport] = useState({ w: 1280, h: 800 })
  const [interactive, setInteractive] = useState(false)
  const [soundOn, setSoundOn] = useState(false)
  /** Live mirror of soundOn for the audio gate. The slider's Draggable is
   * created once (useGSAP deps exclude callbacks), so its onPositionChange
   * closure freezes the FIRST render's `soundOn` — reading state there would
   * re-mute right after every unmute. Refs stay live; state stays for UI. */
  const soundOnRef = useRef(false)
  /** Which pane currently "owns" being live (playback + soundtrack) —
   * follows the divider with a hysteresis band (≥60% before / ≤40% after)
   * so the idle float animation can't flip it back and forth across the
   * middle. Initial: the RESULT side — it's the hero of the section (and
   * the clear-voice first impression when unmuted). */
  const dominantRef = useRef<"before" | "after">("after")
  /** UI mirror of dominantRef (the ref serves the Draggable's frozen
   * closures; this state drives the sounding-side indicator on the label
   * chips — the visible answer to "which side's audio is live?"). */
  const [dominant, setDominant] = useState<"before" | "after">("after")

  useEffect(() => {
    const update = (): void =>
      setViewport({ w: window.innerWidth, h: window.innerHeight })
    update()
    window.addEventListener("resize", update)
    return () => window.removeEventListener("resize", update)
  }, [])

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end end"],
  })

  const fullWidth =
    Math.min(viewport.w, MAX_WIDTH) - sectionPadding(viewport.w) * 2
  const fullHeight = viewport.h - NAV_OFFSET - BOTTOM_GAP
  const peekY = viewport.h - PEEK_VISIBLE - NAV_OFFSET

  const width = useTransform(
    scrollYProgress,
    [0, GROWTH_END],
    [PEEK_WIDTH, fullWidth]
  )
  const height = useTransform(
    scrollYProgress,
    [0, GROWTH_END],
    [PEEK_HEIGHT, fullHeight]
  )
  const y = useTransform(scrollYProgress, [0, GROWTH_END], [peekY, 0])
  // The caption line rides 44px above the frame's top edge: in the peek it's
  // the tease, once grown it sits in the freed strip below the header — it
  // only leaves as the section releases (fade starts late, at 94%).
  const captionOpacity = useTransform(scrollYProgress, [0.94, 1], [1, 0])
  const captionY = useTransform(y, (value) => NAV_OFFSET + value - 44)
  const scrollHintOpacity = useTransform(
    scrollYProgress,
    [GROWTH_END, GROWTH_END + 0.1, 0.94, 1],
    [0, 1, 1, 0]
  )
  // The "treatment" chrome (pane labels / tag stacks / sound toggle) is
  // resident, not a scroll effect: it snaps in the moment the frame
  // finishes growing and stays fully opaque until the section scrolls
  // away — the same posture as the SCROLL DOWN pill, never a
  // scroll-coupled fade.
  const chromeOpacity = useTransform(scrollYProgress, (value) =>
    value >= GROWTH_END ? 1 : 0
  )

  /** Re-assert playback + interactivity. Wired to scroll, visibility AND
   * slider drag events: the browser can system-pause a video the divider has
   * fully clipped away, and only a user-gesture-context play() reliably
   * resumes it — drag start/end are gestures, scroll ticks are not (their
   * rejected promises are swallowed, leaving a frozen pane). */
  const inViewRef = useRef(false)
  /** Which panes may play: ONLY the dominant side (the one with the bigger
   * visible share) — the squeezed side freezes instead of spinning
   * pointlessly. Mirrors the single-soundtrack model exactly: one live
   * pane, and it's the same pane that owns the audio. (Replaces the 40–60
   * middle band where both played — the float swinging the divider made
   * "Raw 占大头" and "result still playing" visibly contradict.) */
  const playGateRef = useRef({ before: false, after: true })
  const syncPlayback = (): void => {
    const progress = scrollYProgress.get()
    const shouldPlay = inViewRef.current && progress >= PLAY_AT
    setInteractive(progress >= GROWTH_END)
    const gates = playGateRef.current
    const targets: [RefObject<HTMLVideoElement | null>, boolean][] = [
      [beforeVideoRef, gates.before],
      [afterVideoRef, gates.after],
      [railsVideoRef, gates.after],
    ]
    for (const [ref, allowed] of targets) {
      const video = ref.current
      if (!video) continue
      if (shouldPlay && allowed) {
        if (video.paused) void video.play().catch(() => undefined)
      } else if (!video.paused) {
        video.pause()
      }
    }
  }

  // Playback + drag handoff, both gated on scroll progress.
  useEffect(() => {
    if (prefersReducedMotion) return
    const videos = [
      beforeVideoRef.current,
      afterVideoRef.current,
      railsVideoRef.current,
    ].filter((v): v is HTMLVideoElement => v !== null)
    if (videos.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        inViewRef.current = entries[0]?.isIntersecting ?? false
        syncPlayback()
      },
      { threshold: 0 }
    )
    videos.forEach((video) => observer.observe(video))

    const unsubscribe = scrollYProgress.on("change", syncPlayback)
    return () => {
      observer.disconnect()
      unsubscribe()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollYProgress, prefersReducedMotion])

  const applyAudio = (): void => {
    const sound = soundOnRef.current
    const dominant = dominantRef.current
    if (beforeVideoRef.current)
      beforeVideoRef.current.muted = !(sound && dominant === "before")
    if (afterVideoRef.current)
      afterVideoRef.current.muted = !(sound && dominant === "after")
    // The rails are the same clip as the after column — never let them
    // double the soundtrack.
    if (railsVideoRef.current) railsVideoRef.current.muted = true
  }

  // Post-commit re-assert (RecipeCard's proven pattern): React's `muted`
  // prop is unreliable after mount, and HMR / element remounts reset it —
  // re-drive the property from the live refs after every commit.
  useEffect(() => {
    applyAudio()
  })

  const handlePositionChange = (position: number): void => {
    if (position >= 60) {
      dominantRef.current = "before"
      setDominant("before")
    } else if (position <= 40) {
      dominantRef.current = "after"
      setDominant("after")
    }
    // Only the dominant pane plays — the squeezed side freezes (same
    // hysteresis as the soundtrack, so live pane == sounding pane).
    playGateRef.current = {
      before: dominantRef.current === "before",
      after: dominantRef.current === "after",
    }
    applyAudio()
    syncPlayback()
  }

  const toggleSound = (): void => {
    const next = !soundOn
    soundOnRef.current = next
    setSoundOn(next)
    applyAudio()
  }

  const beforePane = (
    <div className="relative h-full w-full">
      <PaneVideo
        videoRef={beforeVideoRef}
        src={BEFORE_VIDEO}
        className="h-full w-full object-cover"
      />
      {/* Same chromeOpacity choreography as the after side — both labels
          fade in together once the frame has grown. */}
      <motion.div
        className="pointer-events-none absolute inset-0"
        style={prefersReducedMotion ? undefined : { opacity: chromeOpacity }}
      >
        <span className={paneChipClass("top-4 left-4")}>
          {soundOn && dominant === "before" && (
            <Volume2 className="h-3 w-3" aria-hidden="true" />
          )}
          {t("landing.comparison.beforeLabel")}
        </span>
        <PaneTagStack tags={beforeTags} className="top-12 left-4 items-start" />
      </motion.div>
    </div>
  )

  const afterPane = (
    <div className="relative h-full w-full bg-black">
      {/* Blurred rails: the same clip scaled to cover, so the vertical column
          reads as the artifact and the pane stays full-bleed. */}
      <PaneVideo
        videoRef={railsVideoRef}
        src={AFTER_VIDEO}
        className="absolute inset-0 h-full w-full scale-110 object-cover blur-2xl brightness-[0.55]"
      />
      {/* The actual 9:16 output, centered in the right half (75% mark): at
          the resting 50% divider the column sits with equal dark rails on
          both flanks — a framed artifact, not a void beside a sliver. The
          captions/title are burned into the video itself (real render), so
          there is no DOM dressing on the column. */}
      <div className="absolute top-0 left-3/4 aspect-[9/16] h-full -translate-x-1/2 shadow-2xl">
        <PaneVideo
          videoRef={afterVideoRef}
          src={AFTER_VIDEO}
          className="h-full w-full object-cover"
        />
      </div>
      {/* The after label anchors to the FRAME's top-right corner — mirroring
          the before label at the frame's top-left, not the column's. */}
      <motion.div
        className="pointer-events-none absolute inset-0"
        style={prefersReducedMotion ? undefined : { opacity: chromeOpacity }}
      >
        <span className={paneChipClass("top-4 right-4")}>
          {soundOn && dominant === "after" && (
            <Volume2 className="h-3 w-3" aria-hidden="true" />
          )}
          {t("landing.comparison.afterLabel")}
        </span>
        <PaneTagStack tags={afterTags} className="top-12 right-4 items-end" />
      </motion.div>
    </div>
  )

  const captionLine = (
    <>
      <ChevronsLeftRight className="size-3.5" aria-hidden="true" />
      {t("landing.comparison.caption")}
    </>
  )

  if (prefersReducedMotion) {
    return (
      <section
        id="features"
        aria-label={t("landing.comparison.ariaLabel")}
        className="flex min-h-svh flex-col items-center justify-center gap-8 px-6 py-24"
      >
        <p className="flex items-center gap-2.5 text-sm font-medium text-foreground">
          {captionLine}
        </p>
        <div
          className="relative w-full overflow-hidden rounded-3xl bg-black"
          style={{ maxWidth: MAX_WIDTH, aspectRatio: "16 / 9" }}
        >
          <ComparisonSlider
            beforeChildren={beforePane}
            afterChildren={afterPane}
            reducedMotion
            ariaLabel={t("landing.comparison.ariaLabel")}
            className="rounded-none shadow-none"
          />
        </div>
      </section>
    )
  }

  return (
    <section
      ref={sectionRef}
      id="features"
      aria-label={t("landing.comparison.ariaLabel")}
      className="pointer-events-none relative z-20 [margin-top:-100svh] h-[180svh]"
    >
      <div className="sticky top-0 h-svh overflow-hidden">
        <motion.p
          style={{ x: "-50%", y: captionY, opacity: captionOpacity }}
          className="absolute top-0 left-1/2 flex items-center gap-2.5 text-xs font-medium whitespace-nowrap text-foreground"
        >
          {captionLine}
        </motion.p>

        <motion.div
          style={{ x: "-50%", y, top: NAV_OFFSET, width, height }}
          className="absolute left-1/2 overflow-hidden rounded-3xl bg-black"
        >
          <div
            className={cn(
              "h-full w-full",
              interactive ? "pointer-events-auto" : "pointer-events-none"
            )}
          >
            <ComparisonSlider
              beforeChildren={beforePane}
              afterChildren={afterPane}
              autoAnimate
              onDragStart={syncPlayback}
              onDragEnd={syncPlayback}
              onPositionChange={handlePositionChange}
              ariaLabel={t("landing.comparison.ariaLabel")}
              className="rounded-none shadow-none"
            />
            <motion.button
              type="button"
              onClick={toggleSound}
              style={{ opacity: chromeOpacity }}
              className="absolute right-5 bottom-5 z-20 grid h-9 w-9 place-items-center rounded-full bg-black/55 text-white/90 backdrop-blur-sm transition-colors hover:bg-black/70"
              aria-label={
                soundOn
                  ? t("landing.comparison.mute")
                  : t("landing.comparison.unmute")
              }
            >
              {soundOn ? (
                <Volume2 className="h-4 w-4" aria-hidden="true" />
              ) : (
                <VolumeX className="h-4 w-4" aria-hidden="true" />
              )}
            </motion.button>
          </div>
          <motion.div
            style={{ opacity: scrollHintOpacity }}
            aria-hidden="true"
            className="absolute bottom-5 left-5 flex items-center gap-2 rounded-full bg-black/55 py-2 pr-3 pl-4 text-white/90"
          >
            <span className="text-[11px] font-medium tracking-wider uppercase">
              {t("landing.comparison.scrollDown")}
            </span>
            <motion.span
              animate={{ y: [0, 3, 0] }}
              transition={{
                duration: 1.8,
                repeat: Infinity,
                ease: "easeInOut",
              }}
            >
              <ArrowDown className="size-3.5" strokeWidth={1.5} aria-hidden="true" />
            </motion.span>
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}
