import {
  Home,
  Mic2,
  FolderKanban,
  Palette,
  Crown,
  BookOpen,
  HelpCircle,
  ArrowLeftToLine,
  ArrowRightToLine,
  ChevronDown,
  User,
  Settings,
  LogOut,
  LogIn,
} from "lucide-react"
import { Link, useNavigate, useRouterState } from "@tanstack/react-router"
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"

import { clearAuth, getUser } from "@/lib/auth"
import { useAuth } from "@/components/AuthProvider"
import { LogoMark } from "@/components/LogoMark"

const navItems = [
  { key: "home", url: "/home", icon: Home },
  { key: "myProjects", url: "/projects", icon: FolderKanban },
  { key: "brandTemplate", url: "/brand-template", icon: Palette },
  { key: "speakers", url: "/speakers", icon: Mic2 },
]

const accountItems = [
  { key: "subscription", url: "#", icon: Crown, disabled: true },
  { key: "learningCenter", url: "#", icon: BookOpen, disabled: true },
  { key: "helpCenter", url: "#", icon: HelpCircle, disabled: true },
]

function isActive(path: string, itemUrl: string) {
  if (itemUrl === "#") return false
  return path === itemUrl || path.startsWith(`${itemUrl}/`)
}

export function AppSidebar() {
  const router = useRouterState()
  const currentPath = router.location.pathname
  const { t } = useTranslation()
  const { toggleSidebar } = useSidebar()
  const navigate = useNavigate()
  const { isAuthenticated, setLoginOpen, refreshAuth } = useAuth()

  // Re-read on every render; auth-state changes re-render via context.
  const user = getUser()
  const displayName = user?.name || user?.email || t("common.guest")
  const initial = (user?.name || user?.email || "U").charAt(0).toUpperCase()

  const handleLogout = () => {
    clearAuth()
    refreshAuth()
    navigate({ to: "/" })
  }

  return (
    <Sidebar
      collapsible="icon"
      className={
        currentPath.startsWith("/brand-template")
          ? undefined
          : "group-data-[side=left]:border-r-0"
      }
    >
      <SidebarHeader className="gap-3 p-3 group-data-[state=collapsed]:items-center">
        <div className="flex w-full items-center justify-between group-data-[state=collapsed]:justify-center">
          <div className="flex items-center gap-2 group-data-[state=collapsed]:hidden">
            <LogoMark />
            <span className="font-semibold tracking-tight">Repurposer</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="relative h-8 w-8 shrink-0 rounded-md"
            onClick={toggleSidebar}
            aria-label={t("a11y.toggleSidebar")}
          >
            <ArrowLeftToLine className="absolute inset-0 m-auto size-4.5 transition-opacity group-data-[state=collapsed]:opacity-0" />
            <ArrowRightToLine className="absolute inset-0 m-auto size-4.5 opacity-0 transition-opacity group-data-[state=collapsed]:opacity-100" />
          </Button>
        </div>
      </SidebarHeader>

      <SidebarContent className="gap-4 px-2">
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
        <DropdownMenu>
          <DropdownMenuTrigger
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
                  <span className="mt-1 text-xs text-muted-foreground">0 credits</span>
                </div>
                <ChevronDown className="h-4 w-4 text-muted-foreground group-data-[state=collapsed]:hidden" />
              </Button>
            }
          />
          <DropdownMenuContent
            className="w-56 rounded-xl"
            side="top"
            align="start"
            sideOffset={8}
          >
            {isAuthenticated ? (
              <>
                <DropdownMenuGroup>
                  <div className="flex items-center gap-2 px-2 py-1.5">
                    <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium">
                      {t("common.freePlan")}
                    </span>
                  </div>
                </DropdownMenuGroup>
                <DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem>
                    <User className="mr-2 h-4 w-4" />
                    {t("common.profile")}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    render={
                      <Link
                        to="/settings"
                        search={{ connected: undefined, error: undefined }}
                      />
                    }
                  >
                    <Settings className="mr-2 h-4 w-4" />
                    {t("common.settings")}
                  </DropdownMenuItem>
                </DropdownMenuGroup>
                <DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout}>
                    <LogOut className="mr-2 h-4 w-4" />
                    {t("common.logout")}
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </>
            ) : (
              <DropdownMenuGroup>
                <DropdownMenuItem onClick={() => setLoginOpen(true)}>
                  <LogIn className="mr-2 h-4 w-4" />
                  {t("common.login")}
                </DropdownMenuItem>
              </DropdownMenuGroup>
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        <SidebarGroup className="px-0 py-0">
          <SidebarGroupContent>
            <SidebarMenu className="gap-1">
              {accountItems.map((item) => (
                <SidebarMenuItem key={item.key}>
                  <SidebarMenuButton
                    disabled={item.disabled}
                    tooltip={t(`nav.${item.key}`)}
                    className="h-10 text-sm text-sidebar-foreground/70"
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
      </SidebarFooter>
    </Sidebar>
  )
}
