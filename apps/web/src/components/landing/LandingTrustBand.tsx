import { Fingerprint, Languages, ReceiptText, ShieldCheck } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"

const ITEM_ICONS = [ShieldCheck, Languages, Fingerprint, ReceiptText]

interface TrustItem {
  title: string
  desc: string
}

export function LandingTrustBand() {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const items = t("landing.trust.items", { returnObjects: true }) as TrustItem[]

  return (
    <section className="px-6 py-16">
      <div className="mx-auto w-full max-w-6xl">
        <motion.h2
          initial={{ opacity: 0, y: reduceMotion ? 0 : 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5 }}
          className="mb-10 text-center text-2xl font-bold tracking-tight sm:text-3xl"
        >
          {t("landing.trust.heading")}
        </motion.h2>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((item, i) => {
            const Icon = ITEM_ICONS[i % ITEM_ICONS.length]
            return (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: reduceMotion ? 0 : 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.45, delay: reduceMotion ? 0 : i * 0.1 }}
                className="flex items-start gap-3 rounded-lg p-4"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="h-4.5 w-4.5" />
                </div>
                <div>
                  <h3 className="mb-1 text-sm font-semibold">{item.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {item.desc}
                  </p>
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
