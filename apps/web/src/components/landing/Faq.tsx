import { AnimatePresence, motion } from "motion/react"
import { Plus } from "lucide-react"
import { useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { softEase, useReducedMotion } from "@/components/landing/motion"
import { SectionHeading } from "@/components/landing/SectionHeading"

const FAQ_KEYS = ["q1", "q2", "q3", "q4", "q5", "q6"] as const

function FaqItem({
  itemKey,
  index,
  isOpen,
  onToggle,
}: {
  itemKey: string
  index: number
  isOpen: boolean
  onToggle: () => void
}): ReactNode {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const panelId = `faq-panel-${index}`
  const buttonId = `faq-button-${index}`

  return (
    <div className="border-t border-border last:border-b">
      <h3>
        <button
          id={buttonId}
          type="button"
          aria-expanded={isOpen}
          aria-controls={panelId}
          onClick={onToggle}
          className="flex w-full items-center justify-between gap-6 py-6 text-left"
        >
          <span className="text-base font-medium tracking-tight text-foreground sm:text-lg">
            {t(`landing.faq.items.${itemKey}.q`)}
          </span>
          <motion.span
            animate={{ rotate: isOpen ? 45 : 0 }}
            transition={
              prefersReducedMotion
                ? { duration: 0.01 }
                : { duration: 0.3, ease: softEase }
            }
            className="shrink-0 text-muted-foreground"
          >
            <Plus className="size-5" strokeWidth={1.75} aria-hidden="true" />
          </motion.span>
        </button>
      </h3>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            id={panelId}
            role="region"
            aria-labelledby={buttonId}
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={
              prefersReducedMotion
                ? { duration: 0.01 }
                : { duration: 0.4, ease: softEase }
            }
            className="overflow-hidden"
          >
            <p className="max-w-2xl pb-7 text-sm leading-relaxed text-muted-foreground">
              {t(`landing.faq.items.${itemKey}.a`)}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function Faq(): ReactNode {
  const { t } = useTranslation()
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  return (
    <section
      id="faq"
      className="mx-auto max-w-[1440px] scroll-mt-24 px-5 pb-24 sm:px-8 sm:pb-32 lg:px-10"
    >
      <div className="grid gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:gap-20">
        <SectionHeading
          title={t("landing.faq.title")}
          description={t("landing.faq.description")}
        />

        <div>
          {FAQ_KEYS.map((key, i) => (
            <FaqItem
              key={key}
              itemKey={key}
              index={i}
              isOpen={openIndex === i}
              onToggle={() => setOpenIndex((cur) => (cur === i ? null : i))}
            />
          ))}
        </div>
      </div>
    </section>
  )
}
