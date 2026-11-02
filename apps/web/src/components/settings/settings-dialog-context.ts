"use client"

import { createContext, useContext } from "react"
import type { CreditTopupRequest } from "@/lib/credits"

export type SettingsSectionId = "channels" | "general" | "assistant" | "credits"

export interface CheckoutReturn {
  orderId: string
  outcome: "success" | "cancelled"
}

export interface SettingsDialogHandle {
  openSettings: (section?: SettingsSectionId, checkoutReturn?: CheckoutReturn) => void
  openCreditTopup: (shortfall?: CreditTopupRequest) => void
  checkoutReturn: CheckoutReturn | null
  clearCheckoutReturn: () => void
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
