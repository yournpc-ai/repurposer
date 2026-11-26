import { Monitor, Moon, Sun } from "@/components/ui/icons"
import { useTranslation } from "react-i18next"
import { SegmentedControl } from "@/components/ui/segmented-control"
import type { Locale } from "@/lib/i18n"
import { useTheme, type Theme } from "@/lib/theme/ThemeProvider"
import { useAccountSettings } from "./account-settings-context"

const themes = [
  { value: "system", icon: Monitor, key: "common.themeSystem" },
  { value: "light", icon: Sun, key: "common.themeLight" },
  { value: "dark", icon: Moon, key: "common.themeDark" },
] as const

export function AppearanceChoice({
  compact = false,
  className,
}: {
  compact?: boolean
  className?: string
}) {
  const { theme } = useTheme()
  const { t } = useTranslation()
  const { busy, save } = useAccountSettings()
  return (
    <SegmentedControl<Theme>
      size="sm"
      fullWidth={compact}
      className={className}
      aria-label={t("common.theme")}
      value={theme}
      disabled={busy}
      onChange={(theme) => void save({ theme })}
      options={themes.map(({ value, icon: Icon, key }) =>
        compact ? { value, icon: <Icon />, ariaLabel: t(key) } : { value, label: t(key) },
      )}
    />
  )
}

export function LanguageChoice({
  compact = false,
  className,
}: {
  compact?: boolean
  className?: string
}) {
  const { t, i18n } = useTranslation()
  const { busy, save } = useAccountSettings()
  return (
    <SegmentedControl<Locale>
      size="sm"
      fullWidth={compact}
      className={className}
      aria-label={t("common.language")}
      value={i18n.language === "zh" ? "zh" : "en"}
      disabled={busy}
      onChange={(locale) => void save({ locale })}
      options={[
        {
          value: "en",
          label: compact ? "EN" : t("languages.en"),
          ariaLabel: t("languages.en"),
        },
        {
          value: "zh",
          label: t("languages.zh"),
          ariaLabel: t("languages.zh"),
        },
      ]}
    />
  )
}
