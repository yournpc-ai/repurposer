import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button-clean"
import { LANDING_CONTAINER } from "./layout"
import { useLandingCreate } from "./useLandingCreate"

export function EarlyAccess() {
  const { t } = useTranslation()
  const create = useLandingCreate()

  return (
    <section id="early-access" aria-labelledby="early-access-title" className="scroll-mt-24 pt-16 pb-10 text-center sm:pt-24 sm:pb-16">
      <div className={LANDING_CONTAINER}>
        <h2 id="early-access-title" className="mx-auto max-w-3xl font-hero text-[clamp(2.25rem,5vw,4rem)] leading-[1.1] font-normal tracking-tight text-balance">
          {t("landing.earlyAccess.title")}
        </h2>
        <p className="mx-auto mt-5 max-w-lg text-base leading-relaxed text-balance text-muted-foreground sm:text-lg">
          {t("landing.earlyAccess.description")}
        </p>
        <div className="mt-8 sm:mt-10">
          <Button size="lg" className="w-full rounded-full px-8 text-sm font-normal sm:w-auto sm:text-base" onClick={() => create()}>
            {t("landing.openStudio")}
          </Button>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            {t("landing.earlyAccess.credits")}
          </p>
        </div>
      </div>
    </section>
  )
}
