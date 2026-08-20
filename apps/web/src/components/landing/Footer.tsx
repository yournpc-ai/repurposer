import { useTranslation } from "react-i18next"
import type { ReactNode } from "react"

import { LogoMark } from "@/components/LogoMark"

/**
 * Landing footer: link columns + oversized clipped wordmark, ported from the
 * template. Column link targets are in-page anchors for now; legal/social
 * routes land with their pages.
 */

type FooterLink = { labelKey: string; href: string }

export function Footer(): ReactNode {
  const { t } = useTranslation()

  const columns: { titleKey: string; links: FooterLink[] }[] = [
    {
      titleKey: "landing.footer.columns.features.title",
      links: [
        { labelKey: "landing.footer.columns.features.l1", href: "#features" },
        { labelKey: "landing.footer.columns.features.l2", href: "#how-it-works" },
        { labelKey: "landing.footer.columns.features.l4", href: "#pricing" },
        { labelKey: "landing.footer.columns.features.l5", href: "#faq" },
      ],
    },
    // Company / legal / social columns hidden until their pages exist —
    // every href was a dead anchor, and dead legal links sit next to the
    // page's GDPR-ready claims (legal pages land with the 法务 week).
    // Restore from git history with the routes.
  ]

  return (
    <footer className="border-t border-border">
      <div className="mx-auto max-w-[1440px] px-5 pt-16 sm:px-8 sm:pt-20 lg:px-10">
        <div className="flex flex-col gap-14 lg:flex-row lg:justify-between">
          <div className="max-w-xs">
            <span className="flex items-center gap-2">
              <LogoMark />
              <span className="font-semibold tracking-tight">Repurposer</span>
            </span>
            <p className="mt-6 text-sm leading-relaxed text-muted-foreground">
              {t("landing.footer.tagline")}
            </p>
            <a
              href="#sign-up"
              className="mt-8 inline-flex h-11 items-center rounded-full bg-foreground px-6 text-sm font-medium text-background transition-opacity hover:opacity-85"
            >
              {t("landing.footer.cta")}
            </a>
          </div>

          <div className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-4 lg:gap-x-16">
            {columns.map((column) => (
              <div key={column.titleKey}>
                <h3 className="text-sm font-medium tracking-tight text-foreground">
                  {t(column.titleKey)}
                </h3>
                <ul className="mt-4 space-y-3">
                  {column.links.map((link) => (
                    <li key={link.href}>
                      <a
                        href={link.href}
                        className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {t(link.labelKey)}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-16 flex flex-col-reverse items-start justify-between gap-4 pt-6 sm:flex-row sm:items-center">
          <p className="text-xs text-muted-foreground">
            {t("landing.footer.copyright", { year: new Date().getFullYear() })}
          </p>
          <p className="text-xs text-muted-foreground">{t("landing.footer.note")}</p>
        </div>

        <div
          aria-hidden="true"
          className="pointer-events-none overflow-hidden select-none"
        >
          <p className="translate-y-[22%] text-center font-display text-[clamp(70px,17vw,240px)] leading-[0.85] font-medium tracking-tighter text-muted">
            {t("landing.footer.wordmark")}
          </p>
        </div>
      </div>
    </footer>
  )
}
