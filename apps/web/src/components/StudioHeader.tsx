"use client"

import { useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { PanelLeft } from "@/components/ui/icons"

import { CreditsPill } from "@/components/credits/CreditsPill"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import { useStudioHeaderSlot } from "@/components/StudioHeaderContext"
import { cn } from "@/lib/utils"

export function StudioHeader() {
  const { t } = useTranslation()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const onProjectChat = /^\/projects\/[^/]+/.test(pathname)
  const { left, actions, hideNotifications } = useStudioHeaderSlot()
  const hasRouteSlot = Boolean(left || actions)
  const showNotifications = !hideNotifications && !onProjectChat

  return (
    <header
      data-slot="studio-header"
      className={cn(
        "sticky top-0 z-30 flex h-12 shrink-0 items-center justify-between gap-2 bg-background/95 px-3 backdrop-blur-sm border-b border-border/40 md:border-b-0 md:bg-transparent md:px-4 md:backdrop-blur-none",
        !hasRouteSlot && "md:border-b-0 md:bg-transparent md:backdrop-blur-none",
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <button
          type="button"
          aria-label={t("a11y.openSidebar")}
          onClick={() =>
            window.dispatchEvent(new Event("repurposer:toggle-mobile-sidebar"))
          }
          className="-ml-1 grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground active:bg-accent md:hidden"
        >
          <PanelLeft className="size-4" />
        </button>

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
        <div className="hidden md:flex">
          <CreditsPill refreshKey={pathname} />
        </div>
        {actions ? (
          <div data-slot="studio-header-actions" className="flex items-center gap-1">
            {actions}
          </div>
        ) : null}
        {showNotifications ? <NotificationBell chip={false} /> : null}
      </div>
    </header>
  )
}
