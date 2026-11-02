"use client"

import { useTranslation } from "react-i18next"

import { CreditPackagePicker } from "@/components/credits/CreditPackagePicker"
import { formatCredits } from "@/components/credits/tx-row"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { CreditTopupRequest } from "@/lib/credits"

/** A short purchase path opened at the spend point. Checkout return still
 * lands in Settings → Credits, where order confirmation and the ledger live. */
export function CreditTopupDialog({
  open,
  shortfall,
  onClose,
}: {
  open: boolean
  shortfall: CreditTopupRequest | null
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <DialogContent className="gap-0 p-6 sm:max-w-lg">
        <DialogHeader className="gap-2 pr-8">
          <DialogTitle className="text-lg font-semibold">
            {t("credits.buyTitle")}
          </DialogTitle>
          <DialogDescription>
            {shortfall
              ? t("credits.insufficient", {
                  balance: formatCredits(shortfall.balance, i18n.language),
                  required: formatCredits(shortfall.required, i18n.language),
                })
              : t("credits.topupSubtitle")}
          </DialogDescription>
        </DialogHeader>
        {open && (
          <div className="mt-6">
            <CreditPackagePicker onCancel={onClose} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
