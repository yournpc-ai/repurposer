import { Check } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"

export function LandingPricing() {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const principles = t("landing.pricing.principles", {
    returnObjects: true,
  }) as string[]

  return (
    <section id="pricing" className="scroll-mt-16 px-6 py-24">
      <motion.div
        initial={{ opacity: 0, y: reduceMotion ? 0 : 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.5 }}
        className="mx-auto w-full max-w-3xl text-center"
      >
        <Badge className="mb-4 rounded-md">{t("landing.pricing.comingSoon")}</Badge>
        <h2 className="mb-3 text-3xl font-bold tracking-tight sm:text-4xl">
          {t("landing.pricing.heading")}
        </h2>
        <p className="mx-auto mb-8 max-w-2xl text-base text-muted-foreground sm:text-lg">
          {t("landing.pricing.subheading")}
        </p>

        <ul className="mx-auto flex max-w-md flex-col items-start gap-3 text-left sm:max-w-none sm:flex-row sm:items-center sm:justify-center sm:gap-8">
          {principles.map((item) => (
            <li key={item} className="flex items-center gap-2 text-sm">
              <Check className="h-4 w-4 shrink-0 text-primary" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </motion.div>
    </section>
  )
}
