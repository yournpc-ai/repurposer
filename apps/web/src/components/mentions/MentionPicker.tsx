"use client"

import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
  MENTION_REGISTRY,
  mentionTypeDef,
  type ChatMention,
  type MentionCandidate,
  type MentionContext,
} from "@/lib/mentions"

/**
 * 提及 picker (MentionPicker) — the @-triggered candidate list, anchored to
 * the caret (fixed positioning, flips below when there's no room above). A
 * hand-rolled popup (not Popover): the editor keeps focus throughout, and a
 * window capture-phase keydown owns Arrow/Enter/Escape while open, so the
 * editor's Enter-to-send never fires on a pick.
 *
 * Registry-driven: candidates come from `MENTION_REGISTRY` sources, rows get
 * their icon from the type's entry — adding an @ type is a registry entry,
 * never a branch here.
 */
export function MentionPicker({
  query,
  position,
  context,
  onSelect,
  onClose,
}: {
  /** Text typed after the "@" (already cursor-scoped by the caller). */
  query: string
  /** The caret's viewport rect — the popup anchors above (or below) it. */
  position: { left: number; top: number; bottom: number }
  /** Live surface data handed to registry sources (e.g. attached files). */
  context: MentionContext
  onSelect: (mention: ChatMention) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [candidates, setCandidates] = useState<
    { type: ChatMention["type"]; candidate: MentionCandidate }[]
  >([])
  const [activeIndex, setActiveIndex] = useState(0)

  // Load candidates from every registered type on open (and when the live
  // context changes — e.g. a file attached mid-typing). Per-open fetch keeps
  // the list fresh; sources are cheap reads.
  useEffect(() => {
    let cancelled = false
    Promise.all(
      MENTION_REGISTRY.map(async (def) =>
        (await def.source(context)).map((candidate) => ({
          type: def.type,
          candidate,
        })),
      ),
    ).then((lists) => {
      if (!cancelled) setCandidates(lists.flat())
    })
    return () => {
      cancelled = true
    }
  }, [context])

  const q = query.trim().toLowerCase()
  const filtered = candidates.filter(
    ({ candidate }) =>
      !q ||
      candidate.label.toLowerCase().includes(q) ||
      candidate.id.toLowerCase().includes(q),
  )

  useEffect(() => {
    setActiveIndex(0)
  }, [q])

  // Capture-phase keyboard ownership while open: arrows cycle, Enter picks,
  // Escape closes. stopPropagation keeps the composer's own Enter-to-send
  // handler from firing on a pick. IME composition is NEVER intercepted —
  // Enter/arrows belong to the input method while a composition is active
  // (the composer's send path has the same guard).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.isComposing) return
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault()
        e.stopPropagation()
        if (filtered.length === 0) return
        setActiveIndex((prev) => {
          const delta = e.key === "ArrowDown" ? 1 : -1
          return (prev + delta + filtered.length) % filtered.length
        })
      } else if (e.key === "Enter") {
        e.preventDefault()
        e.stopPropagation()
        const picked = filtered[activeIndex]
        if (picked) {
          onSelect({ type: picked.type, id: picked.candidate.id, label: picked.candidate.label })
        }
      } else if (e.key === "Escape") {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener("keydown", handler, true)
    return () => window.removeEventListener("keydown", handler, true)
  }, [filtered, activeIndex, onSelect, onClose])

  return (
    // Anchor to the caret: above it while there's room, below otherwise.
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
      className="overlay-surface fixed z-50 flex w-64 flex-col gap-0.5 rounded-lg p-1.5 text-xs text-popover-foreground shadow-md ring-1 ring-foreground/10"
    >
      {filtered.length === 0 ? (
        <span className="px-2 py-1.5 text-muted-foreground">
          {t("mentions.pickerEmpty")}
        </span>
      ) : (
        filtered.map(({ type, candidate }, index) => {
          const Icon = mentionTypeDef(type)?.icon
          return (
            <button
              key={`${type}:${candidate.id}`}
              type="button"
              onMouseDown={(e) => e.preventDefault() /* keep textarea focus */}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() =>
                onSelect({ type, id: candidate.id, label: candidate.label })
              }
              className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-left ${
                index === activeIndex ? "bg-accent" : ""
              }`}
            >
              {Icon ? <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : null}
              <span className="flex-1 truncate">{candidate.label}</span>
              {candidate.hint ? (
                <span className="truncate text-[10px] text-muted-foreground">
                  {candidate.hint}
                </span>
              ) : null}
            </button>
          )
        })
      )}
    </div>
  )
}
