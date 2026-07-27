import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/components/AuthProvider"
import { LanguageSwitcher } from "@/components/language-switcher"
import { LogoMark } from "@/components/LogoMark"
import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"

const NAV_ITEMS = [
  { id: "features", key: "landing.nav.features" },
  { id: "pricing", key: "landing.nav.pricing" },
  { id: "roadmap", key: "landing.nav.roadmap" },
] as const

function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })
}

export function LandingHeader() {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()

  return (
    <header className="sticky top-0 z-50 backdrop-blur-md">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-6">
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          className="flex items-center gap-2"
        >
          <LogoMark />
          <span className="font-semibold tracking-tight">Repurposer</span>
        </button>

        <nav className="hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map((item) => (
            <Button
              key={item.id}
              variant="ghost"
              size="sm"
              onClick={() => scrollToSection(item.id)}
            >
              {t(item.key)}
            </Button>
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
