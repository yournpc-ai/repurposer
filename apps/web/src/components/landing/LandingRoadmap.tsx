import { Check, Clock } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"

export function LandingRoadmap() {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const shipped = t("landing.roadmap.shipped", { returnObjects: true }) as string[]
  const next = t("landing.roadmap.next", { returnObjects: true }) as string[]

  return (
    <section id="roadmap" className="scroll-mt-16 px-6 py-24">
      <div className="mx-auto w-full max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: reduceMotion ? 0 : 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
          className="mb-14 text-center"
        >
          <h2 className="mb-3 text-3xl font-bold tracking-tight sm:text-4xl">
            {t("landing.roadmap.heading")}
          </h2>
          <p className="text-base text-muted-foreground sm:text-lg">
            {t("landing.roadmap.subheading")}
          </p>
        </motion.div>

        <div className="grid gap-6 md:grid-cols-2">
          <motion.div
            initial={{ opacity: 0, x: reduceMotion ? 0 : -32 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5 }}
            className="rounded-lg bg-card p-6 shadow-lg sm:p-8"
          >
            <h3 className="mb-5 text-lg font-semibold">
              {t("landing.roadmap.shippedTitle")}
            </h3>
            <ul className="flex flex-col gap-3">
              {shipped.map((item) => (
                <li key={item} className="flex items-start gap-3 text-sm">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: reduceMotion ? 0 : 32 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5, delay: reduceMotion ? 0 : 0.1 }}
            className="rounded-lg bg-card p-6 shadow-lg sm:p-8"
          >
            <h3 className="mb-5 text-lg font-semibold">
              {t("landing.roadmap.nextTitle")}
            </h3>
            <ul className="flex flex-col gap-3">
              {next.map((item) => (
                <li
                  key={item}
                  className="flex items-start gap-3 text-sm text-muted-foreground"
                >
                  <Clock className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
