import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"

export type ResultsTab = "clips" | "linkedin" | "quotes" | "summary"

interface ResultsTabsProps {
  active: ResultsTab
  onChange: (tab: ResultsTab) => void
  counts: Record<ResultsTab, number>
}

const TABS: { key: ResultsTab; labelKey: string }[] = [
  { key: "clips", labelKey: "results.tabs.clips" },
  { key: "linkedin", labelKey: "results.tabs.linkedin" },
  { key: "quotes", labelKey: "results.tabs.quotes" },
  { key: "summary", labelKey: "results.tabs.summary" },
]

export function ResultsTabs({ active, onChange, counts }: ResultsTabsProps) {
  const { t } = useTranslation()

  return (
    <div className="flex items-center gap-1">
      {TABS.map((tab) => {
        const isActive = active === tab.key
        return (
          <Button
            key={tab.key}
            variant={isActive ? "secondary" : "ghost"}
            size="sm"
            onClick={() => onChange(tab.key)}
            className="h-8"
          >
            {t(tab.labelKey)}
            {counts[tab.key] > 0 && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                {counts[tab.key]}
              </span>
            )}
          </Button>
        )
      })}
    </div>
  )
}
