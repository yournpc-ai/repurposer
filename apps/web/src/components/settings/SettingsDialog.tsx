"use client"

import { useCallback, useId, useMemo, useRef, useState, type ReactNode } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useTranslation } from "react-i18next"
import { Cpu, Share2, Zap } from "lucide-react"

import { SegmentedControl } from "@/components/ui/segmented-control-clean"
import type { CreditTopupRequest } from "@/lib/credits"
import { Dialog } from "@/components/ui/dialog-clean"
import { AssistantSection } from "@/components/settings/AssistantSection"
import { ChannelsSection } from "@/components/settings/ChannelsSection"
import { CreditsSection } from "@/components/settings/CreditsSection"
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

  const openSettings = useCallback((s: SettingsSectionId = "channels", checkout?: CheckoutReturn) => {
    setSection(s)
    setCheckoutReturn(checkout ?? null)
    setTopupOpen(false)
    setTopupRequest(null)
    setOpen(true)
  }, [])
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
    () => ({ modalOpen: open || topupOpen, openSettings, openCreditTopup, checkoutReturn, clearCheckoutReturn }),
    [open, topupOpen, openSettings, openCreditTopup, checkoutReturn, clearCheckoutReturn],
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
      <CreditTopupDialog open={topupOpen} shortfall={topupRequest} onClose={closeCreditTopup} />
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
  const active = SECTIONS.find((s) => s.id === section) ?? SECTIONS[0]

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("settings.title")}
      closeLabel={t("common.close")}
      width="58rem"
    >
      <div className="flex h-[min(540px,65dvh)] min-h-0 flex-col gap-4">
        <SegmentedControl
          kind="tabs"
          value={section}
          onChange={onSectionChange}
          aria-label={t("settings.title")}
          options={SECTIONS.map(({ id, icon: Icon, labelKey }) => ({
            value: id,
            icon: <Icon size={16} />,
            label: t(labelKey),
            controls: headingId + "-" + id,
          }))}
        />

        <div
          ref={scroller}
          role="tabpanel"
          id={headingId + "-" + section}
          aria-labelledby={headingId}
          className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto thin-scroll"
        >
          <AnimatePresence
            mode="wait"
            initial={false}
            onExitComplete={() => scroller.current?.scrollTo({ top: 0 })}
          >
            <motion.div
              key={active.id}
              className="flex min-w-0 flex-col gap-6 p-5 sm:p-8"
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
    </Dialog>
  )
}
