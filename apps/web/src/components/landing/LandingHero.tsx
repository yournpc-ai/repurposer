import { useEffect, useRef, useState } from "react"
import { Link } from "@tanstack/react-router"
import { ChevronDown } from "lucide-react"
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react"
import { useTranslation } from "react-i18next"

import { DEMO_PROJECT_SLUG } from "@/lib/constants"
import { useAuth } from "@/components/AuthProvider"
import RotatingText from "@/components/RotatingText"
import { Button } from "@/components/ui/button"

export function LandingHero() {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()
  const [mounted, setMounted] = useState(false)
  const reduceMotion = useReducedMotion()

  const sectionRef = useRef<HTMLElement>(null)
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  })
  const contentY = useTransform(scrollYProgress, [0, 1], [0, reduceMotion ? 0 : 120])
  const contentOpacity = useTransform(scrollYProgress, [0, 0.8], [1, reduceMotion ? 1 : 0])

  useEffect(() => {
    setMounted(true)
  }, [])

  const heroWords = t("landing.heroWords", { returnObjects: true }) as string[]

  return (
    <section
      ref={sectionRef}
      className="relative flex min-h-[calc(100svh-4rem)] flex-col items-center justify-center overflow-clip px-6"
    >
      <motion.div
        style={{ y: contentY, opacity: contentOpacity }}
        className="w-full max-w-3xl text-center"
      >
        <h1 className="mb-6 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-4xl font-bold tracking-tight sm:text-6xl">
          <span>{t("landing.heroPrefix")}</span>
          {mounted ? (
            <RotatingText
              texts={heroWords}
              rotationInterval={3000}
              splitBy="characters"
              staggerDuration={0.02}
              staggerFrom="random"
              mainClassName="text-primary"
              splitLevelClassName="overflow-hidden py-1"
            />
          ) : (
            <span className="text-primary">{heroWords[0]}</span>
          )}
        </h1>
        <p className="mx-auto mb-10 max-w-2xl text-base text-muted-foreground sm:text-lg">
          {t("landing.heroSubtitle")}
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3">
          {isAuthenticated ? (
            <Button size="lg" render={<Link to="/home" />}>
              {t("landing.getStarted")}
            </Button>
          ) : (
            <Button size="lg" onClick={() => setLoginOpen(true)}>
              {t("landing.getStarted")}
            </Button>
          )}
          <Button
            size="lg"
            variant="outline"
            render={
              <Link to="/projects/$id" params={{ id: DEMO_PROJECT_SLUG }} />
            }
          >
            {t("landing.viewDemo")}
          </Button>
        </div>
      </motion.div>

      {/* Scroll indicator */}
      <motion.button
        type="button"
        aria-label={t("landing.nav.features")}
        onClick={() =>
          document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })
        }
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1 }}
        className="absolute bottom-8 text-muted-foreground transition-colors hover:text-foreground"
      >
        <motion.div
          animate={reduceMotion ? undefined : { y: [0, 6, 0] }}
          transition={{ repeat: Infinity, duration: 1.8, ease: "easeInOut" }}
        >
          <ChevronDown className="h-5 w-5" />
        </motion.div>
      </motion.button>
    </section>
  )
}
