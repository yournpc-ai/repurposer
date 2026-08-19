import {
  motion,
  useScroll,
  useTransform,
  type MotionValue,
} from "motion/react"
import { useRef, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { useReducedMotion } from "@/components/landing/motion"

function Word({
  children,
  progress,
  range,
  trailingSpace,
}: {
  children: string
  progress: MotionValue<number>
  range: [number, number]
  trailingSpace: boolean
}): ReactNode {
  const opacity = useTransform(progress, range, [0.12, 1])

  return (
    <motion.span style={{ opacity }} className="inline">
      {children}
      {trailingSpace ? " " : ""}
    </motion.span>
  )
}

/**
 * Scroll-scrubbed word-by-word statement reveal. Splits on spaces for
 * whitespace languages; falls back to per-character chunks (no trailing
 * spaces) for zh.
 */
export function Manifesto(): ReactNode {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const textRef = useRef<HTMLParagraphElement>(null)

  const statement: string = t("landing.manifesto.statement")

  const { scrollYProgress } = useScroll({
    target: textRef,
    offset: ["start 0.85", "start 0.3"],
  })

  const byWord = statement.includes(" ")
  const units = byWord ? statement.split(" ") : Array.from(statement)

  return (
    <section className="mx-auto flex min-h-svh w-full max-w-[1440px] flex-col justify-center px-5 py-16 sm:px-8 lg:px-10">
      <p
        ref={textRef}
        className="max-w-4xl font-display text-[clamp(26px,4.2vw,52px)] leading-[1.18] font-medium tracking-tight text-foreground"
      >
        {prefersReducedMotion
          ? statement
          : units.map((unit, i) => {
              const start = i / units.length
              const end = start + 1 / units.length
              return (
                <Word
                  key={`${unit}-${i}`}
                  progress={scrollYProgress}
                  range={[start, end]}
                  trailingSpace={byWord}
                >
                  {unit}
                </Word>
              )
            })}
      </p>
    </section>
  )
}
