"use client"

import {
  useCallback,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react"
import {
  AnimatePresence,
  LayoutGroup,
  motion,
  useReducedMotion,
} from "motion/react"
import { useTranslation } from "react-i18next"
import { Cpu, PanelsTopLeft, Share2, Zap } from "lucide-react"

import { cn } from "@/lib/utils"
import type { CreditTopupRequest } from "@/lib/credits"
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog"
import { AssistantSection } from "@/components/settings/AssistantSection"
import { ChannelsSection } from "@/components/settings/ChannelsSection"
import { CreditsSection } from "@/components/settings/CreditsSection"
import { GeneralSection } from "@/components/settings/GeneralSection"
import { CreditTopupDialog } from "@/components/credits/CreditTopupDialog"
import {
  SettingsDialogContext,
  type CheckoutReturn,
  type SettingsSectionId,
} from "@/components/settings/settings-dialog-context"

/** Settings as a shared DIALOG, never a page: one continuous surface with a
 * subtle aside divider, then one scrolling pane whose header and section share
 * a vertical rhythm. The same root also hosts the short credit top-up path. */

interface SettingsSectionDef {
  id: SettingsSectionId
  icon: typeof Share2
  labelKey: string
  descriptionKey: string
  render: () => ReactNode
}

const SECTIONS: SettingsSectionDef[] = [
  {
    id: "channels",
    icon: Share2,
    labelKey: "channels.title",
    descriptionKey: "channels.subtitle",
    render: () => <ChannelsSection />,
  },
  {
    id: "general",
    icon: PanelsTopLeft,
    labelKey: "general.title",
    descriptionKey: "general.subtitle",
    render: () => <GeneralSection />,
  },
  {
    id: "assistant",
    icon: Cpu,
    labelKey: "assistant.title",
    descriptionKey: "assistant.subtitle",
    render: () => <AssistantSection />,
  },
  {
    id: "credits",
    icon: Zap,
    labelKey: "credits.title",
    descriptionKey: "credits.subtitle",
    render: () => <CreditsSection />,
  },
]

export function SettingsDialogProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [section, setSection] = useState<SettingsSectionId>("channels")
  const [checkoutReturn, setCheckoutReturn] = useState<CheckoutReturn | null>(null)
  const [topupOpen, setTopupOpen] = useState(false)
  const [topupRequest, setTopupRequest] = useState<CreditTopupRequest | null>(null)

  const openSettings = useCallback(
    (s: SettingsSectionId = "channels", checkout?: CheckoutReturn) => {
      setSection(s)
      setCheckoutReturn(checkout ?? null)
      setTopupOpen(false)
      setTopupRequest(null)
      setOpen(true)
    },
    [],
  )
  const openCreditTopup = useCallback((shortfall?: CreditTopupRequest) => {
    setTopupRequest(shortfall ?? null)
    setTopupOpen(true)
  }, [])
  const closeCreditTopup = useCallback(() => {
    setTopupOpen(false)
    setTopupRequest(null)
  }, [])
  const clearCheckoutReturn = useCallback(() => setCheckoutReturn(null), [])
  const onOpenChange = useCallback((next: boolean) => {
    setOpen(next)
    if (!next) setCheckoutReturn(null)
  }, [])

  const handle = useMemo(
    () => ({ openSettings, openCreditTopup, checkoutReturn, clearCheckoutReturn }),
    [openSettings, openCreditTopup, checkoutReturn, clearCheckoutReturn],
  )

  return (
    <SettingsDialogContext.Provider value={handle}>
      {children}
      <SettingsDialog
        open={open}
        onOpenChange={onOpenChange}
        section={section}
        onSectionChange={setSection}
      />
      <CreditTopupDialog
        open={topupOpen}
        shortfall={topupRequest}
        onClose={closeCreditTopup}
      />
    </SettingsDialogContext.Provider>
  )
}

function SettingsDialog({
  open,
  onOpenChange,
  section,
  onSectionChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  section: SettingsSectionId
  onSectionChange: (section: SettingsSectionId) => void
}) {
  const { t } = useTranslation()
  const reduce = useReducedMotion()
  const headingId = useId()
  const scroller = useRef<HTMLDivElement>(null)
  const navButtons = useRef<(HTMLButtonElement | null)[]>([])
  const active = SECTIONS.find((s) => s.id === section) ?? SECTIONS[0]

  const onNavKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const steps: Record<string, number> = {
      ArrowDown: 1,
      ArrowRight: 1,
      ArrowUp: -1,
      ArrowLeft: -1,
    }
    const next = event.key in steps
      ? (index + steps[event.key] + SECTIONS.length) % SECTIONS.length
      : event.key === "Home"
        ? 0
        : event.key === "End"
          ? SECTIONS.length - 1
          : -1
    if (next < 0) return
    event.preventDefault()
    navButtons.current[next]?.focus()
    onSectionChange(SECTIONS[next].id)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[min(680px,88svh)] gap-0 overflow-hidden p-0 sm:max-w-4xl">
        <DialogTitle className="sr-only">{t("settings.title")}</DialogTitle>
        <div className="flex h-full min-h-0">
          <aside className="flex w-12 flex-none flex-col border-r border-subtle p-2 sm:w-60 sm:p-4">
            <p className="hidden px-2 pb-5 pt-1 text-xl font-semibold sm:block">
              {t("settings.title")}
            </p>
            <nav aria-label={t("settings.title")}>
              <LayoutGroup id="settings-dialog-sections">
                <ul className="flex flex-col gap-1">
                  {SECTIONS.map((s, index) => (
                    <li key={s.id}>
                      <button
                        ref={(node) => { navButtons.current[index] = node }}
                        type="button"
                        onClick={() => onSectionChange(s.id)}
                        onKeyDown={(event) => onNavKey(event, index)}
                        title={t(s.labelKey)}
                        aria-current={s.id === active.id ? "page" : undefined}
                        className={cn(
                          "relative flex h-10 w-full items-center justify-center gap-2 rounded-md px-2.5 text-sm transition-colors hover:bg-accent hover:text-foreground sm:justify-start",
                          s.id === active.id
                            ? "text-foreground"
                            : "text-muted-foreground",
                        )}
                      >
                        {s.id === active.id && (
                          <motion.span
                            layoutId="settings-section-highlight"
                            className="absolute inset-0 rounded-md bg-accent"
                            transition={{ duration: reduce ? 0 : 0.18 }}
                            aria-hidden="true"
                          />
                        )}
                        <s.icon className="relative z-10 h-4.5 w-4.5" />
                        <span className="relative z-10 hidden sm:inline">
                          {t(s.labelKey)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </LayoutGroup>
            </nav>
          </aside>

          <div
            ref={scroller}
            role="region"
            aria-labelledby={headingId}
            className="min-w-0 flex-1 overflow-y-auto thin-scroll"
          >
            <AnimatePresence
              mode="wait"
              initial={false}
              onExitComplete={() => scroller.current?.scrollTo({ top: 0 })}
            >
              <motion.div
                key={active.id}
                className="flex flex-col gap-6 p-5 sm:p-8"
                initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
                transition={{ duration: reduce ? 0 : 0.16 }}
              >
                <header className="pr-8">
                  <h3 id={headingId} className="text-xl font-semibold">
                    {t(active.labelKey)}
                  </h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                    {t(active.descriptionKey)}
                  </p>
                </header>
                {open ? active.render() : null}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
