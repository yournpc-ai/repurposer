import {
  motion,
  useAnimationFrame,
  useMotionValue,
  useScroll,
  useSpring,
  useTransform,
  useVelocity,
} from "motion/react"
import { useRef, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { useReducedMotion } from "@/components/landing/motion"
import { SectionHeading } from "@/components/landing/SectionHeading"

/**
 * Velocity-reactive marquee of knowledge-asset cards (the template's photo
 * marquee, re-contented: our outputs are text, so the cards are mini
 * LinkedIn posts / quote cards / clip notes). Two rows, opposite directions,
 * scroll velocity boosts and can reverse the drift.
 */

const ROW_A_KEYS = ["c1", "c2", "c3", "c4", "c5"] as const
const ROW_B_KEYS = ["c6", "c7", "c8", "c9", "c10"] as const

const COPIES = 5
const SET_FRACTION = 100 / COPIES
const BASE_SPEED = 0.55
const MAX_VELOCITY_BOOST = 4

function wrap(min: number, max: number, value: number): number {
  const range = max - min
  return ((((value - min) % range) + range) % range) + min
}

function AssetCard({ cardKey }: { cardKey: string }): ReactNode {
  const { t } = useTranslation()
  return (
    <figure className="mr-5 w-[260px] shrink-0 sm:w-[300px]">
      <div className="rounded-2xl border border-border bg-background p-5">
        <span className="font-mono text-[10px] tracking-widest text-muted-foreground uppercase">
          {t(`landing.gallery.cards.${cardKey}.type`)}
        </span>
        <p className="mt-2.5 text-[13px] leading-relaxed text-foreground">
          {t(`landing.gallery.cards.${cardKey}.text`)}
        </p>
      </div>
    </figure>
  )
}

function MarqueeRow({
  cardKeys,
  direction,
}: {
  cardKeys: readonly string[]
  direction: 1 | -1
}): ReactNode {
  const prefersReducedMotion = useReducedMotion()
  const baseX = useMotionValue(direction === 1 ? -SET_FRACTION / 2 : 0)
  const directionFactor = useRef<number>(direction)

  const { scrollY } = useScroll()
  const scrollVelocity = useVelocity(scrollY)
  const smoothVelocity = useSpring(scrollVelocity, {
    damping: 50,
    stiffness: 400,
  })
  const velocityFactor = useTransform(
    smoothVelocity,
    [0, 1200],
    [0, MAX_VELOCITY_BOOST],
    { clamp: false }
  )

  const x = useTransform(baseX, (value) => `${wrap(-SET_FRACTION, 0, value)}%`)

  useAnimationFrame((_, delta) => {
    if (prefersReducedMotion) return
    const step = BASE_SPEED * (delta / 1000)
    const boost = velocityFactor.get()
    if (boost < 0) directionFactor.current = -direction
    else if (boost > 0) directionFactor.current = direction
    const moveBy = directionFactor.current * step * (1 + Math.abs(boost)) * -1
    baseX.set(baseX.get() + moveBy)
  })

  if (prefersReducedMotion) {
    return (
      <div className="overflow-x-auto px-5 sm:px-8 lg:px-10">
        <div className="flex w-max">
          {cardKeys.map((key) => (
            <AssetCard key={key} cardKey={key} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="overflow-hidden">
      <motion.div style={{ x }} className="flex w-max">
        {Array.from({ length: COPIES }, (_, copy) =>
          cardKeys.map((key) => <AssetCard key={`${copy}-${key}`} cardKey={key} />)
        )}
      </motion.div>
    </div>
  )
}

export function Gallery(): ReactNode {
  const { t } = useTranslation()
  return (
    <section
      id="gallery"
      className="scroll-mt-24 overflow-hidden pb-24 sm:pb-32"
    >
      <div className="mx-auto max-w-[1440px] px-5 sm:px-8 lg:px-10">
        <SectionHeading
          title={t("landing.gallery.title")}
          description={t("landing.gallery.description")}
        />
      </div>

      <div className="mt-14 flex flex-col gap-5">
        <MarqueeRow cardKeys={ROW_A_KEYS} direction={1} />
        <MarqueeRow cardKeys={ROW_B_KEYS} direction={-1} />
      </div>
    </section>
  )
}
