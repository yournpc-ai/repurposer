"use client"

import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { BookOpen } from "lucide-react"
import { useTranslation } from "react-i18next"

import {
  fetchChatSkills,
  filterSkillOptions,
  type SkillOption,
} from "@/lib/skills"
import { cn } from "@/lib/utils"

/** Caret-anchored Skill picker. Like MentionPicker, it portals to body and
 * owns Arrow/Enter/Escape in the capture phase while the editor keeps focus.
 * Selecting emits the DTO binding; the host consumes only the slash token. */
export function SkillPicker({
  query,
  position,
  onSelect,
  onClose,
}: {
  query: string
  position: { left: number; top: number; bottom: number }
  onSelect: (option: SkillOption) => void
  onClose: () => void
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

  const filtered = filterSkillOptions(options, query)

  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.isComposing) return
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault()
        event.stopPropagation()
        if (filtered.length === 0) return
        setActiveIndex((previous) => {
          const delta = event.key === "ArrowDown" ? 1 : -1
          return (previous + delta + filtered.length) % filtered.length
        })
      } else if (event.key === "Enter") {
        event.preventDefault()
        event.stopPropagation()
        const picked = filtered[activeIndex]
        if (picked) onSelect(picked)
      } else if (event.key === "Escape") {
        event.preventDefault()
        event.stopPropagation()
        onClose()
      }
    }
    window.addEventListener("keydown", handler, true)
    return () => window.removeEventListener("keydown", handler, true)
  }, [filtered, activeIndex, onSelect, onClose])

  return createPortal(
    <div
      style={
        position.top > 220
          ? {
              left: position.left,
              top: position.top,
              transform: "translateY(calc(-100% - 4px))",
            }
          : { left: position.left, top: position.bottom + 4 }
      }
      className="overlay-surface fixed z-50 flex max-h-64 w-80 flex-col gap-0.5 overflow-y-auto rounded-lg p-1.5 text-xs text-popover-foreground border border-subtle thin-scroll"
    >
      {status === "loading" ? (
        <span className="px-2 py-1.5 text-muted-foreground">
          {t("common.loading")}
        </span>
      ) : status === "error" ? (
        <span className="px-2 py-1.5 text-muted-foreground">
          {t("common.requestFailed")}
        </span>
      ) : filtered.length === 0 ? (
        <span className="px-2 py-1.5 text-muted-foreground">
          {t("mentions.pickerEmpty")}
        </span>
      ) : (
        filtered.map((option, index) => {
          const key =
            option.reference.kind === "builtin"
              ? `builtin:${option.reference.skill_id}:${option.reference.version}`
              : `external:${option.reference.skill_version_id}`
          return (
            <button
              key={key}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => onSelect(option)}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-left",
                index === activeIndex && "bg-accent",
              )}
            >
              <BookOpen className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1">
                <span className="block truncate">
                  /{option.name}
                  {option.version_number != null ? ` v${option.version_number}` : ""}
                </span>
                {option.description ? (
                  <span className="block truncate text-[10px] text-muted-foreground">
                    {option.reference.kind === "builtin"
                      ? t(`skills.builtin.${option.reference.skill_id}.description`)
                      : option.description}
                  </span>
                ) : null}
              </span>
            </button>
          )
        })
      )}
    </div>,
    document.body,
  )
}
