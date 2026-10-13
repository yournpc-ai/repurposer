"use client"

import { useTranslation } from "react-i18next"

import type { ResolvedFamily } from "./recipeFamilies"

/**
 * 两级 tab (D5, prototype 屏①): 一级 = family pill 轨 (stadium pills on a
 * muted track — the rounded-full law's gallery-pill exception register;
 * active = solid foreground pill, inactive = quiet text, hover bg-accent),
 * 二级 = 下划线文本 tab (2px foreground indicator under the active label).
 *
 * The component is fully controlled — the route owns the selection
 * (active family + per-family sub memory, prototype parity) so the shelf
 * section below reads the same pair. A family with a SINGLE sub skips the
 * subrow entirely: an underline communicates selection among siblings, and
 * with one sibling it is pure noise.
 */
export function RecipeTabs({
  families,
  activeFamilyId,
  activeSubId,
  onSelectFamily,
  onSelectSub,
}: {
  families: ResolvedFamily[]
  activeFamilyId: string
  activeSubId: string | null
  onSelectFamily: (familyId: string) => void
  onSelectSub: (familyId: string, subId: string) => void
}) {
  const { t } = useTranslation()
  const active = families.find((f) => f.id === activeFamilyId)

  return (
    <div className="flex flex-col items-center gap-5">
      {/* 一级 pill 轨 — the track is a recessed muted lane; pills ride it.
          Text stays regular weight (pill law — 不加粗). */}
      <div className="inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-full bg-muted p-1 no-scrollbar">
        {families.map((family) => {
          const Icon = family.icon
          const on = family.id === activeFamilyId
          return (
            <button
              key={family.id}
              type="button"
              onClick={() => onSelectFamily(family.id)}
              className={`flex h-9 flex-none items-center gap-1.5 rounded-full px-4 text-sm transition-colors ${
                on
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
            >
              {Icon && <Icon className="h-4 w-4" />}
              {t(`recipes.shelf.families.${family.id}`)}
            </button>
          )
        })}
      </div>

      {/* 二级下划线子 tab — only when the family actually has siblings to
          choose among. */}
      {active && active.subs.length > 1 && (
        <div className="flex max-w-full items-center justify-center gap-8 overflow-x-auto no-scrollbar">
          {active.subs.map((sub) => {
            const on = sub.id === activeSubId
            return (
              <button
                key={sub.id}
                type="button"
                onClick={() => onSelectSub(active.id, sub.id)}
                className={`relative flex-none pb-2 text-sm transition-colors ${
                  on ? "text-foreground" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t(`recipes.shelf.subs.${sub.id}`)}
                {on && (
                  <span className="absolute bottom-0 left-1/2 h-0.5 w-5 -translate-x-1/2 bg-foreground" />
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
