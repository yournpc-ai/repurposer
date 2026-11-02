import { Link } from "@tanstack/react-router"
import { ChevronDown } from "lucide-react"
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

import { useAuth } from "@/lib/auth-context"
import { LanguageSwitcher } from "@/components/language-switcher"
import { useReducedMotion } from "@/components/landing/motion"
import { LogoMark } from "@/components/LogoMark"
import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"

const MENU_EASE = [0.23, 1, 0.32, 1] as const

type MenuId = "features" | "pricing" | "faq" | "roadmap"
type MenuItem = { key: string; marker?: string }
type NavMenu = { id: MenuId; items: MenuItem[] }

const NAV_MENUS: NavMenu[] = [
  {
    id: "features",
    items: [
      { key: "conversation" },
      { key: "animation" },
      { key: "mixedMedia" },
      { key: "revision" },
    ],
  },
  {
    id: "pricing",
    items: [
      { key: "topup" },
      { key: "balance" },
      { key: "history" },
      { key: "packages" },
    ],
  },
  {
    id: "faq",
    items: [
      { key: "inputs" },
      { key: "revision" },
      { key: "videoTypes" },
      { key: "download" },
    ],
  },
  {
    id: "roadmap",
    items: [
      { key: "a", marker: "A" },
      { key: "b", marker: "B" },
      { key: "c", marker: "C" },
      { key: "d", marker: "D" },
    ],
  },
]

function NavHoverMenu({
  id,
  items,
  isOpen,
  onOpen,
  onClose,
}: NavMenu & {
  isOpen: boolean
  onOpen: () => void
  onClose: () => void
}): ReactNode {
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  const triggerRef = useRef<HTMLButtonElement>(null)
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
  const panelId = `landing-${id}-panel`

  return (
    <div onMouseEnter={onOpen} onMouseLeave={onClose}>
      <button
        ref={triggerRef}
        type="button"
        className="inline-flex h-9 items-center gap-1 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onFocus={onOpen}
        onBlur={onClose}
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose()
        }}
      >
        {t(`landing.nav.${id}`)}
        <motion.span
          className="inline-flex"
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2, ease: MENU_EASE }}
        >
          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
        </motion.span>
      </button>
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
                  id={panelId}
                  initial={hidden}
                  animate={shown}
                  exit={hidden}
                  transition={{ duration: 0.2, ease: MENU_EASE }}
                  className="overlay-surface flex items-stretch gap-2 overflow-hidden rounded-lg p-2 shadow-lg"
                >
                  <div className="w-80">
                    {items.map((item) => (
                      <div key={item.key} className="rounded-md px-4 py-3">
                        <div className="flex items-baseline gap-2">
                          {item.marker && (
                            <span className="w-4 shrink-0 text-xs text-muted-foreground">
                              {item.marker}
                            </span>
                          )}
                          <p className="text-sm text-foreground">
                            {t(`landing.nav.menus.${id}.items.${item.key}.title`)}
                          </p>
                        </div>
                        <p
                          className={`mt-0.5 text-xs leading-relaxed text-muted-foreground ${item.marker ? "ml-6" : ""}`}
                        >
                          {t(
                            `landing.nav.menus.${id}.items.${item.key}.description`
                          )}
                        </p>
                      </div>
                    ))}
                  </div>
                  <div className="flex w-52 flex-col justify-between rounded-md bg-muted p-4">
                    <div>
                      <p className="text-xs text-muted-foreground">
                        {t(`landing.nav.menus.${id}.aside.label`)}
                      </p>
                      <h3 className="mt-1 text-sm font-semibold">
                        {t(`landing.nav.menus.${id}.aside.title`)}
                      </h3>
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                        {t(`landing.nav.menus.${id}.aside.description`)}
                      </p>
                    </div>
                    <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                      {t(`landing.nav.menus.${id}.aside.note`)}
                    </p>
                  </div>
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
  const [activeMenu, setActiveMenu] = useState<MenuId | null>(null)
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const openMenu = (id: MenuId) => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current)
      closeTimeoutRef.current = null
    }
    setActiveMenu(id)
  }

  const scheduleClose = () => {
    if (closeTimeoutRef.current) clearTimeout(closeTimeoutRef.current)
    closeTimeoutRef.current = setTimeout(() => setActiveMenu(null), 100)
  }

  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) clearTimeout(closeTimeoutRef.current)
    }
  }, [])

  return (
    <header className="relative z-50 shrink-0 backdrop-blur-md">
      {/* Equal flex-1 side slots keep the nav optically centered — no
          absolute left-1/2 hack, so centering holds at any content width. */}
      <div className="mx-auto flex min-h-16 w-full max-w-[1440px] flex-wrap items-center gap-y-1 px-5 py-2 sm:px-8 lg:px-10">
        <div className="flex flex-1 items-center">
          <a href="#top" className="flex items-center gap-2">
            <LogoMark />
            <span className="font-semibold tracking-tight">Repurposer</span>
          </a>
        </div>

        <nav
          aria-label={t("landing.entry.navigation")}
          className="hidden items-center gap-1 md:flex"
        >
          {NAV_MENUS.map((menu) => (
            <NavHoverMenu
              key={menu.id}
              {...menu}
              isOpen={activeMenu === menu.id}
              onOpen={() => openMenu(menu.id)}
              onClose={scheduleClose}
            />
          ))}
        </nav>

        <div className="flex flex-1 items-center justify-end gap-2">
          <ThemeToggle />
          <LanguageSwitcher />
          {isAuthenticated ? (
            <Button size="sm" className="h-7" render={<Link to="/home" />}>{t("landing.openStudio")}</Button>
          ) : (
            <Button size="sm" className="h-7" onClick={() => setLoginOpen(true)}>{t("landing.openStudio")}</Button>
          )}
        </div>
      </div>
    </header>
  )
}
