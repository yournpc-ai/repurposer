"use client"

import { useEffect, useState } from "react"
import { Coins } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Card } from "@/components/ui/card"
import { apiFetch } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Credits section of the shared SettingsDialog (BILLING §7 — the balance
 * + ledger full-view seat): overview card (balance / held when active /
 * free-trial placeholder with zero CTA until W11) + recent-activity card.
 * Data rides the SAME two endpoints as the CreditsPill and the account
 * console (三面同源 — zero new endpoints); the semantic fold (spend / grant
 * / top-up rows) is server-side, the client renders label + signed amount
 * + relative time per row. */

interface WalletState {
  balance: number
  held: number
}

interface WalletTransaction {
  id: string
  family: "spend" | "grant" | "topup" | string
  amount: number
  label: string
  created_at: string
}

const COLLAPSED_COUNT = 3

export function CreditsSection() {
  const { t } = useTranslation()
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
        const res = await apiFetch("/api/v1/wallet/transactions?limit=10", {
          toast: false,
        })
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

  const relativeTime = (iso: string) => {
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
    if (seconds < 60) return t("notifications.justNow")
    if (seconds < 3600)
      return t("notifications.minutesAgo", { count: Math.floor(seconds / 60) })
    if (seconds < 86400)
      return t("notifications.hoursAgo", { count: Math.floor(seconds / 3600) })
    return t("notifications.daysAgo", { count: Math.floor(seconds / 86400) })
  }

  const visible = expanded ? items : items?.slice(0, COLLAPSED_COUNT)

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t("credits.subtitle")}</p>

      <Card className="gap-0 px-4 py-2">
        <p className="pb-1 pt-2 text-[11px] text-meta">
          {t("credits.overview")}
        </p>
        <div className="flex h-9 items-center gap-2">
          <Coins className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs text-foreground">{t("credits.balance")}</span>
          <span className="ml-auto text-sm tabular-nums">
            {wallet?.balance ?? "—"}
          </span>
        </div>
        {wallet != null && wallet.held > 0 && (
          <div className="flex h-9 items-center gap-2">
            <span className="h-3.5 w-3.5" aria-hidden />
            <span className="text-xs text-foreground">{t("credits.held")}</span>
            <span className="ml-auto text-sm tabular-nums text-muted-foreground">
              {wallet.held}
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
              <div key={item.id} className="flex items-center gap-2 py-1.5">
                <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                  {item.label}
                </span>
                <span
                  className={cn(
                    "shrink-0 text-xs tabular-nums",
                    item.amount >= 0
                      ? "text-foreground"
                      : "text-muted-foreground",
                  )}
                >
                  {item.amount >= 0 ? `+${item.amount}` : item.amount}
                </span>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {relativeTime(item.created_at)}
                </span>
              </div>
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
