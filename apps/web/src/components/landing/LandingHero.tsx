import { motion } from "motion/react"
import { type ReactNode } from "react"
import { Trans, useTranslation } from "react-i18next"
import { useNavigate } from "@tanstack/react-router"

import {
  softEase,
  useReducedMotion,
} from "@/components/landing/motion"
import { HeroWaves } from "@/components/landing/HeroWaves"
import { MagneticLink } from "@/components/landing/MagneticLink"
import { LandingInfoDialog } from "@/components/landing/LandingInfoDialog"
import { useAuth } from "@/lib/auth-context"

/**
 * Landing hero: headline choreography over an atmosphere layer.
 * `data-slot="hero-webgl"` is the reserved mount point for the future WebGL
 * set piece (the Cortex orbit field was intentionally not ported — new
 * content TBD). Until then the ambient-glow utility carries the atmosphere.
 */
export function LandingHero(): ReactNode {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()
  const navigate = useNavigate()
  const prefersReducedMotion = useReducedMotion()
  const fadeUp = (delay: number) => ({
    initial: prefersReducedMotion
      ? ({ opacity: 0 } as const)
      : ({ opacity: 0, y: 24 } as const),
    animate: { opacity: 1, y: 0 },
    transition: prefersReducedMotion
      ? { duration: 0.01 }
      : { duration: 0.7, ease: softEase, delay: delay + 0.15 },
  })

  return (
    <section
      className="relative flex h-full items-center justify-center overflow-clip"
    >
      <motion.div
        className="absolute inset-0 flex items-center justify-center"
      >
        {/* Reserved WebGL mount point — now hosting the ASCII wave field. */}
        <div aria-hidden data-slot="hero-webgl" className="pointer-events-none absolute inset-0">
          <HeroWaves />
        </div>
        {/* Ambient glow — soft opal-tinted atmosphere behind the hero content. */}
        <div aria-hidden data-slot="hero-background" className="absolute inset-0 ambient-glow" />

        <div className="relative z-10 flex w-full max-w-6xl flex-col items-center px-5 py-6 text-center sm:px-8">
          {/* Legibility veil — radial background tint that quiets the ASCII
              field behind the text only. Sized off THIS content box (as in
              the Sentinel hero), so the field stays vivid at the edges. */}
          <div
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-1/2 -z-[1] h-[150%] w-[160%] -translate-x-1/2 -translate-y-1/2"
            style={{
              background:
                "radial-gradient(ellipse at center, var(--background) 0%, color-mix(in srgb, var(--background) 78%, transparent) 45%, transparent 72%)",
            }}
          />
          <motion.h1
            {...fadeUp(0.1)}
            className="font-display text-[clamp(36px,7.5vw,84px)] leading-[1.02] font-medium tracking-tight text-balance text-foreground"
          >
            <span className="sm:whitespace-nowrap">{t("landing.heroTitle1")}</span>
            <br />
            <span className="sm:whitespace-nowrap">{t("landing.heroTitle2")}</span>
          </motion.h1>
          <motion.p
            {...fadeUp(0.24)}
            className="mt-6 max-w-3xl text-base sm:text-lg leading-relaxed text-muted-foreground"
          >
            <Trans
              i18nKey="landing.heroSubtitle"
              components={{ b: <strong className="font-medium text-foreground" /> }}
            />
          </motion.p>
          <motion.div {...fadeUp(0.38)} className="mt-9 flex flex-col items-center gap-3 sm:flex-row">
            <MagneticLink
              reduce={prefersReducedMotion}
              onClick={() => {
                if (isAuthenticated) {
                  void navigate({ to: "/home" })
                } else {
                  setLoginOpen(true)
                }
              }}
              className="inline-flex h-13 items-center rounded-full bg-foreground px-8 text-sm font-medium text-background transition-opacity hover:opacity-85"
            >
              {t("landing.openStudio")}
            </MagneticLink>
            <LandingInfoDialog
              kind="community"
              className="inline-flex h-13 items-center rounded-full border border-border bg-background px-8 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            />
          </motion.div>
        </div>
      </motion.div>
    </section>
  )
}
