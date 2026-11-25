import { useNavigate } from "@tanstack/react-router"
import { ChevronDown, Menu } from "lucide-react"
import { useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { LanguageSwitcher } from "@/components/language-switcher"
import { IconButton } from "@/components/ui/icon-button-clean"
import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { FeatureList } from "./FeatureList"
import { useAuth } from "@/lib/auth-context"

export function MobileNavigation(): ReactNode {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  const createVideo = (): void => {
    setOpen(false)
    if (isAuthenticated) void navigate({ to: "/home" })
    else setLoginOpen(true)
  }

  return (
    <div className="md:hidden">
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Rookie"
        closeLabel={t("common.close")}
        trigger={<IconButton label={t("landing.entry.navigation")} icon={<Menu />} />}
      >
        <nav aria-label={t("landing.entry.navigation")} className="p-3">
          <a
            href="#early-access"
            onClick={() => setOpen(false)}
            className="flex h-12 items-center rounded-md px-3 text-base text-foreground transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-foreground"
          >
            {t("landing.nav.earlyAccess")}
          </a>
          <details className="group">
            <summary className="flex h-12 cursor-pointer list-none items-center justify-between rounded-md px-3 text-base hover:bg-accent [&::-webkit-details-marker]:hidden">
              {t("landing.nav.features")}
              <ChevronDown aria-hidden="true" className="size-4 text-muted-foreground group-open:rotate-180" />
            </summary>
            <FeatureList className="grid gap-4 px-3 py-3" />
          </details>
          <a
            href="#faq"
            onClick={() => setOpen(false)}
            className="flex h-12 items-center rounded-md px-3 text-base transition-colors hover:bg-accent"
          >
            {t("landing.nav.faq")}
          </a>
        </nav>

        <div className="flex items-center gap-5 border-t border-subtle px-6 py-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <ThemeToggle />
            <span>{t("common.toggleTheme")}</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <LanguageSwitcher />
            <span>{t("common.language")}</span>
          </div>
        </div>
        <div className="p-5 pt-2">
          <Button size="lg" className="w-full text-sm" onClick={createVideo}>
            {t("landing.headerCta")}
          </Button>
        </div>
      </Dialog>
    </div>
  )
}
