"use client"

import { useEffect, useState } from "react"
import { Link, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { FolderKanban, User } from "lucide-react"

import { getUser } from "@/lib/auth"
import { useAuth } from "@/lib/auth-context"
import { AccountConsole } from "@/components/account-console"
import { CreditsPill } from "@/components/credits/CreditsPill"
import { LogoMark } from "@/components/LogoMark"
import { NotificationBell } from "@/components/notifications/NotificationBell"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

export function StudioHeader() {
  const { t } = useTranslation()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const onProjects = pathname.startsWith("/projects")
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
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between px-4 border-b border-border md:h-12 md:justify-end md:border-0">
      <Link
        to="/home"
        aria-label={t("nav.home")}
        className="-ml-2 md:hidden flex items-center gap-2 rounded-lg px-2 py-1 transition-colors active:bg-accent"
      >
        <LogoMark className="h-6 w-6" />
        <span className="font-semibold tracking-tight max-[400px]:hidden">Rookie Cut</span>
      </Link>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          nativeButton={false}
          render={<Link to="/projects" />}
          aria-label={t("nav.myProjects")}
          aria-current={onProjects ? "page" : undefined}
          className={`md:hidden h-10 w-10 rounded-lg active:bg-accent ${
            onProjects ? "text-foreground" : "text-muted-foreground"
          }`}
        >
          <FolderKanban />
        </Button>
        <CreditsPill refreshKey={pathname} />
        <NotificationBell chip={false} />
        <Popover open={consoleOpen} onOpenChange={setConsoleOpen}>
          <PopoverTrigger
            aria-label={displayName}
            className="md:hidden flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg transition-colors outline-none hover:bg-accent active:bg-accent focus-visible:outline-2 focus-visible:outline-ring/30"
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
