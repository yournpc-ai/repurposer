import { useTranslation } from "react-i18next"
import { Check } from "lucide-react"

import { Message, MessageContent } from "@/components/ui/message"
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

export function isVideoPresetCandidateSurface(surface: CandidateSurface): boolean {
  return surface.kind === "video_preset_set" && surface.members.length >= 2 &&
    surface.members.every(isVideoPresetCandidateMember)
}

function isVideoPresetCandidateMember(member: CandidateMemberPayload): boolean {
  return Boolean(
    member.preset_id && member.preview_url && member.preview_digest &&
    typeof member.duration_seconds === "number" && member.duration_seconds > 0 &&
    member.aspect && member.width && member.height
  )
}

/** Real dynamic Preset comparison. Cards are not selection buttons: the user's
 * later ordinary message selects by ordinal, and this surface only repaints. */
export function VideoPresetCandidateSurface({
  surface,
  hydrated,
  serverMessageId,
  turnId,
  onStructureVisible,
}: {
  surface: CandidateSurface
  hydrated?: boolean
  serverMessageId?: string
  turnId?: string
  onStructureVisible?: RegisterStructureVisibility
}) {
  const { t } = useTranslation()
  useStructureVisibilityRegistration({
    open: surface.members.length > 0,
    history: hydrated,
    serverMessageId,
    turnId,
    register: onStructureVisible,
  })

  return (
    <Message align="start">
      <MessageContent>
        <div className={cn(
          "grid w-full max-w-2xl grid-cols-1 gap-2 rounded-lg bg-muted p-2 sm:grid-cols-2",
          shouldAnimateEntrance(hydrated) &&
            "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300",
        )}>
          {surface.members.map((member, index) => {
            const selected = surface.selected.includes(index)
            const presetId = member.preset_id ?? ""
            return (
              <div
                key={`${presetId}:${member.preview_digest}`}
                className={cn("overflow-hidden rounded-md", selected && "bg-accent")}
              >
                <div className="relative bg-muted">
                  <video
                    src={member.preview_url ?? ""}
                    controls
                    muted
                    loop
                    playsInline
                    preload="metadata"
                    aria-label={t(`videoPresets.${presetId}.name`)}
                    className="block w-full object-contain"
                    style={{ aspectRatio: `${member.width} / ${member.height}` }}
                  />
                  <span className="absolute left-2 top-2 rounded-md bg-background px-1.5 py-0.5 text-xs tabular-nums text-foreground">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                </div>
                <div className="flex items-center gap-2 px-2.5 py-2">
                  <span className="min-w-0 flex-1 truncate text-sm">
                    {t(`videoPresets.${presetId}.name`)}
                  </span>
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                    {member.duration_seconds?.toFixed(1)}s
                  </span>
                  {selected ? <Check className="size-4 shrink-0" aria-label={t("chat.candidates.selected")} /> : null}
                </div>
              </div>
            )
          })}
        </div>
      </MessageContent>
    </Message>
  )
}
