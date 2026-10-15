import { Outlet, createFileRoute } from "@tanstack/react-router"
import { createServerFn } from "@tanstack/react-start"

import { AppSidebar } from "@/components/app-sidebar"
import { MobileHeader } from "@/components/mobile-header"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import {
  SIDEBAR_COOKIE_NAME,
  SidebarProvider,
  SidebarInset,
} from "@/components/ui/sidebar"

// Server-module imports are denied in the client bundle (same pattern as the
// root route's language cookie read).
const readSidebarCookieOnServer = createServerFn({ method: "GET" }).handler(
  async (): Promise<boolean> => {
    const { getCookie } = await import("@tanstack/react-start/server")
    return getCookie(SIDEBAR_COOKIE_NAME) === "true"
  }
)

/**
 * Pathless layout route for the authenticated studio: everything under
 * `_app` gets the sidebar chrome. The public landing page (`/`) lives
 * outside this layout.
 *
 * No global AppHeader on md+ (ADR-046 D5): utilities live in the account
 * console (rail footer); the notification bell is the single floating chrome
 * chip at the content area's top-right — the top-right slot is reserved
 * app-wide, page-level controls never take that corner. Below md the chrome
 * consolidates into the glass MobileHeader (2026-10-14 user ruling — the
 * two-entry nav doesn't deserve a bottom tab bar; the floating sidebar
 * trigger retires with it, the drawer is unreachable, and PC keeps
 * expanding/collapsing via the rail's hover-logo button or Cmd/Ctrl+B).
 *
 * The expanded/collapsed choice PERSISTS: the primitive writes the
 * `sidebar_state` cookie on every toggle and this loader reads it back, so
 * SSR and hydration render the same form (language-cookie precedent in
 * `__root.tsx`).
 */
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
  return (
    <SidebarProvider defaultOpen={sidebarOpen}>
      {/* Settings = a shared dialog rooted at __root.tsx (summonable from
          anywhere via useSettingsDialog) — the account console row and the
          /settings OAuth shim both ride that single seat. */}
      <AppSidebar />
      <SidebarInset className="relative overflow-x-clip">
        <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
          <div className="absolute -left-[20%] -top-[10%] h-[50%] w-[50%] rounded-full bg-primary/5 blur-[120px]" />
          <div className="absolute -right-[20%] top-[20%] h-[40%] w-[40%] rounded-full bg-primary/3 blur-[100px]" />
        </div>
        {/* Mobile chrome (stacked, never overlay): the glass header is the
            first IN-FLOW child — sticky top-0 pins it on window-scroll
            pages, whose content scrolls under the glass naturally; home is
            the one exception, its scrollport pulls up UNDER the glass
            (-mt-14) so the frost has something to blur. First child order
            keeps it above the Outlet in both paint and tab order. */}
        <MobileHeader />
        {/* …and the bell chip (top-right, reserved app-wide) — md+ only;
            below md the bell lives bare inside the MobileHeader. */}
        <div className="fixed right-4 top-4 z-40 hidden md:block">
          <NotificationBell />
        </div>
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  )
}
