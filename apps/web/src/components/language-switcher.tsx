import { useTranslation } from "react-i18next"
import { Globe, Check } from "lucide-react"

import { setLocale, type Locale } from "@/lib/i18n"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

const locales: { value: Locale; labelKey: string }[] = [
  { value: "zh", labelKey: "languages.zh" },
  { value: "en", labelKey: "languages.en" },
]

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation()
  const current: Locale = i18n.language === "en" ? "en" : "zh"

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("common.language")}
          />
        }
      >
        <Globe className="h-5 w-5" />
      </PopoverTrigger>
      <PopoverContent className="w-40 p-1" align="end">
        <div className="flex flex-col gap-0.5">
          {locales.map((loc) => {
            const active = current === loc.value
            return (
              <Button
                key={loc.value}
                variant={active ? "secondary" : "ghost"}
                className="justify-between"
                size="sm"
                onClick={() => setLocale(loc.value)}
              >
                <span>{t(loc.labelKey)}</span>
                {active && <Check className="h-3.5 w-3.5" />}
              </Button>
            )
          })}
        </div>
      </PopoverContent>
    </Popover>
  )
}
