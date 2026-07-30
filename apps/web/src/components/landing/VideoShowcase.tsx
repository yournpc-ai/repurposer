import { motion, useScroll, useTransform } from "motion/react"
import { ArrowDown, Play } from "lucide-react"
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react"
import { useTranslation } from "react-i18next"

import { useReducedMotion } from "@/components/landing/motion"

// TODO: swap in the real product film + poster once produced. The template's
// stock clip is kept so the scroll mechanics are reviewable today.
const VIDEO_SRC =
  "https://videos.pexels.com/video-files/3015510/3015510-hd_1920_1080_24fps.mp4"
const VIDEO_POSTER =
  "https://images.pexels.com/videos/3015510/free-video-3015510.jpg?auto=compress&cs=tinysrgb&w=1600"
const MAX_WIDTH = 1440

const PEEK_VISIBLE = 50
const PEEK_WIDTH = 400
const PEEK_HEIGHT = 260
const NAV_OFFSET = 96
const BOTTOM_GAP = 24
const GROWTH_END = 0.55
const PLAY_AT = 0.35

/** Matches the horizontal padding of sections below: px-5 / sm:px-8 / lg:px-10 */
function sectionPadding(viewportWidth: number): number {
  if (viewportWidth >= 1024) return 40
  if (viewportWidth >= 640) return 32
  return 20
}

function ShowcaseVideo({
  videoRef,
  controls = false,
}: {
  videoRef: RefObject<HTMLVideoElement | null>
  controls?: boolean
}): ReactNode {
  const { t } = useTranslation()
  return (
    <video
      ref={videoRef}
      className="h-full w-full object-cover"
      src={VIDEO_SRC}
      poster={VIDEO_POSTER}
      muted
      loop
      playsInline
      controls={controls}
      preload="metadata"
      aria-label={t("landing.video.ariaLabel")}
    />
  )
}

/**
 * The film peeks out from under the hero and grows to section width as you
 * scroll. Autoplay is gated on visibility + scroll progress; reduced motion
 * gets a static, controls-enabled player.
 */
export function VideoShowcase(): ReactNode {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const sectionRef = useRef<HTMLElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [viewport, setViewport] = useState({ w: 1280, h: 800 })

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
  const captionOpacity = useTransform(scrollYProgress, [0, 0.1], [1, 0])
  const captionY = useTransform(y, (value) => NAV_OFFSET + value - 44)
  const scrollHintOpacity = useTransform(
    scrollYProgress,
    [GROWTH_END, GROWTH_END + 0.1, 0.9, 0.98],
    [0, 1, 1, 0]
  )

  useEffect(() => {
    if (prefersReducedMotion) return
    const video = videoRef.current
    if (!video) return

    let inView = false
    const sync = (): void => {
      const shouldPlay = inView && scrollYProgress.get() >= PLAY_AT
      if (shouldPlay) {
        if (video.paused) void video.play().catch(() => undefined)
      } else if (!video.paused) {
        video.pause()
      }
    }

    const observer = new IntersectionObserver(
      (entries) => {
        inView = entries[0]?.isIntersecting ?? false
        sync()
      },
      { threshold: 0 }
    )
    observer.observe(video)

    const unsubscribe = scrollYProgress.on("change", sync)
    return () => {
      observer.disconnect()
      unsubscribe()
    }
  }, [scrollYProgress, prefersReducedMotion])

  if (prefersReducedMotion) {
    return (
      <section
        id="features"
        aria-label={t("landing.video.ariaLabel")}
        className="flex min-h-svh flex-col items-center justify-center gap-8 px-6 py-24"
      >
        <p className="flex items-center gap-2.5 text-sm font-medium text-foreground">
          <Play className="size-3.5 fill-current" aria-hidden="true" />
          {t("landing.video.caption")}
        </p>
        <div
          className="relative w-full overflow-hidden rounded-3xl bg-black"
          style={{ maxWidth: MAX_WIDTH, aspectRatio: "16 / 9" }}
        >
          <ShowcaseVideo videoRef={videoRef} controls />
        </div>
      </section>
    )
  }

  return (
    <section
      ref={sectionRef}
      id="features"
      aria-label={t("landing.video.ariaLabel")}
      className="pointer-events-none relative z-20 [margin-top:-100svh] h-[180svh]"
    >
      <div className="sticky top-0 h-svh overflow-hidden">
        <motion.p
          style={{ x: "-50%", y: captionY, opacity: captionOpacity }}
          className="absolute top-0 left-1/2 flex items-center gap-2.5 text-xs font-medium whitespace-nowrap text-foreground"
        >
          <Play className="size-3 fill-current" aria-hidden="true" />
          {t("landing.video.caption")}
        </motion.p>

        <motion.div
          style={{ x: "-50%", y, top: NAV_OFFSET, width, height }}
          className="absolute left-1/2 overflow-hidden rounded-3xl bg-black"
        >
          <ShowcaseVideo videoRef={videoRef} />
          <motion.div
            style={{ x: "-50%", opacity: scrollHintOpacity }}
            aria-hidden="true"
            className="absolute bottom-5 left-1/2 flex items-center gap-2 rounded-full bg-black/55 py-2 pr-3 pl-4 text-white/90"
          >
            <span className="text-[11px] font-medium tracking-wider uppercase">
              {t("landing.video.scrollDown")}
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
