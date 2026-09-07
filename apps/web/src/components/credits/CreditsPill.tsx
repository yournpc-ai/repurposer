"use client"

import { useCallback, useEffect, useState } from "react"
import { Coins } from "lucide-react"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/components/AuthProvider"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { apiFetch } from "@/lib/api"
import { cn } from "@/lib/utils"

interface WalletState {
  balance: number
  held: number
}

interface WalletTransaction {
  id: string
  /** The semantic fold's three families (ADR-057 K4 — the ledger's
   * hold/capture/release machinery never crosses the wire): spend = 花费 /
   * grant = 赠送 / topup = 充值. */
  family: "spend" | "grant" | "topup" | string
  amount: number
  /** The row's display name — a spend names its run; grant/topup name
   * their family (server-composed in the UI language). */
  label: string
  created_at: string
}

/** Same relative-time helper as NotificationBell (reuses the notifications.*
 * keys) — duplicated locally per the codebase's hand-rolled pattern. */
function useRelativeTime() {
  const { t } = useTranslation()
  return (iso: string | null) => {
    if (!iso) return ""
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
    if (seconds < 60) return t("notifications.justNow")
    if (seconds < 3600)
      return t("notifications.minutesAgo", { count: Math.floor(seconds / 60) })
    if (seconds < 86400)
      return t("notifications.hoursAgo", { count: Math.floor(seconds / 3600) })
    return t("notifications.daysAgo", { count: Math.floor(seconds / 86400) })
  }
}

/** The project page's bottom-left credits pill (BILLING §7 read surface,
 * 2026-09-06 — the FLORA "92% Left" slot, adapted: absolute credits, no plan
 * quota or purchase entry yet). The page is the one surface where credits
 * are spent AND no studio shell carries the account console. Desktop only —
 * the mobile bottom dock owns the small-screen's bottom edge.
 *
 * Data contract mirrors the account console (防双报 discipline): silent
 * fetch failures keep "—", never a toast. Refreshes on mount, on
 * `refreshKey` change (the page passes the latest run's id+status — a run's
 * hold/capture/release settles server-side), and on every popover open. */
export function CreditsPill({ refreshKey }: { refreshKey: string }) {
  const { t } = useTranslation()
  const { isAuthenticated } = useAuth()
  const relativeTime = useRelativeTime()
  const [wallet, setWallet] = useState<WalletState | null>(null)
  const [items, setItems] = useState<WalletTransaction[] | null>(null)
  const [open, setOpen] = useState(false)

  const fetchWallet = useCallback(async () => {
    try {
      const res = await apiFetch("/api/v1/wallet", { toast: false })
      if (!res.ok) return
      setWallet((await res.json()) as WalletState)
    } catch {
      /* silent — the pill keeps its last value (or "—") */
    }
  }, [])

  useEffect(() => {
    if (isAuthenticated) void fetchWallet()
  }, [isAuthenticated, fetchWallet, refreshKey])

  // Every open refetches BOTH endpoints — the ledger is the truth, never a
  // cached snapshot.
  useEffect(() => {
    if (!open || !isAuthenticated) return
    void fetchWallet()
    let cancelled = false
    void (async () => {
      try {
        const res = await apiFetch("/api/v1/wallet/transactions?limit=10", {
          toast: false,
        })
        if (!res.ok) return
        const data = (await res.json()) as { items: WalletTransaction[] }
        if (!cancelled) setItems(data.items)
      } catch {
        /* silent — the list keeps its last value */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, isAuthenticated, fetchWallet])

  if (!isAuthenticated) return null

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <button
            type="button"
            aria-label={t("common.credits")}
            className="dock-surface fixed bottom-4 left-4 z-40 hidden h-9 items-center gap-1.5 rounded-md px-3 text-sm ring-1 ring-foreground/10 transition-colors hover:bg-accent md:flex"
          >
            <Coins className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="tabular-nums">{wallet?.balance ?? "—"}</span>
          </button>
        }
      />
      <PopoverContent
        side="top"
        align="start"
        sideOffset={8}
        className="w-80 gap-0 p-0"
      >
        {/* Balance block — the account console's value-row anatomy (icon +
            label + ml-auto tabular value), one quiet register. */}
        <div className="flex flex-col gap-0.5 p-2">
          <div className="flex h-8 items-center gap-2 px-2">
            <Coins className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs text-foreground">
              {t("credits.balance")}
            </span>
            <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">
              {wallet?.balance ?? "—"}
            </span>
          </div>
          {wallet != null && wallet.held > 0 && (
            <div className="flex h-8 items-center gap-2 px-2">
              <span className="h-3.5 w-3.5" aria-hidden />
              <span className="text-xs text-foreground">
                {t("credits.held")}
              </span>
              <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">
                {wallet.held}
              </span>
            </div>
          )}
          {wallet != null && wallet.balance < 0 && (
            <p className="px-2 pb-1.5 text-[11px] leading-snug text-muted-foreground">
              {t("credits.negativeNote")}
            </p>
          )}
        </div>
        {/* Recent semantic rows (ADR-057 K4 语义账本塌缩): one row per run
            event / grant / top-up — the ledger's hold/capture/release
            machinery folds server-side and never renders here. Signed
            amounts stay neutral (no green/red semantics). */}
        <div className="flex flex-col p-2 pt-0">
          <p className="px-2 pb-1 text-[11px] text-meta">
            {t("credits.recent")}
          </p>
          {items === null ? (
            <p className="px-2 py-1.5 text-xs text-muted-foreground">…</p>
          ) : items.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-muted-foreground">
              {t("credits.tx.empty")}
            </p>
          ) : (
            items.map((item) => (
              <div key={item.id} className="flex items-center gap-2 px-2 py-1.5">
                <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                  {item.label}
                </span>
                <span
                  className={cn(
                    "shrink-0 text-xs tabular-nums",
                    item.amount >= 0
                      ? "text-foreground"
                      : "text-muted-foreground"
                  )}
                >
                  {item.amount >= 0 ? `+${item.amount}` : item.amount}
                </span>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {relativeTime(item.created_at)}
                </span>
              </div>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
