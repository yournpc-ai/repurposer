"use client"

import { useEffect, useState } from "react"
import { Zap } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Card } from "@/components/ui/card"
import { apiFetch } from "@/lib/api"
import {
  formatCredits,
  TransactionRow,
  type WalletTransaction,
} from "@/components/credits/tx-row"

/** Credits section of the shared SettingsDialog (BILLING §7 — the balance
 * + ledger full-view seat): overview card (balance / held when active /
 * free-trial placeholder with zero CTA until W11) + recent-activity card.
 * Data rides the SAME two endpoints as the CreditsPill and the account
 * console (三面同源 — zero new endpoints); the semantic fold (spend / grant
 * / top-up rows) is server-side, and the row display composition rides the
 * shared tx-row module — a row reads identically in both seats. */

interface WalletState {
  balance: number
  held: number
}

const COLLAPSED_COUNT = 3
const FETCH_LIMIT = 50

export function CreditsSection() {
  const { t, i18n } = useTranslation()
  const [wallet, setWallet] = useState<WalletState | null>(null)
  const [items, setItems] = useState<WalletTransaction[] | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await apiFetch("/api/v1/wallet", { toast: false })
        if (res.ok && !cancelled) setWallet((await res.json()) as WalletState)
      } catch {
        /* silent — the overview keeps "—" */
      }
      try {
        const res = await apiFetch(
          `/api/v1/wallet/transactions?limit=${FETCH_LIMIT}`,
          { toast: false },
        )
        if (res.ok && !cancelled) {
          setItems(((await res.json()) as { items: WalletTransaction[] }).items)
        }
      } catch {
        /* silent — the list keeps its last value */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const visible = expanded ? items : items?.slice(0, COLLAPSED_COUNT)

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t("credits.subtitle")}</p>

      <Card className="gap-0 px-4 py-2">
        <p className="pb-1 pt-2 text-[11px] text-meta">
          {t("credits.overview")}
        </p>
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
        {/* Zero-CTA placeholder — the purchase entry is W11; there is
            nothing to sell yet, so the row is a plain statement. */}
        <div className="flex h-9 items-center gap-2">
          <span className="h-3.5 w-3.5" aria-hidden />
          <span className="text-[11px] text-muted-foreground">
            {t("credits.planFree")}
          </span>
          <span className="ml-auto text-[11px] text-meta">
            {t("credits.plansComing")}
          </span>
        </div>
      </Card>

      <Card className="gap-0 px-4 py-2">
        <p className="pb-1 pt-2 text-[11px] text-meta">{t("credits.recent")}</p>
        {items === null ? (
          <p className="py-1.5 text-xs text-muted-foreground">…</p>
        ) : items.length === 0 ? (
          <p className="py-1.5 text-xs text-muted-foreground">
            {t("credits.tx.empty")}
          </p>
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
