import { useState } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { ChevronDown } from "lucide-react"

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
import { WaveformPlayer } from "./WaveformPlayer"

const VISIBLE_COUNT = 3

export function isAudioCandidateMember(member: CandidateMemberPayload): boolean {
  return (
    member.provider === "freesound" &&
    typeof member.provider_id === "string" &&
    typeof member.title === "string" &&
    typeof member.author === "string" &&
    typeof member.duration_seconds === "number" &&
    Number.isFinite(member.duration_seconds) &&
    member.duration_seconds > 0 &&
    typeof member.source_url === "string" &&
    typeof member.preview_url === "string" &&
    member.license === "CC0" &&
    typeof member.attribution === "string" &&
    typeof member.query === "string"
  )
}

export function isAudioCandidateSurface(surface: CandidateSurface): boolean {
  return surface.members.length > 0 && surface.members.every(isAudioCandidateMember)
}

/** Display the provider's name, not its filename extension. Provenance stays
 * untouched in the persisted member payload and the server-side import door. */
export function soundDisplayTitle(title: string): string {
  return title.replace(/\.[a-z][a-z0-9]{0,15}$/i, "")
}

/** SFX candidates add playback to the existing ordinal/selection contract;
 * importing still happens only through the user's next natural-language turn. */
export function AudioCandidateSurface({
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

  return (
    <Message align="start">
      <MessageContent>
        <motion.div
          layout={!reduceMotion}
          initial={shouldAnimateEntrance(hydrated) && !reduceMotion ? { opacity: 0, y: 4 } : false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduceMotion ? 0 : 0.18 }}
          className="w-full max-w-xl rounded-lg bg-muted p-2"
        >
          <div
            className={cn(
              "flex flex-col gap-1",
              expanded && "max-h-96 overflow-y-auto thin-scroll",
            )}
          >
            <AnimatePresence initial={false} mode="popLayout">
              {shown.map((member, index) => {
                const selected = surface.selected.includes(index)
                return (
                  <motion.div
                    layout={!reduceMotion}
                    key={`${member.provider_id}-${index}`}
                    initial={shouldAnimateEntrance(hydrated) && !reduceMotion ? { opacity: 0, y: 4 } : false}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduceMotion ? { opacity: 1 } : { opacity: 0, y: -4 }}
                    transition={{ duration: reduceMotion ? 0 : 0.16 }}
                    className={cn(
                      "rounded-md px-2 py-2",
                      selected && "bg-accent",
                    )}
                  >
                    <div className="mb-1 flex items-center gap-2.5">
                      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <p className="min-w-0 flex-1 truncate text-sm">
                        {soundDisplayTitle(member.title ?? member.excerpt)}
                      </p>
                    </div>
                    <WaveformPlayer
                      src={member.preview_url ?? ""}
                      durationSeconds={member.duration_seconds}
                      waveformKey={`${surface.candidateSetId}:${member.provider_id}:${index}`}
                    />
                  </motion.div>
                )
              })}
            </AnimatePresence>
          </div>
          {overflow > 0 ? (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="mt-1 flex w-full items-center gap-1.5 rounded-md px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
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
      </MessageContent>
    </Message>
  )
}
