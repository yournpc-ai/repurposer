import { useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button-clean"
import { LANDING_CONTAINER } from "./layout"

export function LandingHero() {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()
  const navigate = useNavigate()
  return (
    <section className="pt-12 pb-14 text-center sm:pt-16 sm:pb-16 lg:pt-8 lg:pb-12">
      <div className={LANDING_CONTAINER}>
        <p className="text-sm text-muted-foreground sm:text-base">{t("landing.heroEyebrow")}</p>
        <h1 className="mx-auto mt-6 max-w-6xl font-hero text-[clamp(40px,6.3vw,72px)] leading-[1.06] font-normal tracking-tight text-balance">
          {t("landing.heroTitle")}
        </h1>
        <Button size="lg" className="mt-12 rounded-full px-8 text-sm font-normal sm:text-base" onClick={() => {
          if (isAuthenticated) void navigate({ to: "/home" })
          else setLoginOpen(true)
        }}>{t("landing.heroCta")}</Button>
      </div>
    </section>
  )
}
