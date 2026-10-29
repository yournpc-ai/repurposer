"use client"

import { useCallback, useEffect, useState } from "react"
import { Zap } from "lucide-react"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/lib/auth-context"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { apiFetch } from "@/lib/api"
import { useSettingsDialog } from "@/components/settings/SettingsDialog"
import {
  formatCredits,
  TransactionRow,
  type WalletTransaction,
} from "@/components/credits/tx-row"

interface WalletState {
  balance: number
  held: number
}

/** The ProjectHeader's credits read + purchase-entry surface (BILLING §7 —
 * absolute credits, no plan quota). Seat (2026-10-15 user ruling):
 * inside the glass ProjectHeader, right end, all breakpoints and all world
 * states — credits must be visible at the spend point, pre-run included.
 * Bare anatomy (the MobileHeader bell's law): controls inside glass carry
 * no tile of their own.
 *
 * The popover is the GLANCE seat: the trigger already carries the balance,
 * so the panel answers "什么操作扣了多少" — the latest three rows for
 * spend-point confirmation, with held / negative notes as a conditional
 * strip. The ledger's full view lives in the SettingsDialog credits
 * section — the "View all" row deep-links there via the shared
 * openSettings("credits").
 *
 * Data contract mirrors the account console (防双报 discipline): silent
 * fetch failures keep "—", never a toast. Refreshes on mount, on
 * `refreshKey` change (the page passes the latest run's id+status — a run's
 * hold/capture/release settles server-side), and on every popover open. */
export function CreditsPill({ refreshKey }: { refreshKey: string }) {
  const { t, i18n } = useTranslation()
  const { isAuthenticated } = useAuth()
  const { openSettings } = useSettingsDialog()
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
  // cached snapshot. Three rows: the popover is a preview, the full ledger
  // is the settings section's seat.
  useEffect(() => {
    if (!open || !isAuthenticated) return
    void fetchWallet()
    let cancelled = false
    void (async () => {
      try {
        const res = await apiFetch("/api/v1/wallet/transactions?limit=3", {
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
            className="group flex h-9 items-center gap-1.5 rounded-md px-2 text-[13px] transition-colors hover:bg-accent active:bg-accent"
          >
            <Zap className="h-3.5 w-3.5 text-muted-foreground" />
            {/* Quiet by default — the spend-point read is a glance, not a
                banner; foreground only on hover. */}
            <span className="tabular-nums text-muted-foreground transition-colors group-hover:text-foreground">
              {wallet ? formatCredits(wallet.balance, i18n.language) : "—"}
            </span>
          </button>
        }
      />
      <PopoverContent
        side="bottom"
        align="end"
        sideOffset={8}
        className="w-80 gap-0 p-0"
      >
        {/* The trigger already carries the balance — the popover is the
            "what happened" surface, so no hero repeat. Held / negative
            notes surface as a quiet strip only when they exist. */}
        <div className="flex flex-col p-2">
          {wallet != null && (wallet.held > 0 || wallet.balance < 0) && (
            <div className="flex flex-col gap-0.5 px-2 pb-1.5 pt-1">
              {wallet.held > 0 && (
                <p className="text-[11px] text-muted-foreground">
                  {t("credits.heldInline", {
                    count: formatCredits(wallet.held, i18n.language),
                  })}
                </p>
              )}
              {wallet.balance < 0 && (
                <p className="text-[11px] leading-snug text-muted-foreground">
                  {t("credits.negativeNote")}
                </p>
              )}
            </div>
          )}
          {/* Recent rows (ADR-057 K4 语义账本塌缩): one row per run event /
              grant / top-up — the ledger's hold/capture/release machinery
              folds server-side and never renders here. */}
          <p className="px-2 pb-1 pt-1 text-[11px] text-meta">
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
              <TransactionRow key={item.id} item={item} className="px-2" />
            ))
          )}
          {/* Purchase selection stays in the management seat; this is only an
              entry, never a second package panel. */}
          <button
            type="button"
            className="mt-0.5 flex h-8 w-full items-center rounded-md px-2 text-xs text-foreground transition-colors hover:bg-accent"
            onClick={() => {
              setOpen(false)
              openSettings("credits")
            }}
          >
            {t("credits.buyTitle")}
          </button>
          {/* Full-ledger deep link — the management seat is the
              SettingsDialog credits section. */}
          <button
            type="button"
            className="mt-0.5 flex h-8 w-full items-center rounded-md px-2 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            onClick={() => {
              setOpen(false)
              openSettings("credits")
            }}
          >
            {t("credits.viewAll")}
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
