import {
  Home,
  FolderKanban,
  PanelLeft,
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
import { useAuth } from "@/lib/auth-context"
import { LogoMark } from "@/components/LogoMark"
import { cn } from "@/lib/utils"

const navItems = [
  { key: "home", url: "/home", icon: Home },
  { key: "myProjects", url: "/projects", icon: FolderKanban },
  // Personas nav hidden 2026-09-23 (user ruling): returns with the
  // positioning / memory ops-layer iteration (docs/POSITIONING.md) — the
  // /personas route itself stays alive, only the entries go away. Restore
  // together with the composer's Persona button (HomeComposer).
  // { key: "personas", url: "/personas", icon: Mic2 },
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

  /* The trigger is a NATIVE button (PopoverTrigger's default render), not a
     Button component — no variant fills to fight. The expanded row's hover/
     open fill lives on the footer container below, so the whole row
     (avatar + text + upgrade pill) reads as ONE unit; only the collapsed
     rail gives this button its own hover fill. */
  const avatarTrigger = (
    <PopoverTrigger className="flex h-11 min-w-0 flex-1 cursor-pointer items-center justify-start gap-3 rounded-xl px-3 text-left font-normal transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/30 group-data-[state=collapsed]:h-10 group-data-[state=collapsed]:w-10 group-data-[state=collapsed]:flex-none group-data-[state=collapsed]:justify-center group-data-[state=collapsed]:gap-0 group-data-[state=collapsed]:p-0 group-data-[state=collapsed]:hover:bg-sidebar-accent">
      <Avatar className="h-8 w-8 rounded-full group-data-[state=collapsed]:h-6 group-data-[state=collapsed]:w-6">
        <AvatarImage src="" alt={displayName} />
        <AvatarFallback className="rounded-full bg-sidebar-primary text-sidebar-primary-foreground text-[10px]">
          {isAuthenticated ? initial : <User className="h-3 w-3" />}
        </AvatarFallback>
      </Avatar>
      <div className="flex min-w-0 flex-1 flex-col items-start gap-1 text-left group-data-[state=collapsed]:hidden">
        <span className="w-full truncate text-sm font-medium leading-none">{displayName}</span>
        {isAuthenticated && (
          <span className="text-xs leading-none text-muted-foreground">
            {t("common.freePlan")}
          </span>
        )}
      </div>
    </PopoverTrigger>
  )

  return (
    <Sidebar collapsible="icon" className="border-sidebar-border">
      {/* Header renders in the EXPANDED form only (PC expanded + mobile
          off-canvas): logo lockup + the collapse toggle on the right
          (ChatGPT anatomy, 2026-09-27). The collapsed PC rail carries no
          header — there, the hover-swap LogoMark in the content stack below
          IS the expand entry. There is no global top bar (ADR-046 D5);
          utilities live in the account console, and the notification bell
          floats at the content area's top-right. */}
      <SidebarHeader className="gap-3 p-3 py-4 group-data-[state=collapsed]:md:hidden">
        <div className="flex w-full items-center justify-between">
          <div className="flex items-center gap-2">
            <LogoMark />
            <span className="font-semibold tracking-tight">Repurposer</span>
          </div>
          {/* Collapse toggle (ChatGPT anatomy, 2026-09-27): a single quiet
              PanelLeft glyph — the same icon family as the rail's hover
              expand button and SidebarTrigger — muted at rest, foreground
              on hover. (The old ArrowLeftToLine pair read as "back", not
              "collapse sidebar", and its state crossfade was dead weight:
              the header only ever renders in the expanded form.) */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 rounded-md text-muted-foreground hover:text-foreground"
            onClick={toggleSidebar}
            aria-label={t("a11y.toggleSidebar")}
          >
            <PanelLeft className="size-4.5" />
          </Button>
        </div>
      </SidebarHeader>

      <SidebarContent className="gap-4 px-2 group-data-[state=collapsed]:gap-5 group-data-[state=collapsed]:pt-4">
        {/* Collapsed rail = ONE top stack (Lovart nav-bar-next-top anatomy
            2026-08-31, container 36×216 exactly): the logo slot (24px —
            downsized from 28px 2026-09-27 after a same-crop ChatGPT
            comparison: their ~22px line glyph vs our 28px solid tile read
            a full register too heavy; 24px keeps one size step clear of
            the 36px menu items) as first member, stack gap-5 (20px) down
            to the menu group, menu items internally gap-1 (40px pitch).
            The logo slot is a HOVER-SWAP (ChatGPT parity, 2026-09-27): at
            rest the brand mark; on hover/focus-within it crossfades into
            the expand button (PanelLeft + tooltip) — the rail's only
            expand entry besides Cmd/Ctrl+B. Opacity swap (not display)
            keeps the button keyboard-focusable and the slot geometry
            constant. */}
        <div className="group/logo relative hidden h-6 w-6 self-center group-data-[state=collapsed]:md:grid">
          <LogoMark className="absolute inset-0 h-6 w-6 transition-opacity group-hover/logo:opacity-0 group-focus-within/logo:opacity-0" />
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={toggleSidebar}
                  aria-label={t("a11y.openSidebar")}
                  className="absolute inset-0 h-6 w-6 rounded-[22%] opacity-0 transition-opacity hover:bg-sidebar-accent group-hover/logo:opacity-100 focus-visible:opacity-100"
                />
              }
            >
              <PanelLeft className="size-4" />
            </TooltipTrigger>
            <TooltipContent side="right">
              <p>{t("a11y.openSidebar")}</p>
            </TooltipContent>
          </Tooltip>
        </div>
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
            logout) — never a DropdownMenu of links. Expanded footer anatomy
            (ChatGPT parity, 2026-09-27): ONE container owns the hover/open
            fill — [avatar + name/plan two lines][upgrade pill] read as a
            single row unit, the pill living INSIDE it (2026-09-27 user
            correction: never two visually separate pieces). The pill rides
            to the landing pricing anchor (the in-app purchase entry is
            W11). */}
        <div
          className={cn(
            // One container owns the row fill — but it YIELDS when the
            // upgrade pill is the hover target (:has guard, 2026-09-27):
            // hovering the pill lights the pill alone, not the whole row.
            "flex w-full items-center rounded-xl transition-colors group-data-[state=collapsed]:justify-center group-data-[state=expanded]:not-has-[[data-slot=button]:hover]:hover:bg-sidebar-accent",
            consoleOpen && "group-data-[state=expanded]:bg-sidebar-accent",
          )}
        >
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
          <Button
            variant="outline"
            size="sm"
            nativeButton={false}
            className="mr-1.5 h-7 shrink-0 rounded-md px-2.5 text-xs hover:bg-accent group-data-[state=collapsed]:hidden"
            render={<Link to="/" hash="pricing" />}
          >
            {t("common.upgrade")}
          </Button>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
