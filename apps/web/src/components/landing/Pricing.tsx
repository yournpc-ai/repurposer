import { AnimatePresence, motion } from "motion/react"
import { Check } from "lucide-react"
import { useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { softEase, useReducedMotion } from "@/components/landing/motion"
import { SectionHeading } from "@/components/landing/SectionHeading"
import { cn } from "@/lib/utils"

/**
 * Pricing with the template's sliding billing toggle + rolling price digits.
 * The highlighted tier uses the inverted --inverse panel.
 */

const TIERS = [
  {
    key: "free",
    monthly: 0,
    yearly: 0,
    featureKeys: ["f1", "f2", "f3", "f4"],
  },
  {
    key: "pro",
    monthly: 19,
    yearly: 15,
    featureKeys: ["f1", "f2", "f3", "f4", "f5"],
  },
  {
    key: "institution",
    monthly: 79,
    yearly: 63,
    featureKeys: ["f1", "f2", "f3", "f4"],
  },
] as const

type Tier = (typeof TIERS)[number]

function PriceValue({
  value,
  yearly,
  reduce,
}: {
  value: number
  yearly: boolean
  reduce: boolean
}): ReactNode {
  const enterY = reduce ? 0 : yearly ? "-110%" : "110%"
  const exitY = reduce ? 0 : yearly ? "110%" : "-110%"

  return (
    <span className="relative inline-flex overflow-hidden leading-none tabular-nums">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={value}
          initial={{ y: enterY, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: exitY, opacity: 0 }}
          transition={{ duration: reduce ? 0.001 : 0.45, ease: softEase }}
        >
          {value}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}

function BillingToggle({
  yearly,
  setYearly,
  reduce,
}: {
  yearly: boolean
  setYearly: (value: boolean) => void
  reduce: boolean
}): ReactNode {
  const { t } = useTranslation()
  const options = [
    { id: "monthly", label: t("landing.pricing.monthly"), value: false },
    { id: "yearly", label: t("landing.pricing.yearly"), value: true },
  ] as const

  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-border bg-muted p-1">
      {options.map((option) => {
        const isActive = option.value === yearly
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => setYearly(option.value)}
            aria-pressed={isActive}
            className="relative rounded-full px-5 py-2 text-sm font-medium"
          >
            {isActive && (
              <motion.span
                layoutId="billing-toggle-active"
                className="absolute inset-0 rounded-full bg-background shadow-sm"
                transition={
                  reduce
                    ? { duration: 0.001 }
                    : { type: "spring", stiffness: 420, damping: 34 }
                }
              />
            )}
            <span
              className={cn(
                "relative z-10 transition-colors",
                isActive ? "text-foreground" : "text-muted-foreground"
              )}
            >
              {option.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function TierCard({
  tier,
  yearly,
  reduce,
}: {
  tier: Tier
  yearly: boolean
  reduce: boolean
}): ReactNode {
  const { t } = useTranslation()
  const tierKey = tier.key
  const highlighted = tierKey === "pro"
  const price = yearly ? tier.yearly : tier.monthly

  return (
    <article
      className={cn(
        "flex h-full flex-col rounded-3xl p-7 sm:p-8",
        highlighted
          ? "bg-inverse text-inverse-foreground"
          : "border border-border"
      )}
    >
      <header className="flex items-center justify-between gap-4">
        <h3 className="text-lg font-medium tracking-tight">
          {t(`landing.pricing.tiers.${tierKey}.name`)}
        </h3>
        {highlighted && (
          <span className="rounded-full border border-current/25 px-2.5 py-1 text-[11px] leading-none font-medium">
            {t("landing.pricing.mostPopular")}
          </span>
        )}
      </header>
      <p
        className={cn(
          "mt-1.5 text-sm",
          highlighted ? "opacity-65" : "text-muted-foreground"
        )}
      >
        {t(`landing.pricing.tiers.${tierKey}.blurb`)}
      </p>

      <div className="mt-8 flex items-end">
        <span className="self-start pt-1 text-xl font-medium tracking-tight">€</span>
        <span className="text-5xl leading-none font-medium tracking-tight">
          <PriceValue value={price} yearly={yearly} reduce={reduce} />
        </span>
        <span
          className={cn(
            "ml-2 pb-0.5 text-sm",
            highlighted ? "opacity-65" : "text-muted-foreground"
          )}
        >
          {t("landing.pricing.perMonth")}
        </span>
      </div>
      <p
        className={cn(
          "mt-2 h-4 text-xs",
          highlighted ? "opacity-65" : "text-muted-foreground"
        )}
      >
        {tier.monthly === 0
          ? t("landing.pricing.freeForever")
          : yearly
            ? t("landing.pricing.billedYearly")
            : t("landing.pricing.billedMonthly")}
      </p>

      <ul className="mt-8 flex-1 space-y-3">
        {tier.featureKeys.map((featureKey) => {
          const feature = t(`landing.pricing.tiers.${tierKey}.features.${featureKey}`)
          return (
            <li key={featureKey} className="flex items-start gap-2.5">
              <Check
                className={cn(
                  "mt-0.5 size-4 shrink-0",
                  highlighted ? "opacity-80" : "text-foreground"
                )}
                strokeWidth={2}
                aria-hidden="true"
              />
              <span
                className={cn(
                  "text-sm leading-relaxed",
                  highlighted ? "opacity-80" : "text-muted-foreground"
                )}
              >
                {feature}
              </span>
            </li>
          )
        })}
      </ul>

      <a
        href="#sign-up"
        className={cn(
          "mt-9 inline-flex h-12 items-center justify-center rounded-full text-sm font-medium transition-opacity hover:opacity-85",
          highlighted
            ? "bg-inverse-foreground text-inverse"
            : "border border-border text-foreground hover:bg-muted hover:opacity-100"
        )}
      >
        {t(`landing.pricing.tiers.${tierKey}.cta`)}
      </a>
    </article>
  )
}

export function Pricing(): ReactNode {
  const { t } = useTranslation()
  const reduce = useReducedMotion()
  const [yearly, setYearly] = useState(false)

  return (
    <section
      id="pricing"
      className="mx-auto flex min-h-svh w-full max-w-[1440px] scroll-mt-24 flex-col justify-center px-5 pb-24 sm:px-8 sm:pb-32 lg:px-10"
    >
      <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
        <SectionHeading
          title={t("landing.pricing.title")}
          description={t("landing.pricing.description")}
        />
        <div className="shrink-0">
          <BillingToggle yearly={yearly} setYearly={setYearly} reduce={reduce} />
        </div>
      </div>

      <div className="mt-14 grid gap-4 lg:grid-cols-3">
        {TIERS.map((tier) => (
          <TierCard key={tier.key} tier={tier} yearly={yearly} reduce={reduce} />
        ))}
      </div>

      <p className="mt-6 text-xs text-muted-foreground">
        {t("landing.pricing.footnote")}
      </p>
    </section>
  )
}
