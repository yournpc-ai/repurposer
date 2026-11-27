import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Dialog } from "@/components/ui/dialog-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import type { CreditTopupRequest } from "@/lib/credits"
import { apiFetch, WALLET_REFRESH_EVENT } from "@/lib/api"
import { fetchPaymentOrder } from "@/lib/payments"
import { formatCredits } from "@/components/credits/tx-row"
import { CreditTopupDialog } from "@/components/credits/CreditTopupDialog"
import { CheckoutReturnDialog } from "@/components/credits/CheckoutReturnDialog"
import {
  SettingsDialogContext,
  type CheckoutReturn,
  type CheckoutReturnState,
  type SettingsSectionId,
} from "./settings-dialog-context"

const SettingsScreen = lazy(() => import("./SettingsScreen"))

const MAX_ORDER_POLLS = 15
const ORDER_POLL_INTERVAL_MS = 2000

async function readWalletBalance(): Promise<number | null> {
  try {
    const res = await apiFetch("/api/v1/wallet", { toast: false })
    if (!res.ok) return null
    const data = (await res.json()) as { balance?: unknown }
    return typeof data.balance === "number" ? data.balance : null
  } catch {
    return null
  }
}

export function SettingsDialogProvider({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const [section, setSection] = useState<SettingsSectionId>("personal")
  const [topupOpen, setTopupOpen] = useState(false)
  const [topupRequest, setTopupRequest] = useState<CreditTopupRequest | null>(null)
  const [checkoutState, setCheckoutState] = useState<CheckoutReturnState | null>(null)
  const [pollNonce, setPollNonce] = useState(0)

  const openRef = useRef(open)
  openRef.current = open
  const sectionRef = useRef(section)
  sectionRef.current = section
  const checkoutStateRef = useRef(checkoutState)
  checkoutStateRef.current = checkoutState
  const handledReturnKeyRef = useRef<string | null>(null)
  const bgToastIdRef = useRef<string | null>(null)

  const dismissBgToast = useCallback(() => {
    if (bgToastIdRef.current) {
      toast.dismiss(bgToastIdRef.current)
      bgToastIdRef.current = null
    }
  }, [])

  const showBgConfirmingToast = useCallback(
    (orderId: string) => {
      const toastId = `checkout-confirm:${orderId}`
      bgToastIdRef.current = toastId
      toast.loading(t("credits.return.confirmingBackground"), { id: toastId })
    },
    [t],
  )

  const openSettings = useCallback((s: SettingsSectionId = "personal") => {
    setSection(s)
    setTopupOpen(false)
    setTopupRequest(null)
    setOpen(true)
  }, [])

  const openCreditTopup = useCallback((shortfall?: CreditTopupRequest) => {
    setTopupRequest(shortfall ?? null)
    setTopupOpen(true)
  }, [])

  const closeCreditTopup = useCallback(() => {
    setTopupOpen(false)
    setTopupRequest(null)
  }, [])

  const handleCheckoutReturn = useCallback(
    ({ orderId, outcome, surface = "inline" }: CheckoutReturn) => {
      const key = `${orderId}:${outcome}`
      if (handledReturnKeyRef.current === key) return
      handledReturnKeyRef.current = key

      setTopupOpen(false)
      setTopupRequest(null)
      dismissBgToast()

      if (outcome === "cancelled") {
        if (surface === "settings") {
          setSection("credits")
          setOpen(true)
        }
        toast.info(t("credits.return.cancelled"))
        return
      }

      if (surface === "settings") {
        setSection("credits")
        setOpen(true)
      }
      setCheckoutState({
        orderId,
        surface,
        phase: "confirming",
        order: null,
        walletBalance: null,
        dialogVisible: surface === "inline",
      })
      setPollNonce((value) => value + 1)
    },
    [dismissBgToast, t],
  )

  const retryCheckoutCheck = useCallback(() => {
    setCheckoutState((current) => {
      if (!current) return null
      return {
        ...current,
        phase: "confirming",
        dialogVisible: current.surface === "inline" ? true : current.dialogVisible,
      }
    })
    setPollNonce((value) => value + 1)
  }, [])

  const dismissCheckoutState = useCallback(() => {
    dismissBgToast()
    setCheckoutState(null)
  }, [dismissBgToast])

  const closeCheckoutDialog = useCallback(() => {
    const current = checkoutStateRef.current
    if (!current) return
    if (current.phase === "confirming") {
      setCheckoutState({ ...current, dialogVisible: false })
      showBgConfirmingToast(current.orderId)
      return
    }
    dismissBgToast()
    setCheckoutState(null)
  }, [dismissBgToast, showBgConfirmingToast])

  const onOpenChange = useCallback(
    (next: boolean) => {
      setOpen(next)
      if (!next) {
        const current = checkoutStateRef.current
        if (current?.surface === "settings" && current.phase === "confirming") {
          showBgConfirmingToast(current.orderId)
        } else if (current?.surface === "settings" && current.phase !== "confirming") {
          setCheckoutState(null)
        }
      }
    },
    [showBgConfirmingToast],
  )

  const activeOrderId =
    checkoutState?.phase === "confirming" ? checkoutState.orderId : null

  useEffect(() => {
    if (!activeOrderId) return

    let stopped = false
    let timer: number | undefined
    let polls = 0
    let inFlight = false

    const isSurfaceVisible = () => {
      const current = checkoutStateRef.current
      if (!current) return false
      if (current.surface === "inline") return current.dialogVisible
      return openRef.current && sectionRef.current === "credits"
    }

    const check = async () => {
      if (stopped || inFlight) return
      inFlight = true
      const order = await fetchPaymentOrder(activeOrderId).catch(() => null)
      inFlight = false
      if (stopped) return

      polls += 1
      if (order) {
        setCheckoutState((current) =>
          current && current.orderId === activeOrderId
            ? { ...current, order }
            : current,
        )
      }

      if (order?.status === "paid") {
        const walletBalance = await readWalletBalance()
        if (stopped) return
        dismissBgToast()
        window.dispatchEvent(new Event(WALLET_REFRESH_EVENT))
        if (!isSurfaceVisible()) {
          toast.success(
            t("credits.topupSuccessToast", {
              count: formatCredits(order.credits, i18n.language),
            }),
          )
          setCheckoutState(null)
        } else {
          setCheckoutState((current) =>
            current && current.orderId === activeOrderId
              ? { ...current, order, walletBalance, phase: "paid" }
              : current,
          )
        }
        return
      }

      if (order?.status === "expired" || order?.status === "failed") {
        dismissBgToast()
        toast.error(t("credits.return.failed"))
        setCheckoutState(null)
        return
      }

      if (polls >= MAX_ORDER_POLLS) {
        dismissBgToast()
        if (!isSurfaceVisible()) {
          toast.info(t("credits.return.pending"))
          setCheckoutState(null)
        } else {
          setCheckoutState((current) =>
            current && current.orderId === activeOrderId
              ? { ...current, phase: "pending" }
              : current,
          )
        }
        return
      }

      timer = window.setTimeout(() => void check(), ORDER_POLL_INTERVAL_MS)
    }

    const onVisibility = () => {
      if (document.visibilityState !== "visible" || stopped) return
      if (timer !== undefined) {
        window.clearTimeout(timer)
        timer = undefined
      }
      void check()
    }

    document.addEventListener("visibilitychange", onVisibility)
    void check()

    return () => {
      stopped = true
      document.removeEventListener("visibilitychange", onVisibility)
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [activeOrderId, pollNonce, dismissBgToast, i18n.language, t])

  const viewTopupsFromCheckout = useCallback(() => {
    dismissBgToast()
    setCheckoutState(null)
    setSection("credits")
    setOpen(true)
  }, [dismissBgToast])

  const inlineCheckoutOpen = Boolean(
    checkoutState && checkoutState.surface === "inline" && checkoutState.dialogVisible,
  )

  const handle = useMemo(
    () => ({
      modalOpen: open || topupOpen || inlineCheckoutOpen,
      settingsOpen: open,
      openSettings,
      openCreditTopup,
      handleCheckoutReturn,
      checkoutState,
      retryCheckoutCheck,
      dismissCheckoutState,
    }),
    [
      open,
      topupOpen,
      inlineCheckoutOpen,
      openSettings,
      openCreditTopup,
      handleCheckoutReturn,
      checkoutState,
      retryCheckoutCheck,
      dismissCheckoutState,
    ],
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
      <CheckoutReturnDialog
        state={checkoutState}
        onClose={closeCheckoutDialog}
        onRetry={retryCheckoutCheck}
        onViewTopups={viewTopupsFromCheckout}
      />
    </SettingsDialogContext.Provider>
  )
}
