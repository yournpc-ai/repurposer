import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/components/AuthProvider"
import { LanguageSwitcher } from "@/components/language-switcher"
import { LogoMark } from "@/components/LogoMark"
import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"

const NAV_ITEMS = [
  { id: "product", key: "landing.nav.product" },
  { id: "how-it-works", key: "landing.nav.howItWorks" },
  { id: "pricing", key: "landing.nav.pricing" },
  { id: "faq", key: "landing.nav.faq" },
] as const

export function LandingHeader() {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()

  return (
    <header className="sticky top-0 z-50 backdrop-blur-md">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-6">
        <a href="#top" className="flex items-center gap-2">
          <LogoMark />
          <span className="font-semibold tracking-tight">Repurposer</span>
        </a>

        <nav className="hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className="inline-flex h-9 items-center rounded-md px-3 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              {t(item.key)}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <LanguageSwitcher />
          {isAuthenticated ? (
            <Button render={<Link to="/home" />}>{t("landing.openWorkbench")}</Button>
          ) : (
            <Button onClick={() => setLoginOpen(true)}>{t("landing.signIn")}</Button>
          )}
        </div>
      </div>
    </header>
  )
}
