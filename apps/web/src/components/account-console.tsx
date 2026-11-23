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
} from "lucide-react"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import { clearAuth } from "@/lib/auth"
import { AppearanceChoice, LanguageChoice } from "./settings/PreferenceChoices"
import { useAuth } from "@/lib/auth-context"
import { useSettingsDialog } from "@/components/settings/settings-dialog-context"
import { formatCredits } from "@/components/credits/tx-row"
import { Avatar } from "@/components/ui/avatar-clean"

/** The account console (ADR-046 D5) — the Popover the rail-foot avatar opens.
 * Grouping: the inset ACCOUNT block carries the actionable Credits value;
 * system surfaces live in 偏好 as labeled rows — theme / language with
 * TRAILING segmented controls, deep settings as a chevron row opening the
 * shared SettingsDialog. Never a DropdownMenu — it carries inline controls,
 * not a list of links. */

const rowLayout = "grid min-h-9 w-full grid-cols-[1rem_minmax(0,1fr)_auto] items-center gap-2.5 px-2 text-left text-xs text-foreground"
const actionRow = rowLayout + " rounded-md transition-colors hover:bg-accent"
const rowIcon = "size-4 text-muted-foreground"
const sectionLabel = "px-2 pb-1 pt-3 text-meta text-[10px] font-medium"

export function AccountConsole({ onClose }: { onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const currentPath = useRouterState({ select: (s) => s.location.pathname })
  const { isAuthenticated, setLoginOpen, refreshAuth, user } = useAuth()
  const { openSettings } = useSettingsDialog()
  /** The wallet's real balance (ADR-055 — the credits slot's value). Reads
   * on mount only; a run's hold/capture settles server-side and shows on
   * the next open. Silent failure keeps the "—" (page-level load failure,
   * never a toast — 防双报). */
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
        {t("common.login")}
      </button>
    )
  }

  return (
    <div className="flex flex-col">
      {/* Identity header */}
      <div className="flex items-center gap-2.5 px-2 pb-3">
        <Avatar name={user?.name || user?.email} size={40} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-foreground">{user?.name || user?.email}</p>
          {user?.name && user.email && (
            <p className="truncate text-[11px] text-muted-foreground">{user.email}</p>
          )}
        </div>
      </div>

      {/* Inset ACCOUNT block — Credits is the only value surface while
          subscriptions are unavailable. The whole row opens its real
          management seat instead of presenting a static, button-like row. */}
      <div className="rounded-lg bg-inset">
        <button
          type="button"
          onClick={() => {
            onClose()
            openSettings("credits")
          }}
          className={actionRow}
        >
          <Zap className={rowIcon} />
          <span className="text-xs text-foreground">{t("common.credits")}</span>
          <span className="flex items-center gap-1.5 tabular-nums text-muted-foreground">
            {balance !== null ? formatCredits(balance, i18n.language) : "—"}
            <ChevronRight className={rowIcon} />
          </span>
        </button>
        {/* Negative balance (BILLING §5): a NULL-estimate run may settle the
            balance past zero — the number shows honestly and this note
            explains it. */}
        {balance !== null && balance < 0 && (
          <p className="px-2 pb-1.5 text-[11px] leading-snug text-muted-foreground">
            {t("credits.negativeNote")}
          </p>
        )}
      </div>

      {/* 偏好: labeled rows with trailing controls (MiniMax row anatomy) —
          theme / language as trailing segmented, deep settings as a chevron
          row. */}
      <p className={sectionLabel}>{t("common.preferences")}</p>
      <div className="flex flex-col gap-0.5">
        <div className={rowLayout}>
          <Palette className={rowIcon} />
          <span className="text-xs text-foreground">{t("common.theme")}</span>
          <AppearanceChoice compact />
        </div>
        <div className={rowLayout}>
          <Languages className={rowIcon} />
          <span className="text-xs text-foreground">{t("common.language")}</span>
          <LanguageChoice />
        </div>
        {/* Settings — deep row, opens the shared SettingsDialog. */}
        <button
          type="button"
          onClick={() => {
            onClose()
            openSettings()
          }}
          className={actionRow}
        >
          <Settings className={rowIcon} />
          {t("common.settings")}
          <ChevronRight className={rowIcon} />
        </button>
      </div>

      {/* 帮助 */}
      <p className={sectionLabel}>{t("common.helpSection")}</p>
      <button
        type="button"
        onClick={handleReplayTour}
        className={actionRow}
      >
        <RotateCcw className={rowIcon} />
        {t("common.replayTour")}
      </button>

      <hr className="my-1.5 border-border" />
      <button
        type="button"
        onClick={handleLogout}
        className={actionRow}
      >
        <LogOut className={rowIcon} />
        {t("common.logout")}
      </button>
    </div>
  )
}
