import "@/studio.css"
import { Outlet, createFileRoute, useRouterState } from "@tanstack/react-router"
import { createServerFn } from "@tanstack/react-start"

import { AppSidebar } from "@/components/app-sidebar"
import { CreditsPill } from "@/components/credits/CreditsPill"
import { MobileHeader } from "@/components/mobile-header"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import {
  SIDEBAR_COOKIE_NAME,
  SidebarProvider,
} from "@/components/ui/sidebar"

// Server-module imports are denied in the client bundle (same pattern as the
// root route's language cookie read).
const readSidebarCookieOnServer = createServerFn({ method: "GET" }).handler(
  async (): Promise<boolean> => {
    const { getCookie } = await import("@tanstack/react-start/server")
    return getCookie(SIDEBAR_COOKIE_NAME) === "true"
  }
)

export const Route = createFileRoute("/_app")({
  loader: async (): Promise<{ sidebarOpen: boolean }> => {
    if (typeof document === "undefined") {
      return { sidebarOpen: await readSidebarCookieOnServer() }
    }
    const entry = document.cookie
      .split("; ")
      .find((row) => row.startsWith(`${SIDEBAR_COOKIE_NAME}=`))
    return { sidebarOpen: entry?.split("=")[1] === "true" }
  },
  component: AppLayout,
})

function AppLayout() {
  const { sidebarOpen } = Route.useLoaderData()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  return (
    <SidebarProvider defaultOpen={sidebarOpen} className="ui-as-app">
      <AppSidebar />
      <main className="ui-as-main">
        <MobileHeader />
        <div className="hidden h-12 shrink-0 items-center justify-end gap-1 px-4 md:flex">
          <CreditsPill refreshKey={pathname} />
          <NotificationBell chip={false} />
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </div>
      </main>
    </SidebarProvider>
  )
}
