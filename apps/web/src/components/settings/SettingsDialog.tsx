import { lazy, Suspense, useCallback, useMemo, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { Dialog } from "@/components/ui/dialog-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import type { CreditTopupRequest } from "@/lib/credits"
import { CreditTopupDialog } from "@/components/credits/CreditTopupDialog"
import {
  SettingsDialogContext,
  type CheckoutReturn,
  type SettingsSectionId,
} from "./settings-dialog-context"

const SettingsScreen = lazy(() => import("./SettingsScreen"))

export function SettingsDialogProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [section, setSection] = useState<SettingsSectionId>("personal")
  const [checkoutReturn, setCheckoutReturn] = useState<CheckoutReturn | null>(null)
  const [topupOpen, setTopupOpen] = useState(false)
  const [topupRequest, setTopupRequest] = useState<CreditTopupRequest | null>(null)

  const openSettings = useCallback(
    (s: SettingsSectionId = "personal", checkout?: CheckoutReturn) => {
      setSection(s)
      setCheckoutReturn(checkout ?? null)
      setTopupOpen(false)
      setTopupRequest(null)
      setOpen(true)
    },
    [],
  )
  const openCreditTopup = useCallback((shortfall?: CreditTopupRequest) => {
    setTopupRequest(shortfall ?? null)
    setTopupOpen(true)
  }, [])
  const closeCreditTopup = useCallback(() => {
    setTopupOpen(false)
    setTopupRequest(null)
  }, [])
  const clearCheckoutReturn = useCallback(() => setCheckoutReturn(null), [])
  const onOpenChange = useCallback((next: boolean) => {
    setOpen(next)
    if (!next) setCheckoutReturn(null)
  }, [])

  const handle = useMemo(
    () => ({
      modalOpen: open || topupOpen,
      openSettings,
      openCreditTopup,
      checkoutReturn,
      clearCheckoutReturn,
    }),
    [open, topupOpen, openSettings, openCreditTopup, checkoutReturn, clearCheckoutReturn],
  )

  return (
    <SettingsDialogContext.Provider value={handle}>
      {children}
      <Dialog
        open={open}
        onOpenChange={onOpenChange}
        title={t("settings.title")}
        closeLabel={t("common.close")}
        width="min(69rem, 94vw)"
        className="account-settings"
      >
        <Suspense
          fallback={
            <div className="settings-loading">
              <Spinner label={t("common.loading")} />
            </div>
          }
        >
          <SettingsScreen section={section} onSectionChange={setSection} />
        </Suspense>
      </Dialog>
      <CreditTopupDialog open={topupOpen} shortfall={topupRequest} onClose={closeCreditTopup} />
    </SettingsDialogContext.Provider>
  )
}
