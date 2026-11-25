"use client"

import { Link, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { FolderKanban } from "lucide-react"

import { AccountMenu } from "@/components/app-sidebar"
import { CreditsPill } from "@/components/credits/CreditsPill"
import { LogoMark } from "@/components/LogoMark"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import { useStudioHeaderSlot } from "@/components/StudioHeaderContext"
import { cn } from "@/lib/utils"

export function StudioHeader() {
  const { t } = useTranslation()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const onProjects = pathname.startsWith("/projects")
  const { left, actions } = useStudioHeaderSlot()
  const hasRouteSlot = Boolean(left || actions)

  return (
    <header
      data-slot="studio-header"
      className={cn(
        "sticky top-0 z-30 flex h-12 shrink-0 items-center justify-between gap-2 bg-background/95 px-4 backdrop-blur-sm border-b border-border",
        !hasRouteSlot && "md:border-b-0 md:bg-transparent md:backdrop-blur-none",
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Link
          to="/home"
          aria-label={t("nav.home")}
          className="-ml-2 flex shrink-0 items-center gap-2 rounded-lg px-2 py-1 transition-colors active:bg-accent md:hidden"
        >
          <LogoMark className="h-6 w-6" />
          {!left && (
            <span className="font-semibold tracking-tight max-[400px]:hidden">
              RookieCut
            </span>
          )}
        </Link>

        {left ? (
          <div
            data-slot="studio-header-left"
            className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden"
          >
            {left}
          </div>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {actions ? (
          <>
            <div data-slot="studio-header-actions" className="flex items-center gap-1">
              {actions}
            </div>
            <span
              aria-hidden="true"
              data-slot="studio-header-divider"
              className="mx-1 h-3.5 w-px shrink-0 bg-border"
            />
          </>
        ) : null}

        <Link
          to="/projects"
          aria-label={t("nav.myProjects")}
          aria-current={onProjects ? "page" : undefined}
          className={cn(
            "grid h-9 w-9 place-items-center rounded-lg active:bg-accent md:hidden",
            onProjects ? "text-foreground" : "text-muted-foreground",
          )}
        >
          <FolderKanban className="size-4" />
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
