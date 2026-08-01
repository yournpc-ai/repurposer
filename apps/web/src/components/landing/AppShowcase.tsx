import {
  cubicBezier,
  motion,
  useScroll,
  useTransform,
  type MotionValue,
} from "motion/react"
import { ArrowUp, BadgeCheck, Check, Globe } from "lucide-react"
import { useRef, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { LogoMark } from "@/components/LogoMark"
import {
  useIsDesktop,
  useReducedMotion,
} from "@/components/landing/motion"
import { SectionHeading } from "@/components/landing/SectionHeading"

/**
 * Pinned scroll walkthrough of the Repurposer flow, ported from the Cortex
 * AppShowcase. The phone mock became a browser window (we're a web product);
 * the scroll mechanics — sheet-stacked screens, presence/drift windows for
 * step text + asides, segment ticks — are unchanged.
 */

const STEP_KEYS = ["s1", "s2", "s3", "s4"] as const
const ASIDE_KEYS = ["a1", "a2", "a3", "a4"] as const

const STEP_COUNT = STEP_KEYS.length
const SEGMENT = 1 / STEP_COUNT
const FADE = 0.06
const SHEET_EASE = cubicBezier(0.32, 0.72, 0, 1)

/**
 * Presence/drift windows are aligned to the ScreenLayer slide window
 * [segment boundary ± FADE], so a step's text + aside always travel WITH
 * its screen: (text N + screen N) leave as (text N+1 + screen N+1) arrive —
 * the combo is 01·02 → 02·03 → 03·04 in lockstep, never text-behind-screen.
 */
function presenceWindow(index: number): { input: number[]; output: number[] } {
  const enter = index * SEGMENT
  const exit = (index + 1) * SEGMENT
  if (index === 0)
    return { input: [exit - FADE, exit + FADE], output: [1, 0] }
  if (index === STEP_COUNT - 1)
    return { input: [enter - FADE, enter + FADE], output: [0, 1] }
  return {
    input: [enter - FADE, enter + FADE, exit - FADE, exit + FADE],
    output: [0, 1, 1, 0],
  }
}

function driftWindow(
  index: number,
  distance: number
): { input: number[]; output: number[] } {
  const enter = index * SEGMENT
  const exit = (index + 1) * SEGMENT
  if (index === 0)
    return { input: [0, exit - FADE, exit + FADE], output: [0, 0, -distance] }
  if (index === STEP_COUNT - 1)
    return { input: [enter - FADE, enter + FADE, 1], output: [distance, 0, 0] }
  return {
    input: [enter - FADE, enter + FADE, exit - FADE, exit + FADE],
    output: [distance, 0, 0, -distance],
  }
}

/* ------------------------------------------------------------------ */
/* Browser chrome + the four mock screens                              */
/* ------------------------------------------------------------------ */

function BrowserFrame({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="w-[440px] overflow-hidden rounded-2xl border border-border bg-background shadow-[0_30px_80px_-30px_rgba(0,0,0,0.35)] xl:w-[520px] [@media(max-height:760px)]:w-[400px]">
      <div className="flex items-center gap-3 border-b border-border bg-muted px-4 py-2.5">
        <div className="flex gap-1.5" aria-hidden="true">
          <span className="size-2.5 rounded-full bg-foreground/15" />
          <span className="size-2.5 rounded-full bg-foreground/15" />
          <span className="size-2.5 rounded-full bg-foreground/15" />
        </div>
        <span className="flex-1 rounded-md bg-background px-3 py-1 text-center font-mono text-[10px] text-muted-foreground">
          repurposer.ai
        </span>
      </div>
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-muted">
        {children}
      </div>
    </div>
  )
}

function ScreenChrome({ label }: { label: string }): ReactNode {
  return (
    <div className="flex items-center justify-between px-5 pt-5 pb-3">
      <span className="text-[13px] font-medium tracking-tight text-foreground">
        {label}
      </span>
      <span className="size-6 rounded-full bg-foreground/10" aria-hidden="true" />
    </div>
  )
}

function ComposeScreen(): ReactNode {
  const { t } = useTranslation()
  const chips = [
    t("landing.showcase.screens.compose.chip1"),
    t("landing.showcase.screens.compose.chip2"),
    t("landing.showcase.screens.compose.chip3"),
  ]
  return (
    <div className="flex h-full flex-col px-5 pb-5">
      <ScreenChrome label={t("landing.showcase.screens.compose.chrome")} />
      <div className="mx-1 mt-2 rounded-xl border border-border bg-background p-4">
        <p className="text-[13px] leading-snug text-foreground">
          {t("landing.showcase.screens.compose.prompt")}
          <span className="ml-0.5 inline-block h-3.5 w-px animate-pulse bg-foreground align-middle" />
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {chips.map((chip) => (
            <span
              key={chip}
              className="rounded-full border border-border bg-background px-2.5 py-1 text-[10px] font-medium text-muted-foreground"
            >
              {chip}
            </span>
          ))}
        </div>
      </div>
      <div className="flex-1" />
      <div className="mx-1 flex h-10 items-center justify-center gap-1.5 rounded-full bg-foreground text-xs font-medium text-background">
        <ArrowUp className="size-3.5" aria-hidden="true" />
        {t("landing.showcase.screens.compose.cta")}
      </div>
    </div>
  )
}

function ResultsScreen(): ReactNode {
  const { t } = useTranslation()
  const rows = [
    t("landing.showcase.screens.results.row2"),
    t("landing.showcase.screens.results.row3"),
  ]
  return (
    <div className="flex h-full flex-col px-5 pb-5">
      <ScreenChrome label={t("landing.showcase.screens.results.chrome")} />
      <div className="mx-1 rounded-xl border border-border bg-background p-4">
        <div className="flex items-center justify-between">
          <span className="rounded-full bg-foreground px-2.5 py-1 font-mono text-[10px] text-background">
            {t("landing.showcase.screens.results.score")}
          </span>
          <BadgeCheck className="size-4 text-foreground" aria-hidden="true" />
        </div>
        <p className="mt-3 text-[14px] leading-snug font-medium text-foreground">
          {t("landing.showcase.screens.results.cardTitle")}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          {t("landing.showcase.screens.results.cardMeta")}
        </p>
      </div>
      <div className="mt-2.5 flex flex-col gap-2">
        {rows.map((row) => (
          <div
            key={row}
            className="mx-1 flex items-center justify-between rounded-xl border border-border bg-background px-3.5 py-2.5"
          >
            <span className="text-[12px] font-medium text-foreground">{row}</span>
            <Check className="size-3.5 text-foreground" aria-hidden="true" />
          </div>
        ))}
      </div>
      <div className="flex-1" />
    </div>
  )
}

function ChatScreen(): ReactNode {
  const { t } = useTranslation()
  return (
    <div className="flex h-full flex-col px-5 pb-5">
      <ScreenChrome label={t("landing.showcase.screens.chat.chrome")} />
      <div className="mx-1 self-end rounded-2xl rounded-br-md bg-foreground px-3.5 py-2.5 text-[12px] leading-snug text-background">
        {t("landing.showcase.screens.chat.user")}
      </div>
      <div className="mx-1 mt-2.5 flex items-start gap-2">
        <LogoMark className="mt-0.5 size-5" />
        <div className="rounded-2xl rounded-tl-md border border-border bg-background px-3.5 py-2.5 text-[12px] leading-snug text-foreground">
          {t("landing.showcase.screens.chat.agent")}
        </div>
      </div>
      <div className="flex-1" />
      <div className="mx-1 flex h-9 items-center rounded-full border border-border bg-background px-3.5">
        <span className="h-3 w-px animate-pulse bg-foreground" aria-hidden="true" />
      </div>
    </div>
  )
}

function PublishScreen(): ReactNode {
  const { t } = useTranslation()
  const rows = [
    t("landing.showcase.screens.publish.row1"),
    t("landing.showcase.screens.publish.row2"),
    t("landing.showcase.screens.publish.row3"),
  ]
  return (
    <div className="flex h-full flex-col px-5 pb-5">
      <ScreenChrome label={t("landing.showcase.screens.publish.chrome")} />
      <p className="px-1 text-[11px] font-medium text-muted-foreground">
        {t("landing.showcase.screens.publish.note")}
      </p>
      <div className="mt-3 flex flex-col gap-2">
        {rows.map((row) => (
          <div
            key={row}
            className="flex items-center gap-2.5 rounded-xl border border-border bg-background px-3.5 py-3"
          >
            <Globe className="size-3.5 shrink-0 text-foreground" aria-hidden="true" />
            <span className="text-[12px] font-medium text-foreground">{row}</span>
          </div>
        ))}
      </div>
      <div className="flex-1" />
    </div>
  )
}

const SCREENS: ReactNode[] = [
  <ComposeScreen key="compose" />,
  <ResultsScreen key="results" />,
  <ChatScreen key="chat" />,
  <PublishScreen key="publish" />,
]

/* ------------------------------------------------------------------ */
/* Scroll-driven layers (ported verbatim in behaviour)                 */
/* ------------------------------------------------------------------ */

function ScreenLayer({
  progress,
  index,
  children,
}: {
  progress: MotionValue<number>
  index: number
  children: ReactNode
}): ReactNode {
  const enter = index * SEGMENT
  const cover = (index + 1) * SEGMENT
  const isFirst = index === 0
  const isLast = index === STEP_COUNT - 1

  const y = useTransform(
    progress,
    isFirst ? [0, 1] : [enter - FADE, enter + FADE],
    isFirst ? ["0%", "0%"] : ["103%", "0%"],
    { ease: SHEET_EASE }
  )
  const scale = useTransform(
    progress,
    isLast ? [0, 1] : [cover - FADE, cover + FADE],
    isLast ? [1, 1] : [1, 0.93]
  )
  const dim = useTransform(
    progress,
    isLast ? [0, 1] : [cover - FADE, cover + FADE],
    isLast ? [0, 0] : [0, 0.42]
  )
  const radius = useTransform(
    progress,
    isFirst
      ? [cover - FADE, cover + FADE]
      : isLast
        ? [enter - FADE, enter + FADE]
        : [enter - FADE, enter + FADE, cover - FADE, cover + FADE],
    isFirst ? [0, 24] : isLast ? [32, 0] : [32, 0, 0, 24]
  )

  return (
    <motion.div
      style={{ y, scale, borderRadius: radius }}
      className="absolute inset-0 overflow-hidden bg-muted"
    >
      {children}
      <motion.div
        style={{ opacity: dim }}
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-black"
      />
    </motion.div>
  )
}

function StepText({
  progress,
  index,
  stepKey,
}: {
  progress: MotionValue<number>
  index: number
  stepKey: (typeof STEP_KEYS)[number]
}): ReactNode {
  const { t } = useTranslation()
  const presence = presenceWindow(index)
  const drift = driftWindow(index, 36)
  const opacity = useTransform(progress, presence.input, presence.output)
  const y = useTransform(progress, drift.input, drift.output)

  return (
    <motion.div
      style={{ opacity, y }}
      className="absolute inset-0 flex flex-col justify-center"
    >
      <div className="flex items-center gap-4">
        <span className="font-mono text-xs font-medium text-foreground">
          0{index + 1}
        </span>
        <motion.span
          style={{ scaleX: opacity, originX: 0 }}
          className="block h-px w-12 bg-foreground"
        />
      </div>
      <h3 className="mt-5 text-3xl font-medium tracking-tight text-foreground xl:text-4xl">
        {t(`landing.showcase.steps.${stepKey}.title`)}
      </h3>
      <p className="mt-4 max-w-sm text-base leading-relaxed text-muted-foreground">
        {t(`landing.showcase.steps.${stepKey}.body`)}
      </p>
    </motion.div>
  )
}

function StepAside({
  progress,
  index,
  asideKey,
}: {
  progress: MotionValue<number>
  index: number
  asideKey: (typeof ASIDE_KEYS)[number]
}): ReactNode {
  const { t } = useTranslation()
  const presence = presenceWindow(index)
  const drift = driftWindow(index, 70)
  const opacity = useTransform(progress, presence.input, presence.output)
  const y = useTransform(progress, drift.input, drift.output)

  return (
    <motion.div
      style={{ opacity, y }}
      aria-hidden="true"
      className="absolute inset-0 flex flex-col items-start justify-center gap-4"
    >
      <div className="rounded-2xl border border-border bg-background p-4 shadow-sm">
        <p className="font-mono text-[10px] tracking-widest text-muted-foreground uppercase">
          {t(`landing.showcase.asides.${asideKey}.label`)}
        </p>
        <p className="mt-1.5 text-sm font-medium text-foreground">
          {t(`landing.showcase.asides.${asideKey}.title`)}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {t(`landing.showcase.asides.${asideKey}.body`)}
        </p>
      </div>
      <span className="rounded-full border border-border bg-background px-3.5 py-1.5 text-xs text-muted-foreground">
        {t(`landing.showcase.asides.${asideKey}.chip`)}
      </span>
    </motion.div>
  )
}

function SegmentTick({
  progress,
  index,
}: {
  progress: MotionValue<number>
  index: number
}): ReactNode {
  const fill = useTransform(
    progress,
    [index * SEGMENT, (index + 1) * SEGMENT],
    [0, 1]
  )

  return (
    <span className="h-[3px] w-9 overflow-hidden rounded-full bg-border">
      <motion.span
        style={{ scaleX: fill, originX: 0 }}
        className="block h-full w-full bg-foreground"
      />
    </span>
  )
}

export function AppShowcase(): ReactNode {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const isDesktop = useIsDesktop()
  const wrapperRef = useRef<HTMLDivElement>(null)

  const { scrollYProgress } = useScroll({
    target: wrapperRef,
    offset: ["start start", "end end"],
  })

  const pinned = isDesktop && !prefersReducedMotion

  return (
    <section id="how-it-works" className="scroll-mt-24 pb-24 sm:pb-32">
      <div className="mx-auto max-w-[1440px] px-5 sm:px-8 lg:px-10">
        <SectionHeading
          title={t("landing.showcase.title")}
          description={t("landing.showcase.description")}
        />
      </div>

      {pinned ? (
        <div ref={wrapperRef} className="relative h-[420svh]">
          <div className="sticky top-0 flex h-svh items-center overflow-hidden">
            <div className="mx-auto grid w-full max-w-[1440px] grid-cols-[1fr_auto_1fr] items-center gap-x-16 px-10">
              <div className="relative h-[340px]">
                {STEP_KEYS.map((key, i) => (
                  <StepText
                    key={key}
                    progress={scrollYProgress}
                    index={i}
                    stepKey={key}
                  />
                ))}
              </div>

              <div className="relative">
                <div className="relative z-10 flex flex-col items-center gap-7">
                  <BrowserFrame>
                    <div className="absolute inset-0">
                      {SCREENS.map((screen, i) => (
                        <ScreenLayer
                          key={STEP_KEYS[i]}
                          progress={scrollYProgress}
                          index={i}
                        >
                          {screen}
                        </ScreenLayer>
                      ))}
                    </div>
                  </BrowserFrame>
                  <div className="flex items-center gap-2" aria-hidden="true">
                    {STEP_KEYS.map((key, i) => (
                      <SegmentTick
                        key={key}
                        progress={scrollYProgress}
                        index={i}
                      />
                    ))}
                  </div>
                </div>
              </div>

              <div className="relative h-[340px]">
                {ASIDE_KEYS.map((key, i) => (
                  <StepAside
                    key={key}
                    progress={scrollYProgress}
                    index={i}
                    asideKey={key}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="mx-auto mt-14 flex max-w-[1440px] flex-col gap-16 px-5 sm:px-8 lg:px-10">
          <div className="flex justify-center">
            <BrowserFrame>
              <div className="absolute inset-0">{SCREENS[1]}</div>
            </BrowserFrame>
          </div>
          <ol className="flex flex-col gap-12">
            {STEP_KEYS.map((key, i) => (
              <li key={key}>
                <div className="flex items-center gap-4">
                  <span className="font-mono text-xs font-medium text-foreground">
                    0{i + 1}
                  </span>
                  <span className="block h-px w-12 bg-foreground" />
                </div>
                <h3 className="mt-5 text-3xl font-medium tracking-tight text-foreground sm:text-4xl">
                  {t(`landing.showcase.steps.${key}.title`)}
                </h3>
                <p className="mt-4 max-w-sm text-base leading-relaxed text-muted-foreground">
                  {t(`landing.showcase.steps.${key}.body`)}
                </p>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}
