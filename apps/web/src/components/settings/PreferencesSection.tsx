import { useTranslation } from "react-i18next"
import { AppearanceChoice, LanguageChoice } from "./PreferenceChoices"
import { AssistantSection } from "./AssistantSection"
import { useAccountSettings } from "./account-settings-context"
import { Button } from "@/components/ui/button-clean"
import { Spinner } from "@/components/ui/spinner-clean"

export function PreferencesSection() {
  const { t } = useTranslation()
  const { data, failed, reload } = useAccountSettings()
  return (
    <>
      <section aria-label={t("settings.appearanceGroup")} className="settings-card">
        <div className="settings-row">
          <div>
            <b>{t("common.language")}</b>
            <small>{t("settings.languageHint")}</small>
          </div>
          <LanguageChoice />
        </div>
        <div className="settings-row">
          <div>
            <b>{t("common.theme")}</b>
            <small>{t("settings.themeHint")}</small>
          </div>
          <AppearanceChoice />
        </div>
      </section>
      {data ? (
        <AssistantSection />
      ) : failed ? (
        <Button size="sm" onClick={reload}>
          {t("credits.retry")}
        </Button>
      ) : (
        <Spinner label={t("common.loading")} />
      )}
    </>
  )
}
