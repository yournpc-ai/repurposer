import { useTranslation } from "react-i18next"
import { LEGAL_LINKS, SOCIAL_CHANNELS } from "./content"
import { LANDING_CONTAINER } from "./layout"
import { LogoMark } from "@/components/LogoMark"

type Entry = { label: string; href?: string; external?: boolean }

export function Footer() {
  const { t } = useTranslation()
  const company: Entry[] = [
    { label: t("landing.footerItems.pricing"), href: "#pricing" },
    { label: t("landing.footerItems.changelog") },
    { label: t("landing.footerItems.terms"), href: LEGAL_LINKS.terms || undefined },
    { label: t("landing.footerItems.privacy"), href: LEGAL_LINKS.privacy || undefined },
  ]
  const social: Entry[] = [
    { label: "X", href: SOCIAL_CHANNELS.x || undefined, external: true },
    { label: "Discord", href: SOCIAL_CHANNELS.discord || undefined, external: true },
    { label: "TikTok" },
  ]
  return <footer className="pt-24 pb-8 sm:pt-32 sm:pb-10">
    <div className={LANDING_CONTAINER}>
      <div className="grid gap-14 md:grid-cols-[1fr_1fr] md:gap-10">
        <div className="self-start">
          <a href="#top" className="inline-flex w-fit items-center gap-2 text-xl font-semibold tracking-tight"><LogoMark className="size-6" />Rookie Cut</a>
          <p className="mt-6 max-w-xs text-sm leading-6 text-muted-foreground sm:text-base">{t("landing.heroTitle1")}</p>
        </div>
        <div className="grid grid-cols-2 gap-5 sm:gap-10">
          {([['company', company], ['social', social]] as const).map(([key, entries]) => <div key={key}>
            <h3 className="text-sm font-normal text-meta-foreground sm:text-base">{t(`landing.footer.columns.${key}`)}</h3>
            <ul className="mt-5 space-y-3 sm:mt-6 sm:space-y-4">
              {entries.map((entry) => <li key={entry.label} className="text-sm leading-6 sm:text-base">
                {entry.href ? <a href={entry.href} target={entry.external ? "_blank" : undefined} rel={entry.external ? "noopener noreferrer" : undefined} className="transition-colors hover:text-muted-foreground">{entry.label}</a> : <span>{entry.label}</span>}
              </li>)}
            </ul>
          </div>)}
        </div>
      </div>
      <p className="mt-24 text-sm text-meta-foreground sm:mt-28">{t("landing.footer.copyright", { year: new Date().getFullYear() })}</p>
    </div>
  </footer>
}
