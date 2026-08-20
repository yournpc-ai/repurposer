"use client"

import {
  Monitor,
  Moon,
  Sun,
  LogOut,
  LogIn,
  Crown,
  Sparkles,
  RotateCcw,
  Settings,
  Palette,
  Languages,
  ChevronRight,
} from "lucide-react"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"
import { setLocale, type Locale } from "@/lib/i18n"
import { useTheme, type Theme } from "@/lib/theme/ThemeProvider"
import { clearAuth, getUser } from "@/lib/auth"
import { useAuth } from "@/components/AuthProvider"
import { useSettingsDialog } from "@/components/settings/SettingsDialog"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

/** The account console (ADR-046 D5) — the Popover the rail-foot avatar opens.
 * Grouping (MiniMax discipline, 2026-08-21): the inset ACCOUNT block carries
 * only value surfaces (plan / credits); system surfaces live in 偏好 as
 * labeled rows — theme / language with TRAILING segmented controls, deep
 * settings as a chevron row opening the shared SettingsDialog. Never a
 * DropdownMenu — it carries inline controls, not a list of links. */

const THEME_OPTIONS: { value: Theme; icon: typeof Monitor; labelKey: string }[] = [
  { value: "system", icon: Monitor, labelKey: "common.themeSystem" },
  { value: "light", icon: Sun, labelKey: "common.themeLight" },
  { value: "dark", icon: Moon, labelKey: "common.themeDark" },
]

const LOCALE_OPTIONS: { value: Locale; labelKey: string }[] = [
  { value: "en", labelKey: "languages.en" },
  { value: "zh", labelKey: "languages.zh" },
]

export function AccountConsole({ onClose }: { onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const currentPath = useRouterState({ select: (s) => s.location.pathname })
  const { isAuthenticated, setLoginOpen, refreshAuth } = useAuth()
  const { openSettings } = useSettingsDialog()
  const { theme, setTheme } = useTheme()
  const user = getUser()
  const currentLocale: Locale = i18n.language === "en" ? "en" : "zh"

  const handleLogout = () => {
    clearAuth()
    refreshAuth()
    onClose()
    navigate({ to: "/" })
  }

  // Replay tour: plant the flag for a (re)mounted composer AND ping an
  // already-mounted one — HomeComposer consumes whichever path lands first.
  const handleReplayTour = () => {
    try {
      window.sessionStorage.setItem("repurposer-replay-tour", "1")
    } catch {
      // storage unavailable — the event path may still land
    }
    window.dispatchEvent(new Event("repurposer:replay-tour"))
    onClose()
    if (currentPath !== "/home") navigate({ to: "/home" })
  }

  if (!isAuthenticated) {
    return (
      <button
        type="button"
        onClick={() => {
          onClose()
          setLoginOpen(true)
        }}
        className="flex h-9 items-center gap-2 rounded-md px-2 text-xs text-foreground transition-colors hover:bg-accent"
      >
        <LogIn className="h-3.5 w-3.5 text-muted-foreground" />
        {t("common.login")}
      </button>
    )
  }

  return (
    <div className="flex flex-col">
      {/* Identity header */}
      <div className="flex items-center gap-2.5 px-1 pb-2.5">
        <Avatar className="h-9 w-9">
          <AvatarImage src="" alt={user?.name || user?.email || ""} />
          <AvatarFallback className="bg-primary text-[11px] text-primary-foreground">
            {(user?.name || user?.email || "U").charAt(0).toUpperCase()}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-foreground">
            {user?.name || user?.email}
          </p>
          {user?.name && user.email && (
            <p className="truncate text-[11px] text-muted-foreground">{user.email}</p>
          )}
        </div>
      </div>

      {/* Inset ACCOUNT block — value surfaces ONLY (plan / credits slots).
          Settings is NOT here: it belongs to 偏好 (MiniMax grouping law). */}
      <div className="flex flex-col gap-0.5 rounded-lg bg-inset p-1">
        <div className="flex h-8 items-center gap-2 px-2">
          <Crown className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs text-foreground">{t("nav.subscription")}</span>
          <span className="ml-auto rounded-md bg-card px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
            {t("common.freePlan")}
          </span>
        </div>
        <div className="flex h-8 items-center gap-2 px-2">
          <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs text-foreground">{t("common.credits")}</span>
          <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">—</span>
        </div>
      </div>

      {/* 偏好: labeled rows with trailing controls (MiniMax row anatomy) —
          theme / language as trailing segmented, deep settings as a chevron
          row. */}
      <p className="px-1 pb-1 pt-2.5 text-meta text-[10px] font-medium">
        {t("common.preferences")}
      </p>
      <div className="flex flex-col gap-0.5 px-1">
        <div className="flex h-9 items-center gap-2 px-2">
          <Palette className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs text-foreground">{t("common.theme")}</span>
          <div className="ml-auto flex items-center gap-0.5 rounded-md bg-inset p-0.5">
            {THEME_OPTIONS.map(({ value, icon: Icon, labelKey }) => (
              <button
                key={value}
                type="button"
                title={t(labelKey)}
                aria-label={t(labelKey)}
                onClick={() => setTheme(value)}
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-[5px] transition-colors",
                  theme === value
                    ? "bg-card text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="h-3.5 w-3.5" />
              </button>
            ))}
          </div>
        </div>
        <div className="flex h-9 items-center gap-2 px-2">
          <Languages className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs text-foreground">{t("common.language")}</span>
          <div className="ml-auto flex items-center gap-0.5 rounded-md bg-inset p-0.5">
            {LOCALE_OPTIONS.map(({ value, labelKey }) => (
              <button
                key={value}
                type="button"
                onClick={() => setLocale(value, i18n)}
                className={cn(
                  "flex h-6 items-center justify-center rounded-[5px] px-1.5 text-[11px] transition-colors",
                  currentLocale === value
                    ? "bg-card text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t(labelKey)}
              </button>
            ))}
          </div>
        </div>
        {/* Settings — deep row, opens the shared SettingsDialog. */}
        <button
          type="button"
          onClick={() => {
            onClose()
            openSettings("channels")
          }}
          className="flex h-9 items-center gap-2 rounded-md px-2 text-xs text-foreground transition-colors hover:bg-accent"
        >
          <Settings className="h-3.5 w-3.5 text-muted-foreground" />
          {t("common.settings")}
          <ChevronRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>

      {/* 帮助 */}
      <p className="px-1 pb-1 pt-2.5 text-meta text-[10px] font-medium">
        {t("common.helpSection")}
      </p>
      <button
        type="button"
        onClick={handleReplayTour}
        className="flex h-8 items-center gap-2 rounded-md px-2 text-xs text-foreground transition-colors hover:bg-accent"
      >
        <RotateCcw className="h-3.5 w-3.5 text-muted-foreground" />
        {t("common.replayTour")}
      </button>

      {/* Logout */}
      <button
        type="button"
        onClick={handleLogout}
        className="mt-1.5 flex h-8 items-center gap-2 rounded-md px-2 text-xs text-foreground transition-colors hover:bg-accent"
      >
        <LogOut className="h-3.5 w-3.5 text-muted-foreground" />
        {t("common.logout")}
      </button>
    </div>
  )
}
