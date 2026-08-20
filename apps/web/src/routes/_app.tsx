import { Outlet, createFileRoute } from "@tanstack/react-router"

import { AppSidebar } from "@/components/app-sidebar"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import { SettingsDialogProvider } from "@/components/settings/SettingsDialog"
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar"

/**
 * Pathless layout route for the authenticated studio: everything under
 * `_app` gets the sidebar chrome. The public landing page (`/`) lives
 * outside this layout.
 *
 * No global AppHeader (ADR-046 D5): utilities live in the account console
 * (rail footer); the notification bell is the single floating chrome chip
 * at the content area's top-right — the top-right slot is reserved
 * app-wide, page-level controls never take that corner. Mobile keeps a
 * floating sidebar trigger (top-left).
 */
export const Route = createFileRoute("/_app")({
  component: AppLayout,
})

function AppLayout() {
  return (
    <SidebarProvider defaultOpen={false}>
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
