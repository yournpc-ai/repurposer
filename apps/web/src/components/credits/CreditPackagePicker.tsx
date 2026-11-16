"use client"

import { useEffect, useState } from "react"
import { Info } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  createCheckoutSession,
  fetchCreditPackages,
  formatAmountInput,
  formatCurrencySymbol,
  formatMoney,
  parseAmountMinor,
  type CreditPackageCatalog,
} from "@/lib/payments"
import { cn } from "@/lib/utils"
import { formatCredits } from "@/components/credits/tx-row"

/** The only amount-selection and Checkout-start component, hosted solely by
 * the top-up dialog. Presets fill the input; typing returns to custom amount. */
export function CreditPackagePicker({ onCancel }: { onCancel?: () => void }) {
  const { t, i18n } = useTranslation()
  const [catalog, setCatalog] = useState<CreditPackageCatalog | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadFailed, setLoadFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [amountInput, setAmountInput] = useState("")
  const [purchasing, setPurchasing] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadFailed(false)
    void fetchCreditPackages()
      .then((next) => {
        if (cancelled) return
        setCatalog(next)
        const initial = next.items[0] ?? null
        setSelectedKey(initial?.key ?? null)
        setAmountInput(initial ? formatAmountInput(initial.amount_minor) : "")
      })
      .catch(() => {
        if (cancelled) return
        setCatalog(null)
        setSelectedKey(null)
        setLoadFailed(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const packages = catalog?.items ?? []
  const policy = catalog?.custom ?? null
  const selected = packages.find((item) => item.key === selectedKey) ?? null
  const amountMinor = parseAmountMinor(amountInput)
  const amountValid =
    amountMinor !== null &&
    (selected
      ? amountMinor === selected.amount_minor
      : policy !== null &&
        amountMinor >= policy.min_amount_minor &&
        amountMinor <= policy.max_amount_minor)
  const credits =
    amountValid && amountMinor !== null
      ? (selected?.credits ??
        (policy !== null
          ? Math.floor((amountMinor * policy.credits_per_major) / 100)
          : null))
      : null

  const buy = async () => {
    if (amountMinor === null || !amountValid || purchasing) return
    setPurchasing(true)
    try {
      const result = await createCheckoutSession({ amountMinor })
      if (result) {
        window.location.assign(result.checkout_url)
        return
      }
    } catch {
      // apiFetch reports network/server failures through the global toast.
    }
    setPurchasing(false)
  }

  if (loading) {
    return (
      <div className="space-y-4" aria-label={t("common.loading")}>
        <Skeleton className="h-12.5 w-full" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="ml-auto h-11 w-48" />
      </div>
    )
  }

  if (loadFailed || !policy) {
    return (
      <div className="flex items-center gap-3 rounded-md bg-muted px-3 py-2">
        <p className="min-w-0 flex-1 text-xs text-muted-foreground">
          {t("credits.packagesLoadFailed")}
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setReloadKey((value) => value + 1)}
        >
          {t("credits.retry")}
        </Button>
      </div>
    )
  }

  const conversion = t("credits.conversion", {
    unit: formatMoney(100, policy.currency, i18n.language),
    credits: formatCredits(policy.credits_per_major, i18n.language),
  })
  const amountRange = t("credits.amountRange", {
    min: formatMoney(policy.min_amount_minor, policy.currency, i18n.language),
    max: formatMoney(policy.max_amount_minor, policy.currency, i18n.language),
  })
  const inputCurrency = selected?.currency ?? policy.currency
  const showAmountError = amountInput.length > 0 && !amountValid

  return (
    <div className="space-y-5">
      <div>
        <div className="relative">
          <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-xl text-muted-foreground">
            {formatCurrencySymbol(inputCurrency, i18n.language)}
          </span>
          <Input
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={amountInput}
            disabled={purchasing}
            aria-label={t("credits.amount")}
            aria-invalid={showAmountError}
            aria-describedby="credit-topup-amount-hint"
            onChange={(event) => {
              setAmountInput(event.target.value)
              setSelectedKey(null)
            }}
            className="h-12.5 rounded-md bg-muted pl-10 pr-4 text-2xl font-semibold tabular-nums md:text-2xl dark:bg-muted"
            placeholder="0.00"
          />
        </div>
        <div className="mt-2 flex min-h-5 items-center gap-1">
          <p
            id="credit-topup-amount-hint"
            className={cn(
              "text-sm",
              showAmountError ? "text-destructive" : "font-medium text-muted-foreground",
            )}
          >
            {credits !== null
              ? t("credits.packageCredits", {
                  count: formatCredits(credits, i18n.language),
                })
              : showAmountError
                ? amountRange
                : ""}
          </p>
          <Tooltip>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  aria-label={t("credits.rateInfo")}
                  className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground"
                />
              }
            >
              <Info className="size-3.5" />
            </TooltipTrigger>
            <TooltipContent side="top" align="start" className="max-w-64">
              <div className="space-y-1">
                <p>{conversion}</p>
                <p>{amountRange}</p>
              </div>
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      {packages.length > 0 && (
        <div
          className="grid grid-cols-3 gap-2"
          role="group"
          aria-label={t("credits.amount")}
        >
          {packages.map((item) => {
            const checked = item.key === selectedKey
            return (
              <Button
                key={item.key}
                type="button"
                variant={checked ? "default" : "secondary"}
                size="lg"
                aria-pressed={checked}
                disabled={purchasing}
                className="min-w-0 text-base"
                onClick={() => {
                  setSelectedKey(item.key)
                  setAmountInput(formatAmountInput(item.amount_minor))
                }}
              >
                {formatMoney(item.amount_minor, item.currency, i18n.language)}
              </Button>
            )
          })}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button
            type="button"
            variant="secondary"
            size="lg"
            disabled={purchasing}
            onClick={onCancel}
          >
            {t("common.cancel")}
          </Button>
        )}
        <Button
          type="button"
          size="lg"
          disabled={!amountValid || purchasing}
          onClick={() => void buy()}
        >
          {purchasing ? t("credits.buying") : t("credits.pay")}
        </Button>
      </div>
    </div>
  )
}
