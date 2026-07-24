import { Star } from "lucide-react"

import { LanguageSwitcher } from "@/components/language-switcher"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import { ThemeToggle } from "@/components/theme-toggle"
import { SidebarTrigger } from "@/components/ui/sidebar"

/** Global top bar — sticky against window scroll (SidebarInset must not clip
 * overflow on the vertical axis or sticky breaks). Replaces the per-route
 * fake headers that scrolled away with the content. */
export function AppHeader() {
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between bg-background px-6 py-4">
      {/* Mobile-only: on desktop the sidebar header has its own collapse
       * button; on mobile the sidebar is a hidden sheet and this trigger is
       * the only way to open it. */}
      <SidebarTrigger className="md:hidden" />
      <div className="ml-auto flex items-center gap-3">
        <ThemeToggle />
        <LanguageSwitcher />
        <NotificationBell />
        <div className="flex h-7 items-center gap-2 rounded-md bg-card px-3 text-sm ring-1 ring-border">
          <Star className="h-4 w-4 fill-amber-400 text-amber-500" />
          <span>0</span>
        </div>
      </div>
    </header>
  )
}
