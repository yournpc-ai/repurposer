import { useNavigate } from "@tanstack/react-router"
import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { LANDING_CONTAINER } from "@/components/landing/layout"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth-context"
import { useReducedMotion } from "./motion"
import { cn } from "@/lib/utils"

export function EarlyAccess(): ReactNode {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()
  const navigate = useNavigate()
  const reduce = useReducedMotion()

  const createVideo = (): void => {
    if (isAuthenticated) void navigate({ to: "/home" })
    else setLoginOpen(true)
  }

  return (
    <section
      id="early-access"
      aria-labelledby="early-access-title"
      className={cn("scroll-mt-24 py-20 sm:py-24", !reduce && "lg:min-h-[150svh] lg:py-0")}
    >
      <div className={cn(LANDING_CONTAINER, !reduce && "lg:sticky lg:top-20 lg:flex lg:min-h-[calc(100svh-5rem)] lg:flex-col lg:justify-center lg:py-8")}>
        <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
          <h2
            id="early-access-title"
            className="font-display text-3xl leading-[1.08] font-medium tracking-tight text-balance text-foreground sm:text-4xl"
          >
            {t("landing.earlyAccess.title")}
          </h2>
          <p className="mt-6 max-w-xl text-base leading-7 text-pretty text-muted-foreground sm:text-lg sm:leading-8">
            {t("landing.earlyAccess.description")}
          </p>
          <Button
            size="lg"
            className="mt-8 w-full px-7 text-sm sm:w-auto"
            onClick={createVideo}
          >
            {t("landing.openStudio")}
          </Button>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            {t("landing.earlyAccess.credits")}
          </p>
        </div>
      </div>
    </section>
  )
}
