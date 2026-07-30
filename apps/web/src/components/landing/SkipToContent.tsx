import { useTranslation } from "react-i18next"
import type { ReactNode } from "react"

/** Keyboard-only shortcut to the main content; hidden until focused. */
export function SkipToContent(): ReactNode {
  const { t } = useTranslation()
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[100] focus:rounded-md focus:bg-background focus:px-4 focus:py-3 focus:text-sm focus:font-medium focus:text-foreground focus:shadow-lg"
    >
      {t("common.skipToContent")}
    </a>
  )
}
