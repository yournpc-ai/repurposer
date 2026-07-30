import { motion, useScroll, useTransform } from "motion/react"
import { useRef, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { useReducedMotion } from "@/components/landing/motion"
import { SectionHeading } from "@/components/landing/SectionHeading"

/**
 * Three parallax quote columns drifting at different rates (desktop);
 * plain grid on mobile / reduced motion. Avatars are initials chips —
 * real photos arrive with real quotes.
 */

const TESTIMONIAL_KEYS = ["t1", "t2", "t3", "t4", "t5", "t6"] as const

type TestimonialKey = (typeof TESTIMONIAL_KEYS)[number]

/** Column composition for the desktop parallax layout. */
const COLUMNS: TestimonialKey[][] = [
  ["t1", "t4"],
  ["t2", "t5"],
  ["t3", "t6"],
]

function QuoteCard({ itemKey }: { itemKey: string }): ReactNode {
  const { t } = useTranslation()
  const name = t(`landing.testimonials.items.${itemKey}.name`)
  const initials = name
    .replace(/^(Prof\.|Dr\.)\s*/, "")
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")

  return (
    <figure className="flex flex-col gap-8 rounded-3xl border border-border bg-background p-7 sm:p-8">
      <blockquote className="text-lg leading-relaxed font-medium tracking-tight text-balance text-foreground">
        “{t(`landing.testimonials.items.${itemKey}.quote`)}”
      </blockquote>
      <figcaption className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="flex size-10 shrink-0 items-center justify-center rounded-full border border-border bg-muted text-xs font-medium text-foreground"
        >
          {initials}
        </span>
        <div>
          <p className="text-sm font-medium text-foreground">{name}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t(`landing.testimonials.items.${itemKey}.role`)}
          </p>
        </div>
      </figcaption>
    </figure>
  )
}

export function Testimonials(): ReactNode {
  const { t } = useTranslation()
  const reduce = useReducedMotion()
  const sectionRef = useRef<HTMLElement>(null)

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start end", "end start"],
  })

  const yLeft = useTransform(scrollYProgress, [0, 1], [40, -64])
  const yMiddle = useTransform(scrollYProgress, [0, 1], [128, -24])
  const yRight = useTransform(scrollYProgress, [0, 1], [72, -104])
  const columnY = [yLeft, yMiddle, yRight]

  return (
    <section
      ref={sectionRef}
      id="reviews"
      className="mx-auto max-w-[1440px] scroll-mt-24 px-5 pb-24 sm:px-8 sm:pb-32 lg:px-10"
    >
      <SectionHeading
        title={t("landing.testimonials.title")}
        description={t("landing.testimonials.description")}
      />

      {reduce ? (
        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {TESTIMONIAL_KEYS.map((key) => (
            <QuoteCard key={key} itemKey={key} />
          ))}
        </div>
      ) : (
        <>
          <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:hidden">
            {TESTIMONIAL_KEYS.map((key) => (
              <QuoteCard key={key} itemKey={key} />
            ))}
          </div>

          <div className="mt-16 hidden grid-cols-3 gap-4 lg:grid">
            {COLUMNS.map((column, i) => (
              <motion.div
                key={column.join("-")}
                style={{ y: columnY[i] }}
                className="flex flex-col gap-4"
              >
                {column.map((itemKey) => (
                  <QuoteCard key={itemKey} itemKey={itemKey} />
                ))}
              </motion.div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
