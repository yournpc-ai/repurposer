"use client"

import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"

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

/** One ledger row: line 1 = title + signed amount, line 2 = time · project
 * (meta). Signed amounts stay neutral (no green/red semantics). */
export function TransactionRow({
  item,
  className,
}: {
  item: WalletTransaction
  className?: string
}) {
  const { t, i18n } = useTranslation()
  const relativeTime = useRelativeTime()

  let title = item.label ?? ""
  if (!title) {
    // Unknown/forward-compat types drop out (a missing i18n key echoes back
    // as the key string).
    const nouns = (item.output_types ?? [])
      .map((ty) => {
        const key = `studio.anchorCards.types.${ty}`
        const noun = t(key)
        return noun === key ? null : noun
      })
      .filter((noun): noun is string => noun != null)
    // Chain: LLM name → produced-type nouns (世界自证) → instruction echo →
    // the family word (near-unreachable).
    title = nouns.length > 0 ? nouns.join(" · ") : (item.hint ?? "") || t("credits.tx.spent")
  }
  const meta = [relativeTime(item.created_at), item.project_name]
    .filter(Boolean)
    .join(" · ")

  return (
    <div className={cn("flex items-center gap-2 py-1.5", className)}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs text-foreground">{title}</p>
        {/* Row meta is plain muted — text-meta (uppercase eyebrow) is the
            section header's register, never a per-row voice. */}
        {meta && (
          <p className="truncate text-[11px] text-muted-foreground">{meta}</p>
        )}
      </div>
      <span
        className={cn(
          "shrink-0 text-xs tabular-nums",
          item.amount >= 0 ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {item.amount >= 0 ? "+" : ""}
        {formatCredits(item.amount, i18n.language)}
      </span>
    </div>
  )
}
