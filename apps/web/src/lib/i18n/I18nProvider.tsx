import { useState } from "react"
import { I18nextProvider } from "react-i18next"

import { createI18n, readLangCookie, setActiveI18n, type Locale } from "@/lib/i18n"

/**
 * Mounts a fresh i18n instance already in the cookie language (server: the
 * root loader's cookie read; client: the cookie itself — they agree), so SSR
 * HTML and the first client render match and hydration never sees a language
 * switch.
 */
export function I18nProvider({
  lang,
  children,
}: {
  lang?: Locale | null
  children: React.ReactNode
}) {
  const [instance] = useState(() => {
    const i = createI18n(lang ?? readLangCookie() ?? "en")
    setActiveI18n(i)
    return i
  })
  return <I18nextProvider i18n={instance}>{children}</I18nextProvider>
}
