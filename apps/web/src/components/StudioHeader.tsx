"use client"

import { Link, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { FolderKanban } from "lucide-react"

import { AccountMenu } from "@/components/app-sidebar"
import { CreditsPill } from "@/components/credits/CreditsPill"
import { LogoMark } from "@/components/LogoMark"
import { NotificationBell } from "@/components/notifications/NotificationBell"

export function StudioHeader() {
  const { t } = useTranslation()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const onProjects = pathname.startsWith("/projects")
  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between px-4 border-b border-border md:h-12 md:justify-end md:border-0">
      <Link
        to="/home"
        aria-label={t("nav.home")}
        className="-ml-2 md:hidden flex items-center gap-2 rounded-lg px-2 py-1 transition-colors active:bg-accent"
      >
        <LogoMark className="h-6 w-6" />
        <span className="font-semibold tracking-tight max-[400px]:hidden">Rookie Cut</span>
      </Link>

      <div className="flex items-center gap-1">
        <Link
          to="/projects"
          aria-label={t("nav.myProjects")}
          aria-current={onProjects ? "page" : undefined}
          className={`grid place-items-center md:hidden h-10 w-10 rounded-lg active:bg-accent ${
            onProjects ? "text-foreground" : "text-muted-foreground"
          }`}
        >
          <FolderKanban />
        </Link>
        <CreditsPill refreshKey={pathname} />
        <NotificationBell chip={false} />
        <div className="md:hidden">
          <AccountMenu />
        </div>
      </div>
    </header>
  )
}
