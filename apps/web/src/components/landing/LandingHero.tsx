import { Link } from "@tanstack/react-router"
import { motion, useReducedMotion } from "motion/react"
import { Trans, useTranslation } from "react-i18next"

import { useAuth } from "@/components/AuthProvider"
import { Button } from "@/components/ui/button"

export function LandingHero() {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()
  const reduceMotion = useReducedMotion()

  return (
    <section className="relative flex flex-1 flex-col items-center justify-center overflow-clip px-6 py-16">
      {/* Reserved background layer — future hero art / particle field goes here.
          Keep it behind the content and transform/opacity-only for animation. */}
      <div aria-hidden data-slot="hero-background" className="absolute inset-0" />

      <motion.div
        initial={reduceMotion ? false : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="relative w-full max-w-3xl text-center"
      >
        <h1 className="mb-6 font-display text-[2.625rem] leading-[1.15] font-bold tracking-[-0.02em] text-balance sm:text-[3.25rem]">
          {t("landing.heroTitle1")}
          <br />
          <span className="inline-block">
            <span className="hero-iridescent">{t("landing.heroTitle2")}</span>
            <span aria-hidden className="hero-underline-bar" />
          </span>
        </h1>
        <p className="mx-auto mb-10 max-w-xl font-display text-[1.0625rem] leading-[1.65] text-pretty text-muted-foreground/75">
          <Trans
            i18nKey="landing.heroSubtitle"
            components={{ b: <strong className="font-semibold text-foreground" /> }}
          />
        </p>

        {isAuthenticated ? (
          <Button size="lg" className="h-12 px-8 text-base" render={<Link to="/home" />}>
            {t("landing.ctaTryBeta")}
          </Button>
        ) : (
          <Button
            size="lg"
            className="h-12 px-8 text-base"
            onClick={() => setLoginOpen(true)}
          >
            {t("landing.ctaTryBeta")}
          </Button>
        )}
      </motion.div>
    </section>
  )
}
