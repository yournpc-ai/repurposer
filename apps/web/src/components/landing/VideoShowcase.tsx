import { motion, useScroll, useTransform } from "motion/react"
import { ArrowDown, ChevronsLeftRight, Volume2, VolumeX } from "lucide-react"
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react"
import { Trans, useTranslation } from "react-i18next"

import ComparisonSlider from "@/components/landing/ComparisonSlider"
import { useReducedMotion } from "@/components/landing/motion"
import { LogoMark } from "@/components/LogoMark"
import { RECIPE_ASSETS } from "@/lib/recipes.assets"
import { cn } from "@/lib/utils"

/**
 * Before/after showcase — a REAL recipe pair from the demo tree, not a mock:
 * left is the raw 16:9 interview recording (comparison-source, cut from
 * demo/uploads/xy_1.mp4), right is the reframe recipe's actual 9:16 output
 * docked to the right edge over blurred rails. Dragging the divider is the
 * user performing the transformation themselves. Both assets are
 * content-hashed (immutable URLs, shared cache with the recipe cards).
 */
const BEFORE_VIDEO = RECIPE_ASSETS["comparison-source.mp4"]
const AFTER_VIDEO = RECIPE_ASSETS["reframe-preview.mp4"]
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

function paneChipClass(position: string): string {
  return cn(
    "pointer-events-none absolute z-10 rounded-md bg-black/55 px-3 py-1.5 text-xs font-medium whitespace-nowrap text-white/90 backdrop-blur-sm",
    position
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
  const prefersReducedMotion = useReducedMotion()
  const sectionRef = useRef<HTMLElement>(null)
  const beforeVideoRef = useRef<HTMLVideoElement>(null)
  const afterVideoRef = useRef<HTMLVideoElement>(null)
  const railsVideoRef = useRef<HTMLVideoElement>(null)
  const [viewport, setViewport] = useState({ w: 1280, h: 800 })
  const [interactive, setInteractive] = useState(false)
  const [hasDragged, setHasDragged] = useState(false)
  const [soundOn, setSoundOn] = useState(false)
  /** Which pane currently "owns" the soundtrack — follows the divider with a
   * hysteresis band (≥60% before / ≤40% after) so the idle float animation
   * can't flip the audio back and forth across the middle. */
  const dominantRef = useRef<"before" | "after">("before")

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
  // only leaves when the section does, or once the user has dragged.
  const captionOpacity = useTransform(scrollYProgress, [0.9, 0.98], [1, 0])
  const captionY = useTransform(y, (value) => NAV_OFFSET + value - 44)
  const scrollHintOpacity = useTransform(
    scrollYProgress,
    [GROWTH_END, GROWTH_END + 0.1, 0.9, 0.98],
    [0, 1, 1, 0]
  )
  // The "treatment" chrome (chips / caption / brand mark) only fades in once
  // the frame has grown — during the peek the reveal of the dressed right
  // side IS the story beat.
  const chromeOpacity = useTransform(scrollYProgress, [PLAY_AT, GROWTH_END], [0, 1])

  // Playback + drag handoff, both gated on scroll progress.
  useEffect(() => {
    if (prefersReducedMotion) return
    const videos = [
      beforeVideoRef.current,
      afterVideoRef.current,
      railsVideoRef.current,
    ].filter((v): v is HTMLVideoElement => v !== null)
    if (videos.length === 0) return

    let inView = false
    const sync = (): void => {
      const shouldPlay = inView && scrollYProgress.get() >= PLAY_AT
      setInteractive(scrollYProgress.get() >= GROWTH_END)
      for (const video of videos) {
        if (shouldPlay) {
          if (video.paused) void video.play().catch(() => undefined)
        } else if (!video.paused) {
          video.pause()
        }
      }
    }

    const observer = new IntersectionObserver(
      (entries) => {
        inView = entries[0]?.isIntersecting ?? false
        sync()
      },
      { threshold: 0 }
    )
    videos.forEach((video) => observer.observe(video))

    const unsubscribe = scrollYProgress.on("change", sync)
    return () => {
      observer.disconnect()
      unsubscribe()
    }
  }, [scrollYProgress, prefersReducedMotion])

  const applyAudio = (sound: boolean): void => {
    const dominant = dominantRef.current
    if (beforeVideoRef.current)
      beforeVideoRef.current.muted = !(sound && dominant === "before")
    if (afterVideoRef.current)
      afterVideoRef.current.muted = !(sound && dominant === "after")
    // The rails are the same clip as the after column — never let them
    // double the soundtrack.
    if (railsVideoRef.current) railsVideoRef.current.muted = true
  }

  const handlePositionChange = (position: number): void => {
    if (position >= 60) dominantRef.current = "before"
    else if (position <= 40) dominantRef.current = "after"
    applyAudio(soundOn)
  }

  const toggleSound = (): void => {
    const next = !soundOn
    setSoundOn(next)
    applyAudio(next)
  }

  const beforePane = (
    <div className="relative h-full w-full">
      <PaneVideo
        videoRef={beforeVideoRef}
        src={BEFORE_VIDEO}
        className="h-full w-full object-cover"
      />
      <span className={paneChipClass("top-4 left-4")}>
        {t("landing.comparison.beforeLabel")}
      </span>
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
      {/* The actual 9:16 output, docked to the right edge — dragging left
          reveals the raw footage while the result stays anchored. */}
      <div className="absolute top-0 right-6 aspect-[9/16] h-full shadow-2xl sm:right-10">
        <PaneVideo
          videoRef={afterVideoRef}
          src={AFTER_VIDEO}
          className="h-full w-full object-cover"
        />
        <motion.div
          className="pointer-events-none absolute inset-0"
          style={prefersReducedMotion ? undefined : { opacity: chromeOpacity }}
        >
          <div
            className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-black/70 to-transparent"
            aria-hidden="true"
          />
          <span className={paneChipClass("top-4 left-4")}>
            {t("landing.comparison.clipTitle")}
          </span>
          <span className={paneChipClass("top-4 right-4")}>
            {t("landing.comparison.afterLabel")}
          </span>
          <p className="absolute inset-x-0 bottom-6 z-10 px-6 text-center text-lg font-bold text-white drop-shadow-md sm:text-xl">
            <Trans
              i18nKey="landing.comparison.captionLine"
              components={{ y: <span className="text-yellow-300" /> }}
            />
          </p>
          <LogoMark className="absolute left-4 bottom-4 z-10 h-5 w-5 opacity-90" />
        </motion.div>
      </div>
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
            onDragStart={() => setHasDragged(true)}
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
          <motion.span
            className="flex items-center gap-2.5"
            animate={{ opacity: hasDragged ? 0 : 1 }}
            transition={{ duration: 0.3 }}
          >
            {captionLine}
          </motion.span>
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
              onDragStart={() => setHasDragged(true)}
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
