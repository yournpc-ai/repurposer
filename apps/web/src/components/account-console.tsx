"use client"

import { useEffect, useState } from "react"
import {
  LogOut,
  LogIn,
  Zap,
  RotateCcw,
  Settings,
  Palette,
  Languages,
  ChevronRight,
} from "@/components/ui/icons"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { clearAuth } from "@/lib/auth"
import { AppearanceChoice, LanguageChoice } from "./settings/PreferenceChoices"
import { useAuth } from "@/lib/auth-context"
import { useSettingsDialog } from "@/components/settings/settings-dialog-context"
import { formatCredits } from "@/components/credits/tx-row"
import { Avatar } from "@/components/ui/avatar-clean"

/** The account console (ADR-046 D5) — compact studio menu Popover anchored to
 * the rail-foot avatar. Never a DropdownMenu — it carries inline controls. */

const rowLayout =
  "grid h-8 w-full grid-cols-[14px_minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2 text-left text-[13px] text-foreground"
const actionRow =
  rowLayout +
  " transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
const rowIcon = "size-3.5 text-muted-foreground"
const chevronIcon = "size-3.5 text-muted-foreground/60"
const divider = "my-1 border-t border-subtle"

export function AccountConsole({ onClose }: { onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const currentPath = useRouterState({ select: (s) => s.location.pathname })
  const { isAuthenticated, setLoginOpen, refreshAuth, user } = useAuth()
  const { openSettings } = useSettingsDialog()
  /** The wallet's real balance (ADR-055). Reads on mount only; silent failure
   * keeps the "—" (never a toast — 防双报). */
  const [balance, setBalance] = useState<number | null>(null)
  useEffect(() => {
    if (!isAuthenticated) return
    let cancelled = false
    apiFetch("/api/v1/wallet", { toast: false })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data && typeof data.balance === "number") {
          setBalance(data.balance)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [isAuthenticated])

  const handleLogout = async () => {
    await apiFetch("/api/v1/auth/logout", { method: "POST" }).catch(() => null)
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
        className={actionRow}
      >
        <LogIn className={rowIcon} />
        <span>{t("common.login")}</span>
      </button>
    )
  }

  return (
    <div className="flex flex-col">
      {/* Compact identity header */}
      <div className="flex items-center gap-2.5 px-2 py-1.5">
        <Avatar name={user?.name || user?.email} size={32} />
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-[13px] font-medium text-foreground">
            {user?.name || user?.email}
          </p>
          {user?.name && user.email && (
            <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
              {user.email}
            </p>
          )}
        </div>
      </div>

      <div className={divider} />

      {/* Credits & Preferences */}
      <div className="flex flex-col gap-0.5">
        <button
          type="button"
          onClick={() => {
            onClose()
            openSettings("credits")
          }}
          className={actionRow}
        >
          <Zap className={rowIcon} />
          <span>{t("common.credits")}</span>
          <span className="flex items-center gap-1 text-xs tabular-nums text-muted-foreground">
            {balance !== null ? formatCredits(balance, i18n.language) : "—"}
            <ChevronRight className={chevronIcon} />
          </span>
        </button>
        {balance !== null && balance < 0 && (
          <p className="px-2 pb-1 text-[11px] leading-snug text-muted-foreground">
            {t("credits.negativeNote")}
          </p>
        )}

        <div className={rowLayout}>
          <Palette className={rowIcon} />
          <span>{t("common.theme")}</span>
          <AppearanceChoice compact className="w-[96px]" />
        </div>
        <div className={rowLayout}>
          <Languages className={rowIcon} />
          <span>{t("common.language")}</span>
          <LanguageChoice compact className="w-[96px]" />
        </div>
        <button
          type="button"
          onClick={() => {
            onClose()
            openSettings()
          }}
          className={actionRow}
        >
          <Settings className={rowIcon} />
          <span>{t("common.settings")}</span>
          <ChevronRight className={chevronIcon} />
        </button>
      </div>

      <div className={divider} />

      {/* Help & Session */}
      <div className="flex flex-col gap-0.5">
        <button
          type="button"
          onClick={handleReplayTour}
          className={actionRow}
        >
          <RotateCcw className={rowIcon} />
          <span>{t("common.replayTour")}</span>
        </button>
        <button
          type="button"
          onClick={handleLogout}
          className={actionRow}
        >
          <LogOut className={rowIcon} />
          <span>{t("common.logout")}</span>
        </button>
      </div>
    </div>
  )
}
