import { Moon, Sun } from "lucide-react"
import { useTranslation } from "react-i18next"

import { useTheme } from "@/lib/theme/ThemeProvider"
import { IconButton } from "@/components/ui/icon-button-clean"

export function ThemeToggle() {
  const { resolved, toggleTheme } = useTheme()
  const { t } = useTranslation()

  return (
    <IconButton size="sm" label={t("common.toggleTheme")}
      icon={resolved === "dark" ? <Moon /> : <Sun />}
      onClick={(event) => toggleTheme({ clientX: event.clientX, clientY: event.clientY })}
    />
  )
}
