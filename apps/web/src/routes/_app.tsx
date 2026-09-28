import { Outlet, createFileRoute } from "@tanstack/react-router"
import { createServerFn } from "@tanstack/react-start"

import { AppSidebar } from "@/components/app-sidebar"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import { SettingsDialogProvider } from "@/components/settings/SettingsDialog"
import {
  SIDEBAR_COOKIE_NAME,
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
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
 * No global AppHeader (ADR-046 D5): utilities live in the account console
 * (rail footer); the notification bell is the single floating chrome chip
 * at the content area's top-right — the top-right slot is reserved
 * app-wide, page-level controls never take that corner. Mobile keeps a
 * floating sidebar trigger (top-left); PC expands/collapses via the rail's
 * hover-logo button or Cmd/Ctrl+B (2026-09-27, ChatGPT parity).
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
      {/* Settings = a shared dialog (MiniMax/FLORA pattern), summonable from
          anywhere via useSettingsDialog — the provider wraps BOTH the
          sidebar (account console row) and the Outlet (the /settings OAuth
          shim). */}
      <SettingsDialogProvider>
      <AppSidebar />
      <SidebarInset className="relative overflow-x-clip">
        <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
          <div className="absolute -left-[20%] -top-[10%] h-[50%] w-[50%] rounded-full bg-primary/5 blur-[120px]" />
          <div className="absolute -right-[20%] top-[20%] h-[40%] w-[40%] rounded-full bg-primary/3 blur-[100px]" />
        </div>
        {/* Floating chrome: mobile sidebar trigger (top-left)… */}
        <SidebarTrigger className="fixed left-4 top-4 z-40 rounded-lg overlay-surface ring-1 ring-foreground/10 md:hidden" />
        {/* …and the bell chip (top-right, reserved app-wide). */}
        <div className="fixed right-4 top-4 z-40">
          <NotificationBell />
        </div>
        <Outlet />
      </SidebarInset>
      </SettingsDialogProvider>
    </SidebarProvider>
  )
}
