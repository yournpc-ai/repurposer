import {
  Home,
  Mic2,
  FolderKanban,
  ArrowLeftToLine,
  ArrowRightToLine,
  ChevronDown,
  User,
} from "lucide-react"
import { useEffect, useState } from "react"
import { Link, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { AccountConsole } from "@/components/account-console"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

import { getUser } from "@/lib/auth"
import { useAuth } from "@/components/AuthProvider"
import { LogoMark } from "@/components/LogoMark"

const navItems = [
  { key: "home", url: "/home", icon: Home },
  { key: "myProjects", url: "/projects", icon: FolderKanban },
  { key: "personas", url: "/personas", icon: Mic2 },
]

function isActive(path: string, itemUrl: string) {
  if (itemUrl === "#") return false
  return path === itemUrl || path.startsWith(`${itemUrl}/`)
}

export function AppSidebar() {
  const router = useRouterState()
  const currentPath = router.location.pathname
  const { t } = useTranslation()
  const { toggleSidebar, state } = useSidebar()
  const collapsed = state === "collapsed"
  const { isAuthenticated } = useAuth()

  // Re-read on every render; auth-state changes re-render via context.
  // Gated on mounted: getUser() reads localStorage, which the server cannot
  // see — rendering it pre-hydration mismatches SSR (访客 vs real name).
  const [mounted, setMounted] = useState(false)
  const [consoleOpen, setConsoleOpen] = useState(false)
  useEffect(() => setMounted(true), [])
  const user = mounted ? getUser() : null
  const displayName = user?.name || user?.email || t("common.guest")
  const initial = (user?.name || user?.email || "U").charAt(0).toUpperCase()

  const avatarTrigger = (
    <PopoverTrigger
      render={
        <Button
          variant="ghost"
          className="h-11 w-full justify-start gap-3 rounded-xl px-3 font-normal hover:bg-sidebar-accent hover:text-sidebar-accent-foreground data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground group-data-[state=collapsed]:h-10 group-data-[state=collapsed]:w-10 group-data-[state=collapsed]:justify-center group-data-[state=collapsed]:gap-0 group-data-[state=collapsed]:p-0"
        >
          <Avatar className="h-8 w-8 rounded-full group-data-[state=collapsed]:h-6 group-data-[state=collapsed]:w-6">
            <AvatarImage src="" alt={displayName} />
            <AvatarFallback className="rounded-full bg-sidebar-primary text-sidebar-primary-foreground text-[10px]">
              {isAuthenticated ? initial : <User className="h-3 w-3" />}
            </AvatarFallback>
          </Avatar>
          <div className="flex flex-1 flex-col items-start text-left group-data-[state=collapsed]:hidden">
            <span className="text-sm font-medium leading-none">{displayName}</span>
          </div>
          <ChevronDown className="h-4 w-4 text-muted-foreground group-data-[state=collapsed]:hidden" />
        </Button>
      }
    />
  )

  return (
    <Sidebar collapsible="icon" className="group-data-[side=left]:border-r-0">
      {/* The rail's 60px logo strip (py-4) — there is no global top bar
          (ADR-046 D5); utilities live in the account console, and the
          notification bell floats at the content area's top-right. */}
      <SidebarHeader className="gap-3 p-3 py-4 group-data-[state=collapsed]:items-center">
        <div className="flex w-full items-center justify-between group-data-[state=collapsed]:justify-center">
          <div className="flex items-center gap-2 group-data-[state=collapsed]:hidden">
            <LogoMark />
            <span className="font-semibold tracking-tight">Repurposer</span>
          </div>
          {/* PC collapsed rail: the toggle is retired (PC stays icon-only,
              2026-08-02) — the LogoMark takes its slot. Mobile keeps the
              toggle below; its off-canvas logic is untouched. */}
          <LogoMark className="hidden group-data-[state=collapsed]:md:block" />
          <Button
            variant="ghost"
            size="icon"
            className="relative h-8 w-8 shrink-0 rounded-md md:hidden"
            onClick={toggleSidebar}
            aria-label={t("a11y.toggleSidebar")}
          >
            <ArrowLeftToLine className="absolute inset-0 m-auto size-4.5 transition-opacity group-data-[state=collapsed]:opacity-0" />
            <ArrowRightToLine className="absolute inset-0 m-auto size-4.5 opacity-0 transition-opacity group-data-[state=collapsed]:opacity-100" />
          </Button>
        </div>
      </SidebarHeader>

      <SidebarContent className="gap-4 px-2">
        {/* Nav items top-align right under the header in both forms — only
            the user footer is pinned to the bottom (2026-08-30 ruling; the
            collapsed rail's vertical centering is retired). */}
        <SidebarGroup className="px-0 py-0">
          <SidebarGroupContent>
            <SidebarMenu className="gap-1">
              {navItems.map((item) => (
                <SidebarMenuItem key={item.key}>
                  <SidebarMenuButton
                    isActive={isActive(currentPath, item.url)}
                    tooltip={t(`nav.${item.key}`)}
                    className="h-10 text-sm"
                    render={<Link to={item.url} />}
                  >
                    <item.icon className="h-4.5 w-4.5 shrink-0" />
                    <span>{t(`nav.${item.key}`)}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="gap-3 p-2 group-data-[state=collapsed]:items-center">
        {/* Account console (ADR-046 D5): the avatar opens a Popover carrying
            inline controls (theme / language segmented, replay tour,
            logout) — never a DropdownMenu of links. */}
        <Popover open={consoleOpen} onOpenChange={setConsoleOpen}>
          {/* Collapsed: hovering the avatar shows who is signed in (the name
              row is hidden then); expanded it stays a plain click target. */}
          {collapsed ? (
            <Tooltip>
              <TooltipTrigger render={avatarTrigger} />
              <TooltipContent side="right">
                <p className="text-xs font-medium">{displayName}</p>
                {user?.email && user.email !== displayName && (
                  <p className="text-xs text-muted-foreground">{user.email}</p>
                )}
              </TooltipContent>
            </Tooltip>
          ) : (
            avatarTrigger
          )}
          <PopoverContent
            className="w-64 rounded-xl p-2"
            side="top"
            align="start"
            sideOffset={8}
          >
            <AccountConsole onClose={() => setConsoleOpen(false)} />
          </PopoverContent>
        </Popover>
      </SidebarFooter>
    </Sidebar>
  )
}
