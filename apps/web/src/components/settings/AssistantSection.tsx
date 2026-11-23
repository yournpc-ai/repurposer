import { useTranslation } from "react-i18next"
import { Select } from "@/components/ui/select-clean"
import { useAccountSettings } from "./account-settings-context"

type ConfirmKey = "confirm_execution" | "confirm_credits"

export function AssistantSection() {
  const { t } = useTranslation()
  const { data: prefs, busy, save } = useAccountSettings()
  if (!prefs) return null
  const prefRow = (key: ConfirmKey, labelKey: string, descKey: string) => (
    <div className="settings-row">
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground">{t(labelKey)}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{t(descKey)}</p>
      </div>
      <Select
        size="sm"
        aria-label={t(labelKey)}
        options={[
          { value: "auto", label: t("assistant.mode.auto") },
          { value: "ask", label: t("assistant.mode.ask") },
        ]}
        value={prefs[key]}
        onChange={(value) => void save({ [key]: value })}
        disabled={busy}
      />
    </div>
  )

  return (
    <section className="settings-group">
      <h4>{t("assistant.permissions")}</h4>
      <div className="settings-card">
        {prefRow("confirm_execution", "assistant.execution.label", "assistant.execution.desc")}
        {prefRow("confirm_credits", "assistant.spending.label", "assistant.spending.desc")}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        {t("assistant.footnote")}
      </p>
    </section>
  )
}
