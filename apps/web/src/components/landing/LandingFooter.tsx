import { Sparkles } from "lucide-react"
import { useTranslation } from "react-i18next"

export function LandingFooter() {
  const { t } = useTranslation()

  return (
    <footer className="px-6 py-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col items-center gap-3 text-center">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <span className="text-sm font-semibold tracking-tight">Repurposer</span>
        </div>
        <p className="text-sm text-muted-foreground">{t("landing.footer.tagline")}</p>
        <p className="text-xs text-muted-foreground">
          {t("landing.footer.rights", { year: new Date().getFullYear() })}
        </p>
      </div>
    </footer>
  )
}
