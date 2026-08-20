"use client"

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { useTranslation } from "react-i18next"
import { Share2 } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog"
import { ChannelsSection } from "@/components/settings/ChannelsSection"

/** Settings as a shared DIALOG, never a page (MiniMax / FLORA pattern,
 * 2026-08-21 ruling): one modal — left section nav + right content — that
 * ANY entry point summons via `useSettingsDialog().openSettings(section)`
 * (the account console's settings row today; memory / asset-center rows
 * later). The retired `/settings` page survives only as the channels OAuth
 * callback shim (it toasts, opens this dialog, and bounces home). New deep
 * surfaces register as SECTIONS entries below, never as routes. */

export type SettingsSectionId = "channels"

interface SettingsSectionDef {
  id: SettingsSectionId
  icon: typeof Share2
  labelKey: string
  render: () => ReactNode
}

const SECTIONS: SettingsSectionDef[] = [
  {
    id: "channels",
    icon: Share2,
    labelKey: "channels.title",
    render: () => <ChannelsSection />,
  },
]

interface SettingsDialogHandle {
  openSettings: (section?: SettingsSectionId) => void
}

const SettingsDialogContext = createContext<SettingsDialogHandle | null>(null)

export function useSettingsDialog(): SettingsDialogHandle {
  const ctx = useContext(SettingsDialogContext)
  if (!ctx)
    throw new Error("useSettingsDialog must be used within SettingsDialogProvider")
  return ctx
}

export function SettingsDialogProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [section, setSection] = useState<SettingsSectionId>("channels")

  const openSettings = useCallback((s: SettingsSectionId = "channels") => {
    setSection(s)
    setOpen(true)
  }, [])

  const handle = useMemo(() => ({ openSettings }), [openSettings])

  return (
    <SettingsDialogContext.Provider value={handle}>
      {children}
      <SettingsDialog
        open={open}
        onOpenChange={setOpen}
        section={section}
        onSectionChange={setSection}
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
  const active = SECTIONS.find((s) => s.id === section) ?? SECTIONS[0]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Frosted overlay chrome is baked into DialogContent (overlay-surface).
          Fixed height with one internal scrollport (the content column) —
          the nav never scrolls. */}
      <DialogContent className="h-[min(600px,85svh)] gap-0 overflow-hidden p-0 sm:max-w-3xl">
        {/* a11y: the dialog's accessible name (the visual header below is the
            same copy, so this stays visually hidden). */}
        <DialogTitle className="sr-only">{t("settings.title")}</DialogTitle>
        <div className="flex h-full min-h-0">
          {/* Left section nav (hidden on mobile until a second section lands —
              a one-item rail is chrome, not navigation). Selected = the nav
              law: accent fill + foreground text. */}
          <nav className="hidden w-48 flex-none flex-col gap-0.5 p-3 sm:flex">
            <p className="px-2 pb-2 text-sm font-semibold">{t("settings.title")}</p>
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => onSectionChange(s.id)}
                className={cn(
                  "flex h-9 items-center gap-2 rounded-md px-2 text-xs transition-colors",
                  s.id === active.id
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <s.icon className="h-4 w-4" />
                {t(s.labelKey)}
              </button>
            ))}
          </nav>

          {/* Right content: section title header (clear of the × at
              top-right) + the only scrollport. */}
          <div className="flex min-w-0 flex-1 flex-col">
            <p className="px-5 pt-4 pb-1 pr-10 text-sm font-semibold">
              {t(active.labelKey)}
            </p>
            <div className="min-h-0 flex-1 overflow-y-auto p-5 pt-2">
              {open ? active.render() : null}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
