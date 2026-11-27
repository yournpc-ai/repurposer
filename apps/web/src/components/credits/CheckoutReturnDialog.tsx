"use client"

import { useTranslation } from "react-i18next"
import { CircleCheck } from "@/components/ui/icons"

import { Button } from "@/components/ui/button-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { formatCredits } from "@/components/credits/tx-row"
import { formatMoney } from "@/lib/payments"
import type { CheckoutReturnState } from "@/components/settings/settings-dialog-context"

/** In-place confirmation surface for inline Checkout returns (home, project, etc.).
 * Closing while confirming hands off to a background toast without stopping polling. */
export function CheckoutReturnDialog({
  state,
  onClose,
  onRetry,
  onViewTopups,
}: {
  state: CheckoutReturnState | null
  onClose: () => void
  onRetry: () => void
  onViewTopups: () => void
}) {
  const { t, i18n } = useTranslation()
  const open = Boolean(state && state.surface === "inline" && state.dialogVisible)
  const order = state?.order ?? null
  const orderSummary =
    order != null
      ? `${formatMoney(order.amount_minor, order.currency, i18n.language)} · +${t("credits.packageCredits", {
          count: formatCredits(order.credits, i18n.language),
        })}`
      : null

  const title =
    state?.phase === "paid"
      ? t("credits.paymentSuccess")
      : t("credits.buyTitle")

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title={title}
      closeLabel={t("common.close")}
      size="sm"
    >
      {state?.phase === "confirming" && (
        <div className="flex flex-col items-center py-6 text-center" role="status">
          <Spinner size={28} />
          <p className="mt-4 text-sm font-medium text-foreground">
            {t("credits.return.confirming")}
          </p>
          {orderSummary && (
            <p className="mt-1 text-xs text-muted-foreground tabular-nums">
              {orderSummary}
            </p>
          )}
          <p className="mt-3 max-w-xs text-xs leading-relaxed text-muted-foreground">
            {t("credits.return.confirmingHint")}
          </p>
        </div>
      )}

      {state?.phase === "paid" && (
        <div className="grid gap-5">
          <div className="flex flex-col items-center py-6 text-center">
            <CircleCheck className="size-11 text-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-base font-semibold text-foreground tabular-nums">
              {t("credits.topupSuccess", {
                count: formatCredits(order?.credits ?? 0, i18n.language),
              })}
            </p>
            {state.walletBalance !== null && (
              <p className="mt-1 text-xs text-muted-foreground tabular-nums">
                {t("credits.topupSuccessBalance", {
                  balance: formatCredits(state.walletBalance, i18n.language),
                })}
              </p>
            )}
          </div>
          <div className="grid gap-2">
            <Button type="button" size="lg" className="w-full" onClick={onClose}>
              {t("common.done")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={onViewTopups}
            >
              {t("credits.viewTopups")}
            </Button>
          </div>
        </div>
      )}

      {state?.phase === "pending" && (
        <div className="grid gap-5">
          <div className="flex flex-col items-center py-5 text-center" role="status">
            {orderSummary && (
              <p className="text-xs font-medium text-foreground tabular-nums">
                {orderSummary}
              </p>
            )}
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {t("credits.return.pending")}
            </p>
          </div>
          <div className="flex justify-end gap-2 border-t border-subtle pt-4">
            <Button type="button" variant="secondary" size="md" onClick={onClose}>
              {t("credits.later")}
            </Button>
            <Button type="button" size="md" onClick={onRetry}>
              {t("credits.checkAgain")}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  )
}
