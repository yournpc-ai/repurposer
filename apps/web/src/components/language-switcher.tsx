import { useTranslation } from "react-i18next"
import { Globe } from "@/components/ui/icons"

import { setLocale, type Locale } from "@/lib/i18n"
import { useAccountSettings } from "./settings/account-settings-context"
import { useAuth } from "@/lib/auth-context"
import { IconButton } from "@/components/ui/icon-button-clean"
import { DropdownMenu } from "@/components/ui/dropdown-menu-clean"

const locales: { value: Locale; labelKey: string }[] = [
  { value: "zh", labelKey: "languages.zh" },
  { value: "en", labelKey: "languages.en" },
]

export function LanguageSwitcher() {
  const { isAuthenticated } = useAuth()
  const { save, busy } = useAccountSettings()
  const { i18n, t } = useTranslation()
  const current: Locale = i18n.language === "en" ? "en" : "zh"

  return (
    <DropdownMenu align="end" title={t("common.language")}
      trigger={({ triggerProps }) => <IconButton {...triggerProps} icon={<Globe />} label={t("common.language")} size="sm" />}
      items={locales.map(({ value, labelKey }) => ({
        label: t(labelKey), checked: current === value, disabled: isAuthenticated && busy,
        onSelect: () => {
          if (isAuthenticated) void save({ locale: value })
          else setLocale(value, i18n)
        },
      }))}
    />
  )
}
