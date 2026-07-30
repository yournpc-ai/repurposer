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
      titleKey: "landing.footer.columns.product.title",
      links: [
        { labelKey: "landing.footer.columns.product.l1", href: "#product" },
        { labelKey: "landing.footer.columns.product.l2", href: "#how-it-works" },
        { labelKey: "landing.footer.columns.product.l3", href: "#gallery" },
        { labelKey: "landing.footer.columns.product.l4", href: "#pricing" },
        { labelKey: "landing.footer.columns.product.l5", href: "#faq" },
      ],
    },
    {
      titleKey: "landing.footer.columns.company.title",
      links: [
        { labelKey: "landing.footer.columns.company.l1", href: "#about" },
        { labelKey: "landing.footer.columns.company.l2", href: "#contact" },
        { labelKey: "landing.footer.columns.company.l3", href: "#press" },
      ],
    },
    {
      titleKey: "landing.footer.columns.legal.title",
      links: [
        { labelKey: "landing.footer.columns.legal.l1", href: "#privacy" },
        { labelKey: "landing.footer.columns.legal.l2", href: "#terms" },
        { labelKey: "landing.footer.columns.legal.l3", href: "#cookies" },
      ],
    },
    {
      titleKey: "landing.footer.columns.social.title",
      links: [
        { labelKey: "landing.footer.columns.social.l1", href: "#linkedin" },
        { labelKey: "landing.footer.columns.social.l2", href: "#x" },
        { labelKey: "landing.footer.columns.social.l3", href: "#youtube" },
      ],
    },
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
