"use client"

import { useTranslation } from "react-i18next"

import { CreditPackagePicker } from "@/components/credits/CreditPackagePicker"
import { formatCredits } from "@/components/credits/tx-row"
import { Dialog } from "@/components/ui/dialog-clean"
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
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title={t("credits.buyTitle")}
      closeLabel={t("common.close")}
      description={
        shortfall &&
        t("credits.insufficient", {
          balance: formatCredits(shortfall.balance, i18n.language),
          required: formatCredits(shortfall.required, i18n.language),
        })
      }
    >
      {open && (
        <div className="mt-6">
          <CreditPackagePicker onCancel={onClose} />
        </div>
      )}
    </Dialog>
  )
}
