"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { Clapperboard, Film, Layers } from "@/components/ui/icons"
import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge-clean"
import { Card } from "@/components/ui/card-clean"
import { Loading, Skeleton } from "@/components/ui/skeleton-clean"
import {
  fetchChatSkills,
  filterSkillOptions,
  skillDisplayName,
  type SkillOption,
} from "@/lib/skills"
import { cn } from "@/lib/utils"

function optionKey(option: SkillOption): string {
  return option.reference.kind === "builtin"
    ? `builtin:${option.reference.skill_id}:${option.reference.version}`
    : `external:${option.reference.skill_version_id}`
}

/** Caret-anchored Skill picker. Like MentionPicker, it portals to body and
 * owns Arrow/Enter/Escape in the capture phase while the editor keeps focus.
 * Renders orthogonal Creation Modes (built-in) and Templates (external) with
 * flat keyboard navigation across both sections. */
export function SkillPicker({
  query,
  position,
  onSelect,
  onClose,
  onPreviewSlotPromo,
}: {
  query: string
  position: { left: number; top: number; bottom: number }
  onSelect: (option: SkillOption) => void
  onClose: () => void
  onPreviewSlotPromo?: (option: SkillOption) => void
}) {
  const { t } = useTranslation()
  const [options, setOptions] = useState<SkillOption[]>([])
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  )
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchChatSkills(controller.signal)
      .then((response) => {
        setOptions(response.items)
        setStatus("ready")
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return
        setStatus("error")
      })
    return () => controller.abort()
  }, [])

  const { creationModes, templates, ordered } = useMemo(() => {
    const filtered = filterSkillOptions(
      options,
      query.toLowerCase() === "skill" ? "" : query,
      (option) => skillDisplayName(option, t),
    )
    const builtins = filtered.filter((o) => o.reference.kind === "builtin")
    const externals = filtered.filter((o) => o.reference.kind === "external")
    return {
      creationModes: builtins,
      templates: externals,
      ordered: [...builtins, ...externals],
    }
  }, [options, query, t])

  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  useEffect(() => {
    if (ordered.length > 0 && activeIndex >= ordered.length) {
      setActiveIndex(0)
    }
  }, [ordered.length, activeIndex])

  const navRef = useRef({ ordered, activeIndex, onSelect, onClose })
  navRef.current = { ordered, activeIndex, onSelect, onClose }

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.isComposing) return
      const current = navRef.current
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault()
        event.stopPropagation()
        if (current.ordered.length === 0) return
        setActiveIndex((previous) => {
          const delta = event.key === "ArrowDown" ? 1 : -1
          return (previous + delta + current.ordered.length) % current.ordered.length
        })
      } else if (event.key === "Enter") {
        event.preventDefault()
        event.stopPropagation()
        const picked = current.ordered[current.activeIndex]
        if (picked) current.onSelect(picked)
      } else if (event.key === "Escape") {
        event.preventDefault()
        event.stopPropagation()
        current.onClose()
      }
    }
    window.addEventListener("keydown", handler, true)
    return () => window.removeEventListener("keydown", handler, true)
  }, [])

  const spaceBelow = window.innerHeight - position.bottom
  const openAbove = spaceBelow < 368 && position.top > spaceBelow

  const renderRow = (option: SkillOption, flatIndex: number) => {
    const isExternal = option.reference.kind === "external"
    const isBlueprint =
      isExternal && option.capabilities.includes("slot_blueprint_v1")
    const summary = option.blueprint_summary
    const stylePresetKey = summary?.style_preset
      ? `skills.picker.styles.${summary.style_preset}`
      : null
    const styleLabel = stylePresetKey
      ? t(stylePresetKey, { defaultValue: summary?.style_preset ?? "" })
      : null

    return (
      <div
        key={optionKey(option)}
        onMouseEnter={() => setActiveIndex(flatIndex)}
        className={cn(
          "flex items-center gap-1 rounded-md pr-1 transition-colors",
          flatIndex === activeIndex && "bg-accent",
        )}
      >
        <button
          type="button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => onSelect(option)}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left"
        >
          {isExternal ? (
            <Layers className="size-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <Clapperboard className="size-3.5 shrink-0 text-muted-foreground" />
          )}
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5">
              <span className="truncate font-medium">
                {skillDisplayName(option, t)}
                {option.version_number != null ? ` v${option.version_number}` : ""}
              </span>
              {summary ? (
                <span className="shrink-0 text-[10px] text-muted-foreground tabular-nums">
                  {t("skills.picker.blueprintMeta", {
                    acts: summary.act_count,
                    slots: summary.slot_count,
                  })}
                </span>
              ) : null}
              {styleLabel ? (
                <Badge tone="neutral" size="sm" className="shrink-0">
                  {styleLabel}
                </Badge>
              ) : null}
            </span>
            {option.description ? (
              <span className="block truncate text-[10px] text-muted-foreground">
                {option.reference.kind === "builtin"
                  ? t(`skills.builtin.${option.reference.skill_id}.description`, {
                      defaultValue: option.description,
                    })
                  : option.description}
              </span>
            ) : null}
          </span>
        </button>
        {isBlueprint && onPreviewSlotPromo ? (
          <button
            type="button"
            aria-label={t("skills.slotPreview.openAction")}
            title={t("skills.slotPreview.openAction")}
            onMouseDown={(event) => {
              event.preventDefault()
              event.stopPropagation()
            }}
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              onPreviewSlotPromo(option)
            }}
            className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-background/80 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
          >
            <Film className="size-3.5" />
          </button>
        ) : null}
      </div>
    )
  }

  return createPortal(
    <Card
      style={{
        position: "fixed",
        width: 384,
        maxWidth: "calc(100vw - 16px)",
        left: Math.max(8, Math.min(position.left, window.innerWidth - 384 - 8)),
        top: openAbove ? position.top : position.bottom + 4,
        transform: openAbove ? "translateY(calc(-100% - 4px))" : undefined,
      }}
      className="composer-picker thin-scroll z-50 max-h-[360px] overflow-y-auto"
    >
      {status === "loading" ? (
        <Loading label={t("common.loading")} className="flex flex-col gap-2.5 p-2">
          {[148, 176, 132].map((w, idx) => (
            <div key={idx} className="flex items-center gap-2.5 px-1">
              <Skeleton width={28} height={28} radius={6} />
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <Skeleton width={w} height={10} />
                <Skeleton width={Math.round(w * 1.25)} height={8} />
              </div>
            </div>
          ))}
        </Loading>
      ) : status === "error" ? (
        <span className="px-2 py-1.5 text-muted-foreground">
          {t("common.requestFailed")}
        </span>
      ) : ordered.length === 0 ? (
        <span className="px-2 py-1.5 text-muted-foreground">
          {t("mentions.pickerEmpty")}
        </span>
      ) : (
        <div className="flex flex-col gap-1">
          {creationModes.length > 0 ? (
            <div role="group" aria-label={t("skills.picker.creationModes")}>
              <div className="px-2 pt-1 pb-0.5 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                {t("skills.picker.creationModes")}
              </div>
              {creationModes.map((option, idx) => renderRow(option, idx))}
            </div>
          ) : null}
          {templates.length > 0 ? (
            <div
              role="group"
              aria-label={t("skills.picker.templates")}
              className={cn(
                creationModes.length > 0 && "mt-0.5 border-t border-border/60 pt-1",
              )}
            >
              <div className="px-2 pt-1 pb-0.5 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                {t("skills.picker.templates")}
              </div>
              {templates.map((option, idx) =>
                renderRow(option, creationModes.length + idx),
              )}
            </div>
          ) : null}
        </div>
      )}
    </Card>,
    document.body,
  )
}
