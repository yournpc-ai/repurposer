"use client"

import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"
import { formatMoney } from "@/lib/payments"
import { Badge } from "@/components/ui/badge-clean"

/** The wallet ledger row's wire shape + display composition — ONE seat for
 * both read surfaces (the CreditsPill popover and the SettingsDialog
 * credits section), so a row can never read differently by where it renders.
 *
 * Title composition follows ADR-058 二源律: the server-sent ``label`` first
 * (a spend's LLM-chosen plan name; grant/topup's family word); an unnamed
 * spend falls back to its produced types' nouns (世界自证 — the SAME
 * ``studio.anchorCards.types`` seat as the canvas badges, never a second
 * vocabulary), then the instruction echo (``hint``), then the generic
 * family word. The meta line is ``time · project``. */

export interface WalletTransaction {
  id: string
  /** The semantic fold's three families (ADR-057 K4 — the ledger's
   * hold/capture/release machinery never crosses the wire): spend = 花费 /
   * grant = 赠送 / topup = 充值. */
  family: "spend" | "grant" | "topup" | string
  amount: number
  label: string | null
  /** A spend's produced PUBLIC output types — the honest fallback facts. */
  output_types: string[]
  /** A spend's trimmed instruction — the last-resort echo (the user's own
   * words, ADR-060) for runs with neither a name nor public outputs. */
  hint: string | null
  project_name: string | null
  created_at: string
  payment_order_id?: string | null
  payment_provider?: string | null
  payment_amount_minor?: number | null
  payment_currency?: string | null
  paid_at?: string | null
}

/** Locale-aware thousands grouping (94,083) — pill trigger, hero, rows. */
export function formatCredits(n: number, lang: string): string {
  return new Intl.NumberFormat(lang).format(n)
}

/** Same relative-time helper as NotificationBell (reuses the notifications.*
 * keys) — the credits surfaces' shared seat. */
export function useRelativeTime() {
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

/** Public output nouns share the canvas badge vocabulary in both spend rows
 * and the title fallback; unknown forward-compat types simply drop out. */
function useOutputTypeNouns() {
  const { t } = useTranslation()
  return (types: string[]) =>
    types
      .map((ty) => {
        const key = `studio.anchorCards.types.${ty}`
        const noun = t(key)
        return noun === key ? null : noun
      })
      .filter((noun): noun is string => noun != null)
}

/** Shared title composition for the compact rows and the Settings table. */
export function useTransactionTitle() {
  const { t } = useTranslation()
  const outputTypeNouns = useOutputTypeNouns()
  return (item: WalletTransaction) => {
    if (item.label) return item.label
    const nouns = outputTypeNouns(item.output_types ?? [])
    // Chain: LLM name → produced-type nouns (世界自证) → instruction echo →
    // the family word (near-unreachable).
    return nouns.length > 0 ? nouns.join(" · ") : (item.hint ?? "") || t("credits.tx.spent")
  }
}

function SignedCredits({ amount }: { amount: number }) {
  const { i18n } = useTranslation()
  return (
    <span
      className={cn(
        "shrink-0 whitespace-nowrap text-sm leading-5 font-medium tabular-nums",
        amount >= 0 ? "text-foreground" : "text-muted-foreground",
      )}
    >
      {amount >= 0 ? "+" : ""}
      {formatCredits(amount, i18n.language)}
    </span>
  )
}

/** One ledger row: line 1 = title + signed amount, line 2 = time · project
 * (meta). Signed amounts stay neutral (no green/red semantics). */
export function TransactionRow({
  item,
  className,
}: {
  item: WalletTransaction
  className?: string
}) {
  const relativeTime = useRelativeTime()
  const getTitle = useTransactionTitle()
  const title = getTitle(item)
  const meta = [relativeTime(item.created_at), item.project_name]
    .filter(Boolean)
    .join(" · ")

  return (
    <div className={cn("flex items-start gap-4 py-1.5", className)}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm leading-5 text-foreground">{title}</p>
        {/* Row meta is plain muted — text-meta (uppercase eyebrow) is the
            section header's register, never a per-row voice. */}
        {meta && (
          <p className="mt-0.5 truncate text-[11px] leading-4 text-muted-foreground">
            {meta}
          </p>
        )}
      </div>
      <SignedCredits amount={item.amount} />
    </div>
  )
}

function formatTransactionTime(iso: string, lang: string): string {
  return new Intl.DateTimeFormat(lang, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso))
}

/** Spend row for Settings: absolute time and separate project/amount columns
 * make settled production charges easier to reconcile than a glance row. */
export function SpendTableRow({ item }: { item: WalletTransaction }) {
  const { i18n } = useTranslation()
  const getTitle = useTransactionTitle()
  const outputTypeNouns = useOutputTypeNouns()
  const outputs = outputTypeNouns(item.output_types ?? [])
  const reference = item.id.startsWith("run:") ? item.id.slice(4) : item.id

  return (
    <tr className="border-b border-subtle transition-colors last:border-0 hover:bg-accent">
      <td className="px-4 py-3 align-middle text-xs whitespace-nowrap text-muted-foreground tabular-nums">
        <p title={reference}>#{reference}</p>
      </td>
      <td className="px-4 py-3 align-middle">
        <p className="text-sm leading-5 whitespace-nowrap text-foreground">{getTitle(item)}</p>
      </td>
      <td className="px-4 py-3 align-middle">
        {outputs.length > 0 ? (
          <div className="flex flex-nowrap gap-1">
            {outputs.map((output) => (
              <Badge key={output} tone="neutral">
                {output}
              </Badge>
            ))}
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-3 align-middle">
        <p className="text-xs whitespace-nowrap text-muted-foreground">
          {item.project_name ?? "—"}
        </p>
      </td>
      <td className="px-4 py-3 align-middle text-xs whitespace-nowrap text-muted-foreground tabular-nums">
        {formatTransactionTime(item.created_at, i18n.language)}
      </td>
      <td className="px-4 py-3 text-right align-middle whitespace-nowrap">
        <SignedCredits amount={item.amount} />
      </td>
    </tr>
  )
}

/** Incoming-credit row: purchases expose their linked fiat order facts;
 * grants and legacy rows without an order link stay explicitly unpriced. */
export function TopupTableRow({ item }: { item: WalletTransaction }) {
  const { t, i18n } = useTranslation()
  const getTitle = useTransactionTitle()
  const isPurchase = item.family === "topup"
  const provider = item.payment_provider === "stripe"
    ? "Stripe"
    : (item.payment_provider ?? "—")

  return (
    <tr className="border-b border-subtle transition-colors last:border-0 hover:bg-accent">
      <td className="px-4 py-3 align-middle">
        <p className="text-sm leading-5 whitespace-nowrap text-foreground">{getTitle(item)}</p>
      </td>
      <td className="px-4 py-3 align-middle text-xs whitespace-nowrap text-muted-foreground tabular-nums">
        {item.payment_order_id ? (
          <p title={item.payment_order_id}>
            #{item.payment_order_id}
          </p>
        ) : (
          "—"
        )}
      </td>
      <td className="px-4 py-3 align-middle text-xs whitespace-nowrap text-muted-foreground tabular-nums">
        {formatTransactionTime(item.paid_at ?? item.created_at, i18n.language)}
      </td>
      <td className="px-4 py-3 align-middle text-xs whitespace-nowrap text-muted-foreground">
        {provider}
      </td>
      <td className="px-4 py-3 align-middle text-xs whitespace-nowrap text-muted-foreground tabular-nums">
        {item.payment_amount_minor != null && item.payment_currency
          ? formatMoney(item.payment_amount_minor, item.payment_currency, i18n.language)
          : "—"}
      </td>
      <td className="px-4 py-3 text-right align-middle whitespace-nowrap">
        <SignedCredits amount={item.amount} />
      </td>
      <td className="px-4 py-3 text-right align-middle whitespace-nowrap">
        <Badge tone="neutral">
          {t(isPurchase ? "credits.tx.success" : "credits.tx.credited")}
        </Badge>
      </td>
    </tr>
  )
}
