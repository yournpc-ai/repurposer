"use client"

import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { AudioLines, Captions, Music, PenLine } from "lucide-react"

import { cn } from "@/lib/utils"
import { Switch } from "@/components/ui/switch"
import { Checkbox } from "@/components/ui/checkbox"

/** Models panel — the frosted Popover the Models button opens. The HONEST
 * Auto informational panel (user-ruled 2026-08-30, superseding the
 * 2026-08-22 "no model control" retirement for this read-only form),
 * Lovart anatomy: title + full-ON Auto switch, a TABS row that is an
 * ANCHOR NAV (not a filter — each tab smooth-scrolls the single scroll
 * region below to its modality group, and the active tab follows scroll),
 * then one scroll region with a group per modality: section label + the
 * model row (bare icon + semibold model name + muted what-it-does desc +
 * right checkbox). The Auto switch and every row's checkbox are locked ON
 * via `readOnly` (not `disabled` — keeps the dark fill): "Auto picks among
 * these models" is a fact displayed, not a control. Every group is the
 * pipeline's REAL assignment — no selectable rows, no badges, no timer
 * chips: each modality has exactly one provider today, so there is nothing
 * to choose and no tier/latency data to show. A picker lands only when a
 * real second provider exists, and then as a policy switch, not a model
 * SKU shelf. */
const GROUPS = [
  { key: "copy", icon: PenLine },
  { key: "voice", icon: AudioLines },
  { key: "captions", icon: Captions },
  { key: "music", icon: Music },
] as const

type GroupKey = (typeof GROUPS)[number]["key"]

/** The scroll region is deliberately capped so the four groups genuinely
 * overflow — the anchor tabs stay meaningful (Lovart shows ~1.5 groups). */
const SCROLL_MAX_H = 232

export function ModelsPanel() {
  const { t } = useTranslation()
  const scrollRef = useRef<HTMLDivElement>(null)
  const groupRefs = useRef<Partial<Record<GroupKey, HTMLDivElement>>>({})
  const [active, setActive] = useState<GroupKey>("copy")

  const scrollToGroup = (key: GroupKey) => {
    const container = scrollRef.current
    const group = groupRefs.current[key]
    if (!container || !group) return
    setActive(key)
    container.scrollTo({ top: group.offsetTop - 4, behavior: "smooth" })
  }

  /** Scrollspy: the active tab is the last group whose top has scrolled
   * past the region's top edge. */
  const handleScroll = () => {
    const container = scrollRef.current
    if (!container) return
    const top = container.scrollTop + 12
    let current: GroupKey = GROUPS[0].key
    for (const { key } of GROUPS) {
      const group = groupRefs.current[key]
      if (group && group.offsetTop <= top) current = key
    }
    setActive(current)
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-1.5 pb-2 pt-0.5">
        <span className="text-[15px] font-semibold">{t("composer.models")}</span>
        {/* Locked ON, full opacity: `readOnly` (not `disabled`) keeps the
            dark checked track — Auto is a fact displayed, not a control. */}
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          {t("composer.autoGenerate")}
          <Switch checked readOnly aria-label={t("composer.autoGenerate")} />
        </span>
      </div>

      {/* Anchor tabs — the shared segmented recipe (bg-inset track +
          bg-card thumb), each tab scrolls the region to its group. */}
      <div className="mx-1.5 mb-1 flex rounded-lg bg-inset p-0.5">
        {GROUPS.map(({ key }) => (
          <button
            key={key}
            type="button"
            onClick={() => scrollToGroup(key)}
            className={cn(
              "flex-1 rounded-md py-1.5 text-center text-xs transition-colors",
              active === key
                ? "bg-card text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t(`composer.modelsRows.${key}`)}
          </button>
        ))}
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="relative overflow-y-auto no-scrollbar"
        style={{ maxHeight: SCROLL_MAX_H }}
      >
        {GROUPS.map(({ key, icon: Icon }) => (
          <div
            key={key}
            ref={(el) => {
              if (el) groupRefs.current[key] = el
            }}
            className="px-1.5 pb-4 pt-2"
          >
            <p className="text-xs text-muted-foreground">
              {t(`composer.modelsRows.${key}`)}
            </p>
            <div className="mt-1.5 flex items-start gap-3">
              <Icon className="mt-0.5 h-4.5 w-4.5 flex-none text-foreground" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-foreground">
                  {t(`composer.modelsNames.${key}`)}
                </span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  {t(`composer.modelsDescs.${key}`)}
                </span>
              </span>
              {/* Locked ON like the Auto switch: `readOnly` (not `disabled`)
                  keeps the dark checked fill — "this model is in the Auto
                  pool" is a fact displayed, not a control. */}
              <Checkbox
                checked
                readOnly
                aria-label={t(`composer.modelsNames.${key}`)}
                className="mt-1.5"
              />
            </div>
          </div>
        ))}
        {/* Bottom spacer so the LAST group can also anchor to the region's
            top (otherwise max-scroll clamps and the tab can't follow). */}
        <div aria-hidden style={{ height: SCROLL_MAX_H - 92 }} />
      </div>
    </div>
  )
}
