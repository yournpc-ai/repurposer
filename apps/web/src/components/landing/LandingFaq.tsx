import { useEffect, useRef, useState } from "react"
import { Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
import { LANDING_CONTAINER } from "./layout"
import { useReducedMotion } from "./motion"
import { cn } from "@/lib/utils"

export function LandingFaq() {
  const { t } = useTranslation()
  const reduce = useReducedMotion()
  const content = useRef<HTMLDivElement>(null)
  const [fits, setFits] = useState(false)
  const hold = !reduce && fits
  useEffect(() => {
    const element = content.current
    if (!element) return
    const measure = () => setFits(element.getBoundingClientRect().height <= window.innerHeight - 128)
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    measure()
    window.addEventListener("resize", measure)
    return () => { observer.disconnect(); window.removeEventListener("resize", measure) }
  }, [])
  const pricing = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    const revealPricing = () => { if (window.location.hash === "#pricing" && pricing.current) pricing.current.open = true }
    revealPricing()
    window.addEventListener("hashchange", revealPricing)
    return () => window.removeEventListener("hashchange", revealPricing)
  }, [])
  return <section id="faq" className={cn("scroll-mt-24 py-20 sm:py-28", hold && "lg:h-[160svh] lg:py-0")}>
    <div className={cn(LANDING_CONTAINER, hold && "lg:sticky lg:top-20 lg:flex lg:h-[calc(100svh-5rem)] lg:flex-col lg:justify-center lg:py-6")}>
      <div ref={content}>
      <h2 className="mb-12 text-center font-display text-3xl tracking-tight sm:text-4xl">{t("landing.faqSection.title")}</h2>
      <div className="mx-auto max-w-3xl">
        {["experience", "material", "revision", "pricing", "download"].map((key) => <details key={key} name="landing-faq" ref={key === "pricing" ? pricing : undefined} id={key === "pricing" ? "pricing" : undefined} className="group scroll-mt-28 border-b border-subtle py-6">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-6 text-base sm:text-lg [&::-webkit-details-marker]:hidden">
            {t(`landing.faqSection.${key}.question`)}<Plus className="size-4 shrink-0 transition-transform group-open:rotate-45" />
          </summary>
          <p className="mt-4 max-w-2xl pr-8 text-sm leading-7 text-muted-foreground sm:text-base">{t(`landing.faqSection.${key}.answer`)}</p>
        </details>)}
      </div>
      </div>
    </div>
  </section>
}
