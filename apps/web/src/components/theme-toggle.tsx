import { Moon, Sun } from "@/components/ui/icons"
import { useTranslation } from "react-i18next"

import { useTheme } from "@/lib/theme/ThemeProvider"
import { IconButton } from "@/components/ui/icon-button-clean"

import { useAccountSettings } from "./settings/account-settings-context"
import { useAuth } from "@/lib/auth-context"

export function ThemeToggle() {
  const { isAuthenticated } = useAuth()
  const { save, busy } = useAccountSettings()
  const { resolved, toggleTheme } = useTheme()
  const { t } = useTranslation()

  return (
    <IconButton size="sm" label={t("common.toggleTheme")}
      icon={resolved === "dark" ? <Moon /> : <Sun />}
      disabled={isAuthenticated && busy}
      onClick={(event) => toggleTheme(
        { clientX: event.clientX, clientY: event.clientY },
        isAuthenticated ? theme => { void save({ theme }) } : undefined,
      )}
    />
  )
}
