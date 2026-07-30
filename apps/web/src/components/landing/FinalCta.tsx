import { motion, useScroll, useTransform, type Variants } from "motion/react"
import { useRef, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "@tanstack/react-router"

import { MagneticLink } from "@/components/landing/MagneticLink"
import { softEase, useReducedMotion } from "@/components/landing/motion"
import { useAuth } from "@/components/AuthProvider"

/**
 * Final CTA: inverted --inverse panel that scales in on scroll, a fan of
 * mini output cards (re-contented from the template's photo prints — our
 * outputs are text), a word-by-word masked headline, and a magnetic CTA.
 */

const FAN_CARD_KEYS = ["c2", "c1", "c8", "c3", "c9"] as const

const FAN_LAYOUT = [
  { x: -260, y: 34, r: -12 },
  { x: -130, y: 10, r: -6 },
  { x: 0, y: 0, r: 0 },
  { x: 130, y: 10, r: 6 },
  { x: 260, y: 34, r: 12 },
]

const FAN_CONTAINER: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07, delayChildren: 0.1 } },
}

const WORD_CONTAINER: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.055, delayChildren: 0.25 } },
}

const WORD_ITEM: Variants = {
  hidden: { y: "110%" },
  visible: { y: 0, transition: { duration: 0.7, ease: softEase } },
}

function CardFan({ reduce }: { reduce: boolean }): ReactNode {
  const { t } = useTranslation()
  return (
    <motion.div
      initial={reduce ? false : "hidden"}
      viewport={{ once: true, margin: "-80px" }}
      variants={FAN_CONTAINER}
      {...(reduce ? {} : { whileInView: "visible" })}
      aria-hidden="true"
      className="relative h-36 w-full origin-top scale-[0.6] sm:h-44 sm:scale-90 lg:scale-100"
    >
      {FAN_CARD_KEYS.map((cardKey, i) => {
        const layout = FAN_LAYOUT[i] ?? { x: 0, y: 0, r: 0 }
        return (
          <motion.div
            key={cardKey}
            variants={{
              hidden: { opacity: 0, y: 48, x: layout.x * 0.25, rotate: 0 },
              visible: {
                opacity: 1,
                x: layout.x,
                y: layout.y,
                rotate: layout.r,
                transition: { type: "spring", stiffness: 220, damping: 22 },
              },
            }}
            {...(reduce
              ? {
                  style: {
                    transform: `translate(${layout.x}px, ${layout.y}px) rotate(${layout.r}deg)`,
                  },
                }
              : {
                  whileHover: {
                    y: layout.y - 10,
                    rotate: layout.r * 0.4,
                  },
                })}
            className="absolute top-0 left-1/2 -ml-[7rem] w-56 overflow-hidden rounded-2xl border border-white/20 bg-white/5 p-4 shadow-[0_16px_40px_-12px_rgba(0,0,0,0.55)] backdrop-blur-sm"
          >
            <span className="font-mono text-[9px] tracking-widest uppercase opacity-60">
              {t(`landing.gallery.cards.${cardKey}.type`)}
            </span>
            <p className="mt-1.5 line-clamp-3 text-[11px] leading-relaxed opacity-90">
              {t(`landing.gallery.cards.${cardKey}.text`)}
            </p>
          </motion.div>
        )
      })}
    </motion.div>
  )
}

export function FinalCta(): ReactNode {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const sectionRef = useRef<HTMLElement>(null)

  const headline: string = t("landing.finalCta.headline")
  const words = headline.includes(" ") ? headline.split(" ") : Array.from(headline)

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start end", "center center"],
  })
  const scale = useTransform(scrollYProgress, [0, 1], [0.93, 1])
  const panelY = useTransform(scrollYProgress, [0, 1], [40, 0])

  const openPrimary = (): void => {
    if (isAuthenticated) void navigate({ to: "/home" })
    else setLoginOpen(true)
  }

  return (
    <section
      ref={sectionRef}
      id="sign-up"
      className="mx-auto max-w-[1440px] scroll-mt-24 px-5 pb-24 sm:px-8 sm:pb-32 lg:px-10"
    >
      <motion.div
        style={reduce ? undefined : { scale, y: panelY }}
        className="flex flex-col items-center overflow-hidden rounded-[40px] bg-inverse px-6 pt-16 pb-24 text-center text-inverse-foreground sm:pt-20 sm:pb-32"
      >
        <CardFan reduce={reduce} />

        <h2 className="mt-12 max-w-3xl font-display text-[clamp(34px,5.5vw,68px)] leading-[1.06] font-medium tracking-tight">
          {reduce ? (
            headline
          ) : (
            <>
              <span className="sr-only">{headline}</span>
              <motion.span
                aria-hidden="true"
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: "-80px" }}
                variants={WORD_CONTAINER}
                className="flex flex-wrap justify-center gap-x-[0.28em]"
              >
                {words.map((word, i) => (
                  <span
                    key={`${word}-${i}`}
                    className="-mb-[0.12em] inline-flex overflow-hidden pb-[0.12em]"
                  >
                    <motion.span variants={WORD_ITEM} className="inline-block">
                      {word}
                    </motion.span>
                  </span>
                ))}
              </motion.span>
            </>
          )}
        </h2>
        <p className="mt-6 max-w-md text-base leading-relaxed opacity-65">
          {t("landing.finalCta.subtitle")}
        </p>
        <div className="mt-10 flex flex-col items-center gap-3 sm:flex-row">
          <MagneticLink
            reduce={reduce}
            onClick={openPrimary}
            className="inline-flex h-13 items-center rounded-full bg-inverse-foreground px-8 text-sm font-medium text-inverse"
          >
            {t("landing.finalCta.ctaPrimary")}
          </MagneticLink>
          <a
            href="#pricing"
            className="inline-flex h-13 items-center rounded-full border border-current/25 px-8 text-sm font-medium transition-opacity hover:opacity-70"
          >
            {t("landing.finalCta.ctaSecondary")}
          </a>
        </div>
      </motion.div>
    </section>
  )
}
