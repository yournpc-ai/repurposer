import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"

export type ResultsTab =
  | "clips"
  | "linkedin"
  | "quotes"
  | "carousel"
  | "summary"
  | "blog"

interface ResultsTabsProps {
  active: ResultsTab
  onChange: (tab: ResultsTab) => void
  counts: Partial<Record<ResultsTab, number>>
  visible?: ResultsTab[]
  running?: ResultsTab[]
  failed?: ResultsTab[]
}

const TABS: { key: ResultsTab; labelKey: string }[] = [
  { key: "clips", labelKey: "results.tabs.clips" },
  { key: "linkedin", labelKey: "results.tabs.linkedin" },
  { key: "quotes", labelKey: "results.tabs.quotes" },
  { key: "carousel", labelKey: "results.tabs.carousel" },
  { key: "summary", labelKey: "results.tabs.summary" },
  { key: "blog", labelKey: "results.tabs.blog" },
]

export function ResultsTabs({
  active,
  onChange,
  counts,
  visible,
  running = [],
  failed = [],
}: ResultsTabsProps) {
  const { t } = useTranslation()

  const visibleTabs = visible
    ? TABS.filter((tab) => visible.includes(tab.key))
    : TABS

  return (
    <div className="flex flex-wrap items-center gap-1">
      {visibleTabs.map((tab) => {
        const isActive = active === tab.key
        const count = counts[tab.key] ?? 0
        const isRunning = running.includes(tab.key)
        const isFailed = failed.includes(tab.key)
        return (
          <Button
            key={tab.key}
            variant={isActive ? "secondary" : "ghost"}
            size="sm"
            onClick={() => onChange(tab.key)}
            className="h-8"
          >
            {t(tab.labelKey)}
            {count > 0 && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                {count}
              </span>
            )}
            {isRunning && !isFailed && (
              <span className="ml-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
            )}
            {isFailed && (
              <span className="ml-1.5 h-1.5 w-1.5 rounded-full bg-destructive" />
            )}
          </Button>
        )
      })}
    </div>
  )
}
