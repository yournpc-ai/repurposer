"use client"

import { useEffect, useState } from "react"
import { Link, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { FolderKanban, User } from "lucide-react"

import { getUser } from "@/lib/auth"
import { useAuth } from "@/lib/auth-context"
import { AccountConsole } from "@/components/account-console"
import { LogoMark } from "@/components/LogoMark"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

/**
 * Mobile chrome (<md, 2026-10-14 user ruling): the desktop law "no global
 * AppHeader — the bell is the single floating chip" scopes to md+. Below md
 * the sidebar rail AND its drawer go away entirely — a two-entry nav
 * (Home / Projects) doesn't deserve a bottom tab bar, so this header absorbs
 * everything: brand lockup left (tap = /home), Projects + bell + avatar
 * (the same AccountConsole popover as the rail footer) right. The floating
 * sidebar trigger and floating bell chip are retired below md with it.
 *
 * Material = dock-surface glass (user ruling — Pexo parity): the pinned
 * chrome is the same species as the results dock's parked glass — persistent,
 * content scrolls UNDER it — so it takes the no-shadow high-translucency
 * recipe, NOT overlay-surface (75% fill + floating-layer shadow reads as a
 * solid white bar over the white page). Stacked anatomy, never overlay: the
 * header is the first IN-FLOW child of SidebarInset (sticky top-0 pins it on
 * window-scroll pages, whose content scrolls under the glass naturally).
 * Home is the ONE deliberate exception — its scrollport pulls up UNDER the
 * glass (-mt-14, root stays 100svh) so the hero/cards frost through it as
 * they scroll, and its pinned tabs bar compensates with max-md:top-14. No
 * shadow — separation comes from the hairline + content blurring through
 * the frost.
 *
 * Press feedback (touch law): `hover:` never fires on a phone — every
 * header control also carries `active:bg-accent` so a finger press reads.
 */
export function MobileHeader() {
  const { t } = useTranslation()
  const router = useRouterState()
  const onProjects = router.location.pathname.startsWith("/projects")
  const { isAuthenticated } = useAuth()

  // Same SSR discipline as the rail footer: getUser() reads localStorage,
  // which the server cannot see — gate on mounted so SSR and the first
  // client render agree (guest fallback).
  const [mounted, setMounted] = useState(false)
  const [consoleOpen, setConsoleOpen] = useState(false)
  useEffect(() => setMounted(true), [])
  const user = mounted ? getUser() : null
  const displayName = user?.name || user?.email || t("common.guest")
  const initial = (user?.name || user?.email || "U").charAt(0).toUpperCase()

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between px-4 dock-surface ring-1 ring-foreground/10 md:hidden">
      {/* Brand lockup = the Home entry (mobile convention: brand tap goes
          home; the rail's SidebarHeader lockup mirrored in miniature). */}
      <Link
        to="/home"
        aria-label={t("nav.home")}
        className="-ml-2 flex items-center gap-2 rounded-lg px-2 py-1 transition-colors active:bg-accent"
      >
        <LogoMark className="h-6 w-6" />
        <span className="font-semibold tracking-tight">Repurposer</span>
      </Link>

      <div className="flex items-center gap-1">
        {/* Projects — the second nav entry, bare icon button inside the
            glass (no chip tile of its own); active reads foreground. */}
        <Button
          variant="ghost"
          size="icon"
          nativeButton={false}
          render={<Link to="/projects" />}
          aria-label={t("nav.myProjects")}
          aria-current={onProjects ? "page" : undefined}
          className={`h-10 w-10 rounded-lg active:bg-accent ${
            onProjects ? "text-foreground" : "text-muted-foreground"
          }`}
        >
          <FolderKanban />
        </Button>

        {/* Bell in its bare form — the glass tile is the header's. */}
        <NotificationBell chip={false} />

        {/* Avatar → the SAME AccountConsole as the rail footer (theme /
            language / replay tour / logout) — without this seat the mobile
            shell would lose the account surface entirely. */}
        <Popover open={consoleOpen} onOpenChange={setConsoleOpen}>
          <PopoverTrigger
            aria-label={displayName}
            className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg transition-colors outline-none hover:bg-accent active:bg-accent focus-visible:ring-2 focus-visible:ring-ring/30"
          >
            <Avatar className="h-7 w-7 rounded-full">
              <AvatarImage src="" alt={displayName} />
              <AvatarFallback className="rounded-full bg-primary text-[10px] text-primary-foreground">
                {isAuthenticated ? initial : <User className="h-3 w-3" />}
              </AvatarFallback>
            </Avatar>
          </PopoverTrigger>
          <PopoverContent
            className="w-64 rounded-xl p-2"
            side="bottom"
            align="end"
            // Trigger 底距 header 下沿 8px —— sideOffset 16 才在玻璃下留出
            // 8px 可见空气，8 会让面板齐平贴上 header。
            sideOffset={16}
          >
            <AccountConsole onClose={() => setConsoleOpen(false)} />
          </PopoverContent>
        </Popover>
      </div>
    </header>
  )
}
