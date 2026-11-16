import { useNavigate } from "@tanstack/react-router"
import { Menu } from "lucide-react"
import { useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { LanguageSwitcher } from "@/components/language-switcher"
import { LogoMark } from "@/components/LogoMark"
import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
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
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            className="md:hidden"
            aria-label={t("landing.entry.navigation")}
          />
        }
      >
        <Menu className="size-4.5" aria-hidden="true" />
      </SheetTrigger>
      <SheetContent
        side="top"
        className="max-h-[calc(100dvh-1rem)] overflow-y-auto rounded-b-xl border-subtle p-0 shadow-floating md:hidden"
      >
        <SheetHeader className="border-b border-subtle p-5 pr-14">
          <SheetTitle className="flex items-center gap-2 text-base font-semibold tracking-tight">
            <LogoMark className="size-7" />
            Rookie Cut
          </SheetTitle>
          <SheetDescription className="sr-only">
            {t("landing.entry.navigation")}
          </SheetDescription>
        </SheetHeader>

        <nav aria-label={t("landing.entry.navigation")} className="p-3">
          <a
            href="#early-access"
            onClick={() => setOpen(false)}
            className="flex h-12 items-center rounded-md px-3 text-base text-foreground transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-foreground"
          >
            {t("landing.nav.earlyAccess")}
          </a>
          {[["#pricing", "landing.nav.pricing"], ["#faq", "landing.nav.faq"]].map(([href, key]) => (
            <a key={href} href={href} onClick={() => setOpen(false)} className="flex h-12 items-center rounded-md px-3 text-base transition-colors hover:bg-accent">{t(key)}</a>
          ))}
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
      </SheetContent>
    </Sheet>
  )
}
