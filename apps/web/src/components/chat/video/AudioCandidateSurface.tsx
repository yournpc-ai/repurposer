import { useState } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { Check, ChevronDown } from "@/components/ui/icons"

import { cn } from "@/lib/utils"
import type {
  CandidateMemberPayload,
  CandidateSurface,
} from "../timeline/types"
import { shouldAnimateEntrance } from "../timeline/reveal"
import {
  useStructureVisibilityRegistration,
  type RegisterStructureVisibility,
} from "../structureVisibility"
import { WaveformPlayer } from "./WaveformPlayer"

const VISIBLE_COUNT = 3

function hasCompleteAudioFacts(member: CandidateMemberPayload): boolean {
  return (
    typeof member.provider_id === "string" &&
    typeof member.title === "string" &&
    typeof member.author === "string" &&
    typeof member.duration_seconds === "number" &&
    Number.isFinite(member.duration_seconds) &&
    member.duration_seconds > 0 &&
    typeof member.preview_url === "string" &&
    typeof member.license === "string" &&
    typeof member.attribution === "string" &&
    typeof member.query === "string"
  )
}

export function isAudioCandidateMember(member: CandidateMemberPayload): boolean {
  if (!hasCompleteAudioFacts(member)) return false
  if (member.provider === "freesound") {
    return (
      member.music_id == null &&
      typeof member.source_url === "string" &&
      member.license === "CC0"
    )
  }
  return (
    member.provider === "music_library" &&
    !!member.provider_id &&
    member.music_id === member.provider_id &&
    (member.source_url == null || typeof member.source_url === "string") &&
    member.start === 0 &&
    member.end === member.duration_seconds
  )
}

export function isAudioCandidateSurface(surface: CandidateSurface): boolean {
  if (surface.members.length === 0 || !surface.members.every(isAudioCandidateMember)) {
    return false
  }
  const provider = surface.members[0].provider
  return (
    surface.members.every((member) => member.provider === provider) &&
    (surface.kind !== "music_set" || provider === "music_library")
  )
}

/** Display the provider's name, not its filename extension. Provenance stays
 * untouched in the persisted member payload and the server-side import door. */
export function soundDisplayTitle(title: string): string {
  return title.replace(/\.[a-z][a-z0-9]{0,15}$/i, "")
}

/** Audio candidates add playback to the existing ordinal/selection contract;
 * importing still happens only through the user's next natural-language turn. */
export function AudioCandidateSurface({
  surface,
  hydrated,
  serverMessageId,
  turnId,
  onStructureVisible,
  onSelectCandidate,
  selectionDisabled = false,
}: {
  surface: CandidateSurface
  hydrated?: boolean
  serverMessageId?: string
  turnId?: string
  onStructureVisible?: RegisterStructureVisibility
  onSelectCandidate?: (message: string, memberIndex: number, surface: CandidateSurface) => void
  selectionDisabled?: boolean
}) {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const [expanded, setExpanded] = useState(false)
  useStructureVisibilityRegistration({
    open: surface.members.length > 0,
    history: hydrated,
    serverMessageId,
    turnId,
    register: onStructureVisible,
  })
  const overflow = surface.members.length - VISIBLE_COUNT
  const shown = expanded ? surface.members : surface.members.slice(0, VISIBLE_COUNT)
  const isMusicSet = surface.kind === "music_set"
  const showSelectAction = Boolean(onSelectCandidate) || isMusicSet

  return (
    <div className="ui-th-message">
      <motion.div
        data-slot="audio-candidate-surface"
        layout={!reduceMotion}
        initial={shouldAnimateEntrance(hydrated) && !reduceMotion ? { opacity: 0, y: 4 } : false}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.18 }}
        className="w-full max-w-2xl rounded-2xl border border-border bg-card/85 p-3.5 shadow-sm"
      >
        {isMusicSet ? (
          <div className="mb-2.5 flex items-center justify-between gap-2 px-0.5">
            <div className="flex min-w-0 items-center gap-2">
              <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                {t("chat.candidates.musicTitle")}
              </span>
              {surface.topic ? (
                <>
                  <span aria-hidden="true" className="text-muted-foreground/40">
                    ·
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {surface.topic}
                  </span>
                </>
              ) : null}
            </div>
            <span className="shrink-0 rounded-full border border-border/70 bg-muted/50 px-2 py-0.5 text-[11px] tabular-nums text-muted-foreground">
              {t("chat.candidates.trackCount", { count: surface.members.length })}
            </span>
          </div>
        ) : null}

        <div
          className={cn(
            "flex flex-col gap-2",
            expanded && "max-h-96 overflow-y-auto thin-scroll",
          )}
        >
          <AnimatePresence initial={false} mode="popLayout">
            {shown.map((member, index) => {
              const selected = surface.selected.includes(index)
              const ordinal = String(index + 1).padStart(2, "0")
              const displayTitle = soundDisplayTitle(member.title ?? member.excerpt)
              const hasBpm = typeof member.bpm === "number" && Number.isFinite(member.bpm) && member.bpm > 0
              const hasLufs = typeof member.lufs === "number" && Number.isFinite(member.lufs)
              const styleTags = (member.compatible_styles ?? []).filter(Boolean).slice(0, 3)
              const hasUseCount = typeof member.use_count === "number" && member.use_count > 0
              const hasMeta =
                hasBpm ||
                hasLufs ||
                member.instrumental === true ||
                styleTags.length > 0 ||
                hasUseCount

              return (
                <motion.div
                  layout={!reduceMotion}
                  key={`${member.provider_id}-${index}`}
                  data-slot="audio-candidate-row"
                  data-selected={selected ? "true" : undefined}
                  initial={shouldAnimateEntrance(hydrated) && !reduceMotion ? { opacity: 0, y: 4 } : false}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduceMotion ? { opacity: 1 } : { opacity: 0, y: -4 }}
                  transition={{ duration: reduceMotion ? 0 : 0.16 }}
                  className={cn(
                    "rounded-xl border px-3 py-2.5 transition-colors",
                    selected
                      ? "border-foreground/25 bg-accent"
                      : "border-border/70 bg-background/60 hover:bg-accent/35",
                  )}
                >
                  <div className="mb-2 flex items-center gap-2.5">
                    <span
                      className={cn(
                        "shrink-0 text-[11px] font-medium tabular-nums",
                        selected ? "text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {ordinal}
                    </span>
                    <p className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
                      {displayTitle}
                    </p>
                    {showSelectAction ? (
                      <button
                        type="button"
                        disabled={!onSelectCandidate || selectionDisabled}
                        onClick={() => {
                          if (!onSelectCandidate || selectionDisabled) return
                          const message = t("chat.candidates.selectTrackMessage", {
                            ordinal,
                            title: displayTitle,
                          })
                          onSelectCandidate(message, index, surface)
                        }}
                        className={cn(
                          "inline-flex h-7 shrink-0 items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-55",
                          selected
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border bg-card text-foreground hover:bg-accent",
                        )}
                      >
                        {selected ? <Check className="size-3" /> : null}
                        <span>
                          {selected
                            ? t("chat.candidates.selected")
                            : t("chat.candidates.useTrack")}
                        </span>
                      </button>
                    ) : null}
                  </div>
                  <WaveformPlayer
                    src={member.preview_url ?? ""}
                    durationSeconds={member.duration_seconds}
                    waveformKey={`${surface.candidateSetId}:${member.provider_id}:${index}`}
                  />
                  {hasMeta ? (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 pl-9">
                      {hasBpm ? (
                        <span className="rounded-full border border-border/60 bg-muted/60 px-2 py-0.5 text-[11px] tabular-nums text-foreground/85">
                          {Math.round(member.bpm!)} BPM
                        </span>
                      ) : null}
                      {hasLufs ? (
                        <span className="rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[11px] tabular-nums text-muted-foreground">
                          {member.lufs!.toFixed(1)} LUFS
                        </span>
                      ) : null}
                      {member.instrumental === true ? (
                        <span className="rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground">
                          {t("chat.candidates.instrumental")}
                        </span>
                      ) : null}
                      {styleTags.map((style) => (
                        <span
                          key={`style-${style}`}
                          className="rounded-full border border-border/50 bg-background/80 px-2 py-0.5 text-[11px] text-muted-foreground"
                        >
                          {style}
                        </span>
                      ))}
                      {hasUseCount ? (
                        <span className="rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[11px] tabular-nums text-muted-foreground">
                          {t("chat.candidates.usedCount", { count: member.use_count })}
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>
        {overflow > 0 ? (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="mt-1.5 flex w-full items-center gap-1.5 rounded-xl px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ChevronDown
              className={cn("size-3.5 transition-transform", expanded && "rotate-180")}
            />
            {expanded
              ? t("chat.candidates.less")
              : t("chat.candidates.more", { count: overflow })}
          </button>
        ) : null}
      </motion.div>
    </div>
  )
}
