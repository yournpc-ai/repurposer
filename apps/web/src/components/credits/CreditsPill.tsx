"use client"

import { useCallback, useEffect, useState } from "react"
import { ArrowRight, Zap } from "lucide-react"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { apiFetch } from "@/lib/api"
import { useSettingsDialog } from "@/components/settings/settings-dialog-context"
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
 * The popover is the GLANCE seat: a compact wallet summary makes the current
 * balance explicit, Add credits is the one primary action, and the latest
 * three semantic rows answer "什么操作扣了多少". Held / negative notes appear
 * only when they exist. The ledger's full view lives in the SettingsDialog
 * credits section — "View all" deep-links there via openSettings("credits").
 *
 * Data contract mirrors the account console (防双报 discipline): silent
 * fetch failures keep "—", never a toast. Refreshes on mount, on
 * `refreshKey` change (the page passes the latest run's id+status — a run's
 * hold/capture/release settles server-side), and on every popover open. */
export function CreditsPill({ refreshKey }: { refreshKey: string }) {
  const { t, i18n } = useTranslation()
  const { isAuthenticated } = useAuth()
  const { openSettings, openCreditTopup } = useSettingsDialog()
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
        <div className="p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground">
                {t("credits.available")}
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {wallet ? formatCredits(wallet.balance, i18n.language) : "—"}
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              className="flex-none"
              onClick={() => {
                setOpen(false)
                openCreditTopup()
              }}
            >
              {t("credits.buyTitle")}
            </Button>
          </div>
          {wallet != null && (wallet.held > 0 || wallet.balance < 0) && (
            <div className="mt-2 space-y-1">
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
        </div>

        <div className="border-t border-subtle px-4 py-3">
          <p className="text-xs text-muted-foreground">
            {t("credits.recent")}
          </p>
          <div className="mt-1">
            {items === null ? (
              <p className="py-2 text-xs text-muted-foreground">…</p>
            ) : items.length === 0 ? (
              <p className="py-2 text-xs text-muted-foreground">
                {t("credits.tx.empty")}
              </p>
            ) : (
              items.map((item) => (
                <TransactionRow key={item.id} item={item} />
              ))
            )}
          </div>
        </div>

        <div className="border-t border-subtle p-1.5">
          <button
            type="button"
            className="flex h-8 w-full items-center justify-between rounded-md px-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            onClick={() => {
              setOpen(false)
              openSettings("credits")
            }}
          >
            <span>{t("credits.viewAll")}</span>
            <ArrowRight className="size-3.5" />
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
