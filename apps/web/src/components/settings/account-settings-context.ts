import { createContext, useContext } from "react"
import type { Theme } from "@/lib/theme/ThemeProvider"
import type { Locale } from "@/lib/i18n"

export type AccountSettings = {
  theme: Theme | null
  locale: Locale | null
  confirm_execution: "ask" | "auto"
  confirm_credits: "ask" | "auto"
  publish_alerts: boolean
  email_available: boolean
}
export type SettingChange = Partial<Omit<AccountSettings, "email_available">>

export const AccountSettingsContext = createContext<{
  data: AccountSettings | null
  busy: boolean
  failed: boolean
  reload: () => void
  save: (change: SettingChange) => Promise<void>
} | null>(null)

export function useAccountSettings() {
  const value = useContext(AccountSettingsContext)
  if (!value) throw new Error("Account settings provider missing")
  return value
}
