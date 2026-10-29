"use client"

import { useCallback, useEffect, useState } from "react"
import { Zap } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { apiFetch } from "@/lib/api"
import {
  createCheckoutSession,
  fetchCreditPackages,
  fetchPaymentOrder,
  formatMoney,
  type CreditPackage,
} from "@/lib/payments"
import { useSettingsDialog } from "@/components/settings/SettingsDialog"
import {
  formatCredits,
  TransactionRow,
  type WalletTransaction,
} from "@/components/credits/tx-row"

/** Credits management seat: real balance, hosted-Checkout packages, and the
 * shared semantic ledger. A browser return never announces a top-up; only the
 * server-side paid order can do that (PAYMENTS §7). */

interface WalletState {
  balance: number
  held: number
}

const COLLAPSED_COUNT = 3
const FETCH_LIMIT = 50
const MAX_ORDER_POLLS = 15

type ReturnNotice = "confirming" | "pending" | null

export function CreditsSection() {
  const { t, i18n } = useTranslation()
  const { checkoutReturn, clearCheckoutReturn } = useSettingsDialog()
  const [wallet, setWallet] = useState<WalletState | null>(null)
  const [items, setItems] = useState<WalletTransaction[] | null>(null)
  const [packages, setPackages] = useState<CreditPackage[] | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [purchasingKey, setPurchasingKey] = useState<string | null>(null)
  const [returnNotice, setReturnNotice] = useState<ReturnNotice>(null)
  const [pollNonce, setPollNonce] = useState(0)

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch("/api/v1/wallet", { toast: false })
      if (res.ok) setWallet((await res.json()) as WalletState)
    } catch {
      /* silent — the overview keeps its last value */
    }
    try {
      const res = await apiFetch(
        `/api/v1/wallet/transactions?limit=${FETCH_LIMIT}`,
        { toast: false },
      )
      if (res.ok) {
        setItems(((await res.json()) as { items: WalletTransaction[] }).items)
      }
    } catch {
      /* silent — the list keeps its last value */
    }
  }, [])

  useEffect(() => {
    void refresh()
    let cancelled = false
    void fetchCreditPackages()
      .then((value) => {
        if (!cancelled) setPackages(value)
      })
      .catch(() => {
        if (!cancelled) setPackages([])
      })
    return () => {
      cancelled = true
    }
  }, [refresh])

  useEffect(() => {
    if (!checkoutReturn) {
      setReturnNotice(null)
      return
    }
    if (checkoutReturn.outcome === "cancelled") {
      toast.info(t("credits.return.cancelled"))
      clearCheckoutReturn()
      return
    }

    let stopped = false
    let timer: number | undefined
    let polls = 0
    setReturnNotice("confirming")

    const check = async () => {
      const order = await fetchPaymentOrder(checkoutReturn.orderId).catch(() => null)
      if (stopped) return
      polls += 1
      if (order?.status === "paid") {
        setReturnNotice(null)
        clearCheckoutReturn()
        toast.success(
          t("credits.topupSuccess", {
            count: formatCredits(order.credits, i18n.language),
          }),
        )
        await refresh()
        return
      }
      if (order?.status === "expired" || order?.status === "failed") {
        toast.error(t("credits.return.failed"))
        clearCheckoutReturn()
        return
      }
      if (polls >= MAX_ORDER_POLLS) {
        setReturnNotice("pending")
        return
      }
      timer = window.setTimeout(check, 2000)
    }

    void check()
    return () => {
      stopped = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [checkoutReturn, clearCheckoutReturn, i18n.language, pollNonce, refresh, t])

  const buy = async (packageKey: string) => {
    setPurchasingKey(packageKey)
    try {
      const result = await createCheckoutSession(packageKey)
      if (result) {
        window.location.assign(result.checkout_url)
        return
      }
    } catch {
      // apiFetch already reported the network/server failure through the toast.
    }
    setPurchasingKey(null)
  }

  const visible = expanded ? items : items?.slice(0, COLLAPSED_COUNT)

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t("credits.subtitle")}</p>

      <Card className="gap-0 px-4 py-2">
        <p className="pb-1 pt-2 text-[11px] text-meta">{t("credits.overview")}</p>
        <div className="flex h-9 items-center gap-2">
          <Zap className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs text-foreground">{t("credits.balance")}</span>
          <span className="ml-auto text-base font-semibold tabular-nums">
            {wallet ? formatCredits(wallet.balance, i18n.language) : "—"}
          </span>
        </div>
        {wallet != null && wallet.held > 0 && (
          <div className="flex h-9 items-center gap-2">
            <span className="h-3.5 w-3.5" aria-hidden />
            <span className="text-xs text-foreground">{t("credits.held")}</span>
            <span className="ml-auto text-sm tabular-nums text-muted-foreground">
              {formatCredits(wallet.held, i18n.language)}
            </span>
          </div>
        )}
        {wallet != null && wallet.balance < 0 && (
          <p className="pb-1.5 text-[11px] leading-snug text-muted-foreground">
            {t("credits.negativeNote")}
          </p>
        )}
      </Card>

      <Card className="gap-0 px-4 py-2">
        <p className="pb-1 pt-2 text-[11px] text-meta">{t("credits.buyTitle")}</p>
        {packages === null ? (
          <p className="py-1.5 text-xs text-muted-foreground">…</p>
        ) : packages.length === 0 ? (
          <p className="py-1.5 text-xs text-muted-foreground">
            {t("credits.packagesUnavailable")}
          </p>
        ) : (
          packages.map((item) => (
            <div key={item.key} className="flex min-h-9 items-center gap-2 py-1">
              <span className="text-xs text-foreground">
                {t("credits.packageCredits", {
                  count: formatCredits(item.credits, i18n.language),
                })}
              </span>
              <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                {formatMoney(item.amount_minor, item.currency, i18n.language)}
              </span>
              <Button
                type="button"
                size="sm"
                className="h-9"
                disabled={purchasingKey !== null}
                onClick={() => void buy(item.key)}
              >
                {purchasingKey === item.key
                  ? t("credits.buying")
                  : t("credits.buy")}
              </Button>
            </div>
          ))
        )}
        {returnNotice && (
          <div className="flex items-center gap-2 pb-1.5 pt-1">
            <p className="text-[11px] leading-snug text-muted-foreground">
              {t(`credits.return.${returnNotice}`)}
            </p>
            {returnNotice === "pending" && (
              <button
                type="button"
                className="ml-auto shrink-0 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                onClick={() => {
                  setReturnNotice("confirming")
                  setPollNonce((value) => value + 1)
                }}
              >
                {t("credits.checkAgain")}
              </button>
            )}
          </div>
        )}
      </Card>

      <Card className="gap-0 px-4 py-2">
        <p className="pb-1 pt-2 text-[11px] text-meta">{t("credits.recent")}</p>
        {items === null ? (
          <p className="py-1.5 text-xs text-muted-foreground">…</p>
        ) : items.length === 0 ? (
          <p className="py-1.5 text-xs text-muted-foreground">{t("credits.tx.empty")}</p>
        ) : (
          <>
            {(visible ?? []).map((item) => (
              <TransactionRow key={item.id} item={item} />
            ))}
            <div className="flex items-center justify-between pt-1.5">
              <span className="text-[11px] text-meta">
                {t("credits.showingRecent", {
                  count: expanded ? items.length : COLLAPSED_COUNT,
                })}
              </span>
              {items.length > COLLAPSED_COUNT && !expanded && (
                <button
                  type="button"
                  className="rounded-md text-xs text-muted-foreground transition-colors hover:text-foreground"
                  onClick={() => setExpanded(true)}
                >
                  {t("credits.viewAll")}
                </button>
              )}
            </div>
          </>
        )}
      </Card>
    </div>
  )
}
