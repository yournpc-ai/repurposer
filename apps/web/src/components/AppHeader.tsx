import { LanguageSwitcher } from "@/components/language-switcher"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import { ThemeToggle } from "@/components/theme-toggle"
import { SidebarTrigger } from "@/components/ui/sidebar"

/** Global top bar — sticky against window scroll (SidebarInset must not clip
 * overflow on the vertical axis or sticky breaks). Replaces the per-route
 * fake headers that scrolled away with the content. z-40 keeps it above
 * in-flow page content (card internals use z-10/z-20) but below the auth
 * wall (z-40, later in DOM) and modals/overlays (z-50). */
export function AppHeader() {
  return (
    <header className="sticky top-0 z-40 flex items-center justify-between bg-background px-6 py-4">
      {/* Mobile-only: on desktop the sidebar header has its own collapse
       * button; on mobile the sidebar is a hidden sheet and this trigger is
       * the only way to open it. */}
      <SidebarTrigger className="md:hidden" />
      <div className="ml-auto flex items-center gap-3">
        <ThemeToggle />
        <LanguageSwitcher />
        <NotificationBell />
      </div>
    </header>
  )
}
