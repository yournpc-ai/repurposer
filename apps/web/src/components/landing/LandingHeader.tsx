import { Link } from "@tanstack/react-router"
import { ArrowRight, ChevronDown } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { createPortal } from "react-dom"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/components/AuthProvider"
import { LanguageSwitcher } from "@/components/language-switcher"
import { useReducedMotion } from "@/components/landing/motion"
import { LogoMark } from "@/components/LogoMark"
import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"

/**
 * Hover mega-menu pattern adapted from the finance reference header:
 * portal-mounted panel positioned under the trigger, 100ms close delay so
 * the pointer can cross the gap, chevron rotation, shared open state at the
 * header level for smooth cross-item travel. Styled to our conventions:
 * overlay-surface (no border), rounded-lg panel, regular-weight triggers.
 */
const MENU_EASE = [0.23, 1, 0.32, 1] as const

type NavMenu = {
  items: { key: string; href: string }[]
  promo?: { href: string }
}

type NavEntry = {
  id: string
  labelKey: string
  menu?: NavMenu
}

const NAV_ITEMS: NavEntry[] = [
  {
    id: "features",
    labelKey: "landing.nav.features",
    menu: {
      items: [
        { key: "clips", href: "#features" },
        { key: "languages", href: "#channels" },
      ],
      promo: { href: "#how-it-works" },
    },
  },
  { id: "pricing", labelKey: "landing.nav.pricing" },
  {
    id: "faq",
    labelKey: "landing.nav.faq",
    menu: {
      items: [
        { key: "data", href: "#faq" },
        { key: "upload", href: "#faq" },
        { key: "languages", href: "#faq" },
        { key: "autoPublish", href: "#faq" },
      ],
    },
  },
]

function NavDropdown({
  id,
  labelKey,
  menu,
  isOpen,
  onOpen,
  onClose,
  onSelect,
}: {
  id: string
  labelKey: string
  menu: NavMenu
  isOpen: boolean
  onOpen: () => void
  onClose: () => void
  onSelect: () => void
}): ReactNode {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const triggerRef = useRef<HTMLAnchorElement>(null)
  const [position, setPosition] = useState<{ top: number; left: number } | null>(
    null
  )

  useLayoutEffect(() => {
    if (isOpen && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      setPosition({ top: rect.bottom, left: rect.left + rect.width / 2 })
    } else if (!isOpen) {
      setPosition(null)
    }
  }, [isOpen])

  const hidden = prefersReducedMotion
    ? { opacity: 0 }
    : { opacity: 0, y: 8, scale: 0.96 }
  const shown = prefersReducedMotion
    ? { opacity: 1 }
    : { opacity: 1, y: 0, scale: 1 }

  return (
    <div onMouseEnter={onOpen} onMouseLeave={onClose}>
      <a
        ref={triggerRef}
        href={`#${id}`}
        className="inline-flex h-9 items-center gap-1 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        {t(labelKey)}
        <motion.span
          className="inline-flex"
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2, ease: MENU_EASE }}
        >
          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
        </motion.span>
      </a>
      {typeof window !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {isOpen && position && (
              <div
                className="fixed z-[100] pt-2"
                style={{
                  top: position.top,
                  left: position.left,
                  transform: "translateX(-50%)",
                }}
                onMouseEnter={onOpen}
                onMouseLeave={onClose}
              >
                <motion.div
                  initial={hidden}
                  animate={shown}
                  exit={hidden}
                  transition={{ duration: 0.2, ease: MENU_EASE }}
                  className="overlay-surface flex items-stretch gap-2 overflow-hidden rounded-lg p-2 shadow-lg"
                >
                  <div className="min-w-64">
                    {menu.items.map((item) => (
                      <a
                        key={item.key}
                        href={item.href}
                        onClick={onSelect}
                        className="block rounded-md px-4 py-3 transition-colors hover:bg-muted"
                      >
                        <div className="text-sm text-foreground">
                          {t(`landing.nav.menus.${id}.items.${item.key}.label`)}
                        </div>
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {t(
                            `landing.nav.menus.${id}.items.${item.key}.description`
                          )}
                        </div>
                      </a>
                    ))}
                  </div>
                  {menu.promo && (
                    <a
                      href={menu.promo.href}
                      onClick={onSelect}
                      className="group flex w-52 flex-col justify-between rounded-md bg-muted p-4"
                    >
                      <div>
                        <h3 className="text-sm font-semibold">
                          {t(`landing.nav.menus.${id}.promo.title`)}
                        </h3>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                          {t(`landing.nav.menus.${id}.promo.description`)}
                        </p>
                      </div>
                      <div className="mt-4 flex justify-start">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-background transition-colors group-hover:bg-background/70">
                          <ArrowRight className="h-4 w-4" aria-hidden="true" />
                        </div>
                      </div>
                    </a>
                  )}
                </motion.div>
              </div>
            )}
          </AnimatePresence>,
          document.body
        )}
    </div>
  )
}

export function LandingHeader() {
  const { t } = useTranslation()
  const { isAuthenticated, setLoginOpen } = useAuth()
  const [activeMenu, setActiveMenu] = useState<string | null>(null)
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const openMenu = (id: string) => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current)
      closeTimeoutRef.current = null
    }
    setActiveMenu(id)
  }

  const scheduleClose = () => {
    closeTimeoutRef.current = setTimeout(() => setActiveMenu(null), 100)
  }

  const closeNow = () => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current)
      closeTimeoutRef.current = null
    }
    setActiveMenu(null)
  }

  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) clearTimeout(closeTimeoutRef.current)
    }
  }, [])

  return (
    <header className="sticky top-0 z-50 backdrop-blur-md">
      {/* Equal flex-1 side slots keep the nav optically centered — no
          absolute left-1/2 hack, so centering holds at any content width. */}
      <div className="mx-auto flex h-16 w-full max-w-[1440px] items-center px-5 sm:px-8 lg:px-10">
        <div className="flex flex-1 items-center">
          <a href="#top" className="flex items-center gap-2">
            <LogoMark />
            <span className="font-semibold tracking-tight">Repurposer</span>
          </a>
        </div>

        <nav className="hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map((item) =>
            item.menu ? (
              <NavDropdown
                key={item.id}
                id={item.id}
                labelKey={item.labelKey}
                menu={item.menu}
                isOpen={activeMenu === item.id}
                onOpen={() => openMenu(item.id)}
                onClose={scheduleClose}
                onSelect={closeNow}
              />
            ) : (
              <a
                key={item.id}
                href={`#${item.id}`}
                className="inline-flex h-9 items-center rounded-md px-3 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {t(item.labelKey)}
              </a>
            )
          )}
        </nav>

        <div className="flex flex-1 items-center justify-end gap-2">
          <ThemeToggle />
          <LanguageSwitcher />
          {isAuthenticated ? (
            <Button render={<Link to="/home" />}>{t("landing.openStudio")}</Button>
          ) : (
            <Button onClick={() => setLoginOpen(true)}>{t("landing.signIn")}</Button>
          )}
        </div>
      </div>
    </header>
  )
}
