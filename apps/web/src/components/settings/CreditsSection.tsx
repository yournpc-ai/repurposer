"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { apiFetch } from "@/lib/api"
import { fetchPaymentOrder } from "@/lib/payments"
import { useSettingsDialog } from "@/components/settings/settings-dialog-context"
import {
  formatCredits,
  TransactionRow,
  type WalletTransaction,
} from "@/components/credits/tx-row"

/** Credits management seat: real balance, a top-up dialog entry, hosted-
 * Checkout return confirmation, and the semantic ledger. A browser return
 * never announces a top-up; only a server-side paid order can do that. */

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
  const { checkoutReturn, clearCheckoutReturn, openCreditTopup } = useSettingsDialog()
  const [wallet, setWallet] = useState<WalletState | null>(null)
  const [items, setItems] = useState<WalletTransaction[] | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [returnNotice, setReturnNotice] = useState<ReturnNotice>(null)
  const [pollNonce, setPollNonce] = useState(0)
  const activityRef = useRef<HTMLElement>(null)

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

  const visible = expanded ? items : items?.slice(0, COLLAPSED_COUNT)

  return (
    <div className="space-y-6">
      {returnNotice && (
        <div
          className="flex items-center gap-2 rounded-md bg-muted px-3 py-2"
          role="status"
        >
          <p className="min-w-0 flex-1 text-xs leading-relaxed text-muted-foreground">
            {t(`credits.return.${returnNotice}`)}
          </p>
          {returnNotice === "pending" && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setReturnNotice("confirming")
                setPollNonce((value) => value + 1)
              }}
            >
              {t("credits.checkAgain")}
            </Button>
          )}
        </div>
      )}

      <section>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-muted-foreground">{t("credits.available")}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {wallet ? formatCredits(wallet.balance, i18n.language) : "—"}
            </p>
            {wallet != null && wallet.held > 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                {t("credits.held")} · {formatCredits(wallet.held, i18n.language)}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => activityRef.current?.scrollIntoView({ block: "start" })}
            >
              {t("credits.recent")}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => openCreditTopup()}
            >
              {t("credits.buyTitle")}
            </Button>
          </div>
        </div>
        {wallet != null && wallet.balance < 0 && (
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            {t("credits.negativeNote")}
          </p>
        )}
      </section>

      <section ref={activityRef} className="border-t border-subtle pt-6">
        <div className="flex items-center gap-3">
          <h4 className="min-w-0 flex-1 text-sm font-semibold">
            {t("credits.recent")}
          </h4>
          {items != null && items.length > COLLAPSED_COUNT && !expanded && (
            <button
              type="button"
              className="rounded-md text-xs text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setExpanded(true)}
            >
              {t("credits.viewAll")}
            </button>
          )}
        </div>
        <div className="mt-2">
          {items === null ? (
            <p className="py-3 text-xs text-muted-foreground">…</p>
          ) : items.length === 0 ? (
            <p className="py-3 text-xs text-muted-foreground">
              {t("credits.tx.empty")}
            </p>
          ) : (
            <div>
              {(visible ?? []).map((item) => (
                <TransactionRow
                  key={item.id}
                  item={item}
                  className="border-b border-subtle py-3 last:border-0"
                />
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
