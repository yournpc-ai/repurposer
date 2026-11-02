import { Moon, Sun } from "lucide-react"
import { useTranslation } from "react-i18next"

import { useTheme } from "@/lib/theme/ThemeProvider"
import { Button } from "@/components/ui/button"

export function ThemeToggle() {
  const { resolved, toggleTheme } = useTheme()
  const { t } = useTranslation()

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      className="size-7"
      aria-label={t("common.toggleTheme")}
      onClick={(e) => toggleTheme({ clientX: e.clientX, clientY: e.clientY })}
    >
      {resolved === "dark" ? (
        <Moon className="size-3.5" />
      ) : (
        <Sun className="size-3.5" />
      )}
    </Button>
  )
}
