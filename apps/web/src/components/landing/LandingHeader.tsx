import { ChevronDown } from "lucide-react"
import { useEffect, useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { LogoMark } from "@/components/LogoMark"
import { ThemeToggle } from "@/components/theme-toggle"
import { LanguageSwitcher } from "@/components/language-switcher"
import { Button } from "@/components/ui/button-clean"
import { Popover } from "@/components/ui/popover-clean"
import { FeatureList } from "./FeatureList"
import { cn } from "@/lib/utils"
import { LANDING_HEADER_CONTAINER } from "./layout"
import { useLandingCreate } from "./useLandingCreate"
import { MobileNavigation } from "./MobileNavigation"

export function LandingHeader() {
  const { t } = useTranslation()
  const featuresId = useId()
  const [featuresOpen, setFeaturesOpen] = useState(false)
  const create = useLandingCreate()
  const [condensed, setCondensed] = useState(false)
  useEffect(() => {
    let frame = 0
    const update = () => {
      const story = document.getElementById("how-it-works")
      if (story) setCondensed(story.getBoundingClientRect().top <= 80)
    }
    const schedule = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(update)
    }
    update()
    window.addEventListener("scroll", schedule, { passive: true })
    window.addEventListener("resize", schedule)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener("scroll", schedule)
      window.removeEventListener("resize", schedule)
    }
  }, [])
  return <header className={cn("pointer-events-none sticky top-0 z-50 h-16", !condensed && "bg-background", condensed && "md:pt-2")}>
    <div className={cn(
      LANDING_HEADER_CONTAINER,
      "pointer-events-auto grid h-16 grid-cols-[1fr_auto] items-center gap-5 bg-background transition-all duration-500 ease-in-out motion-reduce:transition-none md:grid-cols-[1fr_auto_1fr]",
      condensed && "md:h-14 md:w-[calc(100%_-_2rem)] md:max-w-[1100px] md:rounded-full md:px-4 md:pr-1.5 md:landing-header-glass lg:px-4 lg:pr-1.5",
    )}>
      <a href="#top" className="flex items-center justify-self-start gap-2 text-lg font-semibold tracking-tight"><LogoMark className="size-6" />Rookie</a>
      <nav aria-label={t("landing.entry.navigation")} className="hidden items-center justify-self-center gap-8 md:flex">
        <div
          onMouseEnter={() => setFeaturesOpen(true)}
          onMouseLeave={() => setFeaturesOpen(false)}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) setFeaturesOpen(false)
          }}
        >
          <Button
            variant="ghost"
            aria-expanded={featuresOpen}
            aria-controls={featuresOpen ? featuresId : undefined}
            onFocus={() => setFeaturesOpen(true)}
            onClick={() => setFeaturesOpen(true)}
            iconRight={<ChevronDown aria-hidden="true" />}
          >
            {t("landing.nav.features")}
          </Button>
          <Popover
            open={featuresOpen}
            onClose={() => setFeaturesOpen(false)}
            id={featuresId}
            aria-label={t("landing.nav.features")}
            role="region"
            className="rounded-xl backdrop-blur-xl"
            align="center"
            offset={0}
            width={520}
            focusOnOpen={false}
            unstyled
          >
            <FeatureList className="overlay-surface grid grid-cols-2 gap-x-7 gap-y-5 rounded-xl p-6 supports-[backdrop-filter:blur(1px)]:bg-popover/90" />
          </Popover>
        </div>
        <a href="#faq" className="text-sm transition-colors hover:text-muted-foreground">{t("landing.nav.faq")}</a>
      </nav>
      <div className="hidden items-center justify-self-end gap-3 md:flex">{!condensed && <><ThemeToggle /><LanguageSwitcher /></>}<Button size="md" className="rounded-full px-5 text-sm font-normal" onClick={() => create()}>{t("landing.headerCta")}</Button></div>
      <MobileNavigation />
    </div>
  </header>
}
