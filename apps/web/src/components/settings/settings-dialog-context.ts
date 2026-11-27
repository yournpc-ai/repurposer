"use client"

import { createContext, useContext } from "react"
import type { CreditTopupRequest } from "@/lib/credits"
import type { PaymentOrder } from "@/lib/payments"

export type SettingsSectionId = "personal" | "profile" | "channels" | "credits" | "notifications" | "security"

export type CheckoutReturnSurface = "inline" | "settings"

export interface CheckoutReturn {
  orderId: string
  outcome: "success" | "cancelled"
  surface?: CheckoutReturnSurface
}

export type CheckoutStatusPhase = "confirming" | "pending" | "paid"

export interface CheckoutReturnState {
  orderId: string
  surface: CheckoutReturnSurface
  phase: CheckoutStatusPhase
  order: PaymentOrder | null
  walletBalance: number | null
  dialogVisible: boolean
}

export interface SettingsDialogHandle {
  modalOpen: boolean
  settingsOpen: boolean
  openSettings: (section?: SettingsSectionId) => void
  openCreditTopup: (shortfall?: CreditTopupRequest) => void
  handleCheckoutReturn: (checkoutReturn: CheckoutReturn) => void
  checkoutState: CheckoutReturnState | null
  retryCheckoutCheck: () => void
  dismissCheckoutState: () => void
}

/** Kept apart from the component module so HMR cannot split providers and
 * consumers across two Context identities. */
export const SettingsDialogContext = createContext<SettingsDialogHandle | null>(null)

export function useSettingsDialog(): SettingsDialogHandle {
  const ctx = useContext(SettingsDialogContext)
  if (!ctx)
    throw new Error("useSettingsDialog must be used within SettingsDialogProvider")
  return ctx
}
