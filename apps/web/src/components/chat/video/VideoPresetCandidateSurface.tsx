import { lazy, Suspense, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Check } from "@/components/ui/icons"

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

const MotionPresetPlayer = lazy(() => import("./MotionPresetPlayer"))

export function isVideoPresetCandidateSurface(surface: CandidateSurface): boolean {
  return surface.kind === "video_preset_set" && surface.members.length >= 2 &&
    surface.members.every(isVideoPresetCandidateMember)
}

function isVideoPresetCandidateMember(member: CandidateMemberPayload): boolean {
  return Boolean(
    member.preset_id && (member.preview_url || member.preview_spec) && member.preview_digest &&
    typeof member.duration_seconds === "number" && member.duration_seconds > 0 &&
    member.aspect && member.width && member.height
  )
}

export function VideoPresetCandidateSurface({
  surface,
  hydrated,
  serverMessageId,
  turnId,
  onStructureVisible,
  onSelectCandidate,
  selectionDisabled,
}: {
  surface: CandidateSurface
  onSelectCandidate?: (message: string, index: number, surface: CandidateSurface) => void
  selectionDisabled?: boolean
  hydrated?: boolean
  serverMessageId?: string
  turnId?: string
  onStructureVisible?: RegisterStructureVisibility
}) {
  const { t } = useTranslation()
  const [canPlay, setCanPlay] = useState(false)
  useEffect(() => {
    setCanPlay(typeof CanvasRenderingContext2D !== "undefined" && typeof FontFace !== "undefined")
  }, [])
  useStructureVisibilityRegistration({
    open: surface.members.length > 0,
    history: hydrated,
    serverMessageId,
    turnId,
    register: onStructureVisible,
  })

  return (
    <div className="ui-th-message">
      <div className={cn(
        "grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2",
        shouldAnimateEntrance(hydrated) &&
          "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300",
      )}>
        {surface.members.map((member, index) => {
          const selected = surface.selected.includes(index)
          const presetId = member.preset_id ?? ""
          const title = t(`videoPresets.${presetId}.name`, { nsSeparator: false, defaultValue: member.title ?? presetId })
          const ordinal = String(index + 1).padStart(2, "0")
          return (
            <div
              key={`${presetId}:${member.preview_digest}`}
              className="overflow-hidden rounded-xl border border-subtle bg-card text-foreground"
            >
              <div className="relative grid place-items-center bg-muted" style={{ aspectRatio: member.width + "/" + member.height }}>
                {member.preview_spec ? (
                  canPlay ? <Suspense fallback={null}><MotionPresetPlayer spec={member.preview_spec} title={title} /></Suspense>
                    : <span className="text-xs text-muted-foreground">{t("chat.candidates.presetUnavailable")}</span>
                ) : (
                  <video src={member.preview_url ?? ""} controls muted loop playsInline preload="metadata"
                    aria-label={title} className="block w-full object-contain" />
                )}
                <span className="pointer-events-none absolute left-2 top-2 rounded-full bg-card px-2 py-0.5 font-mono text-xs text-foreground">
                  {ordinal}
                </span>
              </div>
              <div className="flex items-center gap-2 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{title}</p>
                  <p className="text-xs tabular-nums text-muted-foreground">
                    {member.category && t(`chat.candidates.${member.category}`) + " · "}{member.duration_seconds?.toFixed(1)}s
                  </p>
                </div>
                <button type="button" disabled={!onSelectCandidate || selectionDisabled || selected}
                  aria-pressed={selected}
                  onClick={() => onSelectCandidate?.(t("chat.candidates.presetMessage", { ordinal, title }), index, surface)}
                  className={cn("inline-flex items-center gap-1 rounded-full border border-subtle px-3 py-1 text-xs font-medium focus-visible:outline-2",
                    selected ? "bg-foreground text-background" : "bg-card text-foreground hover:bg-muted")}>
                  {selected && <Check size={14} />}{t(selected ? "chat.candidates.selected" : "chat.candidates.usePreset")}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
