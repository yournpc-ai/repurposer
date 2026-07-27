"use client"

import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { Check, Mic2, Users, Wand2 } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

/** The speaker shape this picker reads. The API already returns all of these
 * (SpeakerContext); the composer previously typed it down to {id, name}. */
export interface SpeakerPickerEntry {
  id: string
  name: string
  title?: string | null
  language?: string
  avatar_url?: string | null
  sentence_style?: string | null
  emotional_tone?: "rational" | "passionate" | "gentle" | "sharp" | "humorous" | null
  core_values?: string[]
  voice?: string | null
}

interface SpeakerPickerModalProps {
  speakers: SpeakerPickerEntry[]
  /** Current selection: a speaker id, or `autoValue` for auto-generate. */
  value: string
  autoValue: string
  onSelect: (id: string) => void
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Style one-liner: sentence style + tone + up to two core values. */
function useStyleTags(speaker: SpeakerPickerEntry): string {
  const { t } = useTranslation()
  const parts: string[] = []
  if (speaker.sentence_style) parts.push(speaker.sentence_style)
  if (speaker.emotional_tone) {
    parts.push(t(`speakerDetail.tones.${speaker.emotional_tone}`))
  }
  for (const value of speaker.core_values ?? []) {
    if (parts.length >= 3) break
    parts.push(value)
  }
  return parts.join(" · ")
}

/** Rich single-select picker for the Speaker dimension. This is a picker, not
 * an editor — persona editing lives on the /speakers pages. */
export function SpeakerPickerModal({
  speakers,
  value,
  autoValue,
  onSelect,
  open,
  onOpenChange,
}: SpeakerPickerModalProps) {
  const { t } = useTranslation()

  const pick = (id: string) => {
    onSelect(id)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("composer.speakerPickerTitle")}</DialogTitle>
          <DialogDescription>{t("composer.speakerDesc")}</DialogDescription>
        </DialogHeader>

        <div className="flex max-h-[50vh] flex-col gap-1 overflow-y-auto">
          {/* Auto-generate: the default — never fall back to a concrete
              speaker entry; the user picks one explicitly. */}
          <button
            type="button"
            onClick={() => pick(autoValue)}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
              value === autoValue ? "bg-accent" : "hover:bg-accent/50"
            )}
          >
            <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-muted">
              <Wand2 className="h-4 w-4 text-muted-foreground" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm">{t("composer.autoGenerate")}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {t("composer.speakerAutoDesc")}
              </span>
            </span>
            {value === autoValue && <Check className="h-4 w-4 flex-shrink-0" />}
          </button>

          {speakers.map((speaker) => (
            <SpeakerRow
              key={speaker.id}
              speaker={speaker}
              selected={speaker.id === value}
              onPick={() => pick(speaker.id)}
            />
          ))}
        </div>

        <div className="flex justify-end pt-1">
          <Link
            to="/speakers"
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <Users className="h-3.5 w-3.5" />
            {t("composer.manageSpeakers")}
          </Link>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function SpeakerRow({
  speaker,
  selected,
  onPick,
}: {
  speaker: SpeakerPickerEntry
  selected: boolean
  onPick: () => void
}) {
  const { t } = useTranslation()
  const tags = useStyleTags(speaker)

  return (
    <button
      type="button"
      onClick={onPick}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
        selected ? "bg-accent" : "hover:bg-accent/50"
      )}
    >
      <Avatar className="h-9 w-9">
        {speaker.avatar_url ? <AvatarImage src={speaker.avatar_url} alt={speaker.name} /> : null}
        <AvatarFallback>{speaker.name.slice(0, 1)}</AvatarFallback>
      </Avatar>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm">
          {speaker.name}
          {speaker.title ? (
            <span className="text-muted-foreground"> · {speaker.title}</span>
          ) : null}
        </span>
        {tags ? (
          <span className="block truncate text-xs text-muted-foreground">{tags}</span>
        ) : null}
        <span className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
          <Mic2 className="h-3 w-3" />
          {speaker.voice ? t("composer.voiceBound") : t("composer.voiceMissing")}
        </span>
      </span>
      {selected && <Check className="h-4 w-4 flex-shrink-0" />}
    </button>
  )
}
