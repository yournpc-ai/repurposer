import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { apiGet, apiPut } from "@/lib/api"
import { getToken } from "@/lib/auth"
import { setLocale } from "@/lib/i18n"
import { useTheme } from "@/lib/theme/ThemeProvider"
import {
  AccountSettingsContext,
  type AccountSettings,
  type SettingChange,
} from "./account-settings-context"

export function AccountSettingsProvider({
  token,
  children,
}: {
  token: string | null
  children: ReactNode
}) {
  const { theme, setTheme } = useTheme()
  const { i18n } = useTranslation()
  const [data, setData] = useState<AccountSettings | null>(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const queue = useRef({ pending: {} as SettingChange, writing: false })
  const apply = useCallback(
    (values: SettingChange) => {
      if (values.theme) setTheme(values.theme)
      if (values.locale && values.locale !== i18n.language) setLocale(values.locale, i18n)
    },
    [i18n, setTheme],
  )

  useEffect(() => {
    queue.current = { pending: {}, writing: false }
    setData(null)
    setFailed(false)
    if (!token) {
      setBusy(false)
      return
    }
    let active = true
    setBusy(true)
    void (async () => {
      try {
        const res = await apiGet("/api/v1/auth/settings", { toast: false })
        if (!res.ok) throw new Error()
        const saved: AccountSettings = await res.json()
        if (active && getToken() === token) {
          setData(saved)
          apply(saved)
        }
      } catch {
        if (active) setFailed(true)
      } finally {
        if (active) setBusy(false)
      }
    })()
    return () => {
      active = false
    }
  }, [token, revision, apply])

  async function save(change: SettingChange) {
    if (busy || !token || token !== getToken()) return
    const localDefaults = {
      theme,
      locale: i18n.language === "zh" ? ("zh" as const) : ("en" as const),
    }
    const batch = queue.current
    Object.assign(batch.pending, change)
    apply(change)
    setData((previous) => previous && { ...previous, ...change })
    if (batch.writing) return
    batch.writing = true
    let confirmed = data
    try {
      while (Object.keys(batch.pending).length && queue.current === batch && token === getToken()) {
        const patch = batch.pending
        batch.pending = {}
        try {
          const res = await apiPut("/api/v1/auth/settings", patch)
          if (res.ok) confirmed = (await res.json()) as AccountSettings
        } catch {
          /* apiPut reports the error. Restore the last saved values below. */
        }
        if (queue.current !== batch || token !== getToken()) return
        setData(confirmed && { ...confirmed, ...batch.pending })
        if (confirmed) setFailed(false)
        apply({
          theme: confirmed?.theme ?? localDefaults.theme,
          locale: confirmed?.locale ?? localDefaults.locale,
          ...batch.pending,
        })
      }
    } finally {
      batch.writing = false
    }
  }
  return (
    <AccountSettingsContext.Provider
      value={{ data, busy, failed, save, reload: () => setRevision((n) => n + 1) }}
    >
      {children}
    </AccountSettingsContext.Provider>
  )
}
