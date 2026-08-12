import { createInstance, type i18n as I18n } from "i18next"
import { initReactI18next } from "react-i18next"

import en from "./locales/en"
import zh from "./locales/zh"

export const LANG_COOKIE = "repurposer-lang"
export type Locale = "zh" | "en"

export function normalizeLocale(value: string | null | undefined): Locale | null {
  return value === "zh" || value === "en" ? value : null
}

export function readLangCookie(): Locale | null {
  if (typeof document === "undefined") return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${LANG_COOKIE}=([^;]*)`))
  return normalizeLocale(match ? decodeURIComponent(match[1]) : null)
}

/**
 * One instance per app mount — on the server that is per REQUEST (concurrent
 * SSR renders must never share mutable language state), on the client the
 * single mount. The provider mounts it already in the cookie language, so SSR
 * HTML and the first client render agree and no post-hydration language
 * switch exists (lazy route boundaries hydrate after root effects — a switch
 * there mismatches their SSR'd text). Always a fresh instance: in dev, HMR
 * reloads the locale modules and a new mount must serve fresh keys.
 */
export function createI18n(lng: Locale): I18n {
  const instance = createInstance()
  instance.use(initReactI18next).init({
    resources: {
      zh: { translation: zh },
      en: { translation: en },
    },
    lng,
    fallbackLng: "en",
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  })
  return instance
}

// Imperative consumers (apiFetch toasts, mention labels) run client-side after
// the provider mounts; `active` points at the provider's instance. The
// fallback keeps a bare module import safe (SSR module evaluation, tests).
// The registry lives on globalThis: any locale edit re-executes this module
// under vite HMR while React keeps the old provider mounted — module-scope
// state would reset to null and strand setLocale on an orphaned instance
// (click does nothing). Server-side it's written per request but never read
// (components read the context instance via useTranslation).
const registry = ((globalThis as Record<string, unknown>).__repurposerI18n ??= {
  active: null as I18n | null,
  fallback: null as I18n | null,
}) as { active: I18n | null; fallback: I18n | null }

export function setActiveI18n(instance: I18n) {
  registry.active = instance
}

function current(): I18n {
  if (registry.active) return registry.active
  if (!registry.fallback) registry.fallback = createI18n("en")
  return registry.fallback
}

/** Change the active language and persist the choice to a cookie. Interactive
 * callers pass their context instance (from `useTranslation`) — the subscribed
 * instance is always the right one, immune to dev HMR module duplication;
 * the registry is only the fallback for non-React callers. */
export function setLocale(lng: Locale, instance?: I18n) {
  ;(instance ?? current()).changeLanguage(lng)
  if (typeof document !== "undefined") {
    document.cookie = `${LANG_COOKIE}=${lng};path=/;max-age=31536000;samesite=lax`
  }
}

/** Facade over the active instance for non-React consumers. */
const i18nFacade = {
  t: (key: string) => current().t(key),
  get language() {
    return current().language
  },
}

export default i18nFacade
