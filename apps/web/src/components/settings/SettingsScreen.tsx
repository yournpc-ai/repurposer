import { useRef, useLayoutEffect } from "react"
import { useTranslation } from "react-i18next"
import {
  CreditCardIcon,
  Notification01Icon,
  Share01Icon,
  Shield01Icon,
  SlidersHorizontalIcon,
  UserIcon,
} from "@hugeicons/core-free-icons"
import { AppShell } from "@/components/ui/app-shell"
import { Button } from "@/components/ui/button-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { useAccountSettings } from "./account-settings-context"
import { ProfileSection } from "./ProfileSection"
import { PreferencesSection } from "./PreferencesSection"
import { NotificationsSection, SessionsSection } from "./AccountActivity"
import { ChannelsSection } from "./ChannelsSection"
import { CreditsSection } from "./CreditsSection"
import type { SettingsSectionId } from "./settings-dialog-context"

const sections = {
  profile: {
    title: "settings.profile",
    subtitle: "settings.profileDescription",
    icon: UserIcon,
    body: ProfileSection,
  },
  personal: {
    title: "common.preferences",
    subtitle: "settings.preferencesDescription",
    icon: SlidersHorizontalIcon,
    body: PreferencesSection,
  },
  notifications: {
    title: "settings.notifications",
    subtitle: "settings.notificationDescription",
    icon: Notification01Icon,
    body: NotificationsSection,
  },
  security: {
    title: "settings.security",
    subtitle: "settings.securityDescription",
    icon: Shield01Icon,
    body: SessionsSection,
  },
  channels: {
    title: "channels.title",
    subtitle: "channels.subtitle",
    icon: Share01Icon,
    body: ChannelsSection,
  },
  credits: {
    title: "credits.title",
    subtitle: "credits.subtitle",
    icon: CreditCardIcon,
    body: CreditsSection,
  },
} as const

const groups = [
  { title: "settings.personalGroup", ids: ["profile", "personal", "notifications", "security"] },
  { title: "settings.studioGroup", ids: ["channels", "credits"] },
] as const

export default function SettingsScreen({
  section,
  onSectionChange,
}: {
  section: SettingsSectionId
  onSectionChange: (section: SettingsSectionId) => void
}) {
  const { t } = useTranslation()
  const { data, failed, reload } = useAccountSettings()
  const page = useRef<HTMLDivElement>(null)
  const active = sections[section]
  const Body = active.body
  const navGroups = groups.map((group) => ({
    label: t(group.title),
    items: group.ids.map((id) => ({ id, label: t(sections[id].title), icon: sections[id].icon })),
  }))
  useLayoutEffect(() => {
    page.current?.closest("main")?.scrollTo({ top: 0 })
  }, [section])
  return (
    <AppShell
      nav={[]}
      groups={navGroups}
      layout="flat"
      className="settings-shell"
      projects={[]}
      setup={[]}
      dialogSidebarTitle={t("settings.title")}
      active={t(active.title)}
      sidebarWidth={{ default: 220, min: 180, max: 300 }}
      labels={{
        empty: t("settings.searchEmpty"),
        navigateHint: t("settings.navigateHint"),
        openHint: t("settings.openHint"),
        search: t("settings.searchSections"),
        navigate: t("settings.title"),
        open: t("a11y.openSidebar"),
        close: t("a11y.closeSidebar"),
        collapse: t("a11y.toggleSidebar"),
        expand: t("a11y.openSidebar"),
        resize: t("settings.resizeSidebar"),
      }}
      onNavigate={(label) => {
        const item = navGroups.flatMap((group) => group.items).find((item) => item.label === label)
        if (item) onSectionChange(item.id)
      }}
    >
      <div ref={page} className="ui-au-shell-page settings-page" key={section}>
        <header className="settings-intro">
          <h3 className="ui-au-shell-page-title">{t(active.title)}</h3>
          <p className="ui-au-shell-page-sub">{t(active.subtitle)}</p>
        </header>
        {section === "notifications" && !data ? (
          failed ? (
            <Button size="sm" variant="secondary" onClick={reload}>
              {t("credits.retry")}
            </Button>
          ) : (
            <Spinner label={t("common.loading")} />
          )
        ) : (
          <Body />
        )}
      </div>
    </AppShell>
  )
}
