"use client"

import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { Check, Users, Wand2 } from "lucide-react"

import { cn } from "@/lib/utils"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

/** The persona shape this picker reads. The API already returns all of these
 * (PersonaContext); the composer previously typed it down to {id, name}. */
export interface PersonaPickerEntry {
  id: string
  name: string
  title?: string | null
  language?: string
  avatar_url?: string | null
  sentence_style?: string | null
  emotional_tone?: "rational" | "passionate" | "gentle" | "sharp" | "humorous" | null
  core_values?: string[]
  /** Voice block (audio): {"kind":"cloned"|"stock", ...} — null = Auto. */
  voice?: { kind?: string } | null
}

/** Style one-liner: sentence style + tone + up to two core values. */
function useStyleTags(persona: PersonaPickerEntry): string {
  const { t } = useTranslation()
  const parts: string[] = []
  if (persona.sentence_style) parts.push(persona.sentence_style)
  if (persona.emotional_tone) {
    parts.push(t(`personaDetail.tones.${persona.emotional_tone}`))
  }
  for (const value of persona.core_values ?? []) {
    if (parts.length >= 3) break
    parts.push(value)
  }
  return parts.join(" · ")
}

/** Persona picker panel — the frosted Popover the Persona pill opens
 * (side="bottom"): Auto row + persona rows + manage link. This is a
 * picker, not an editor — persona editing lives on the /personas pages.
 * Row anatomy mirrors the Assets panel (2026-08-21): a ROUND identity tile
 * (identity column = round, file column = square) + name / meta two lines
 * (style tags · voice state) + the selected Check. */
export function PersonaPanel({
  personas,
  value,
  autoValue,
  onSelect,
}: {
  personas: PersonaPickerEntry[]
  /** Current selection: a persona id, or `autoValue` for auto-generate. */
  value: string
  autoValue: string
  onSelect: (id: string) => void
}) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-1">
      <div className="flex max-h-72 flex-col gap-0.5 overflow-y-auto no-scrollbar">
        {/* Auto-generate: the default — never fall back to a concrete
            persona entry; the user picks one explicitly. */}
        <button
          type="button"
          onClick={() => onSelect(autoValue)}
          className={cn(
            "flex items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors",
            value === autoValue ? "bg-accent" : "hover:bg-accent/50"
          )}
        >
          <span className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-muted">
            <Wand2 className="h-3.5 w-3.5 text-muted-foreground" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium text-foreground">
              {t("composer.autoGenerate")}
            </span>
            <span className="block truncate text-[11px] text-muted-foreground">
              {t("composer.personaAutoDesc")}
            </span>
          </span>
          {value === autoValue && <Check className="h-3.5 w-3.5 flex-none" />}
        </button>

        {personas.map((persona) => (
          <PersonaPanelRow
            key={persona.id}
            persona={persona}
            selected={persona.id === value}
            onPick={() => onSelect(persona.id)}
          />
        ))}
      </div>

      <div className="flex justify-end pt-1">
        <Link
          to="/personas"
          className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          <Users className="h-3 w-3" />
          {t("composer.managePersonas")}
        </Link>
      </div>
    </div>
  )
}

function PersonaPanelRow({
  persona,
  selected,
  onPick,
}: {
  persona: PersonaPickerEntry
  selected: boolean
  onPick: () => void
}) {
  const { t } = useTranslation()
  const tags = useStyleTags(persona)

  return (
    <button
      type="button"
      onClick={onPick}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors",
        selected ? "bg-accent" : "hover:bg-accent/50"
      )}
    >
      <Avatar className="h-9 w-9">
        {persona.avatar_url ? <AvatarImage src={persona.avatar_url} alt={persona.name} /> : null}
        <AvatarFallback>{persona.name.slice(0, 1)}</AvatarFallback>
      </Avatar>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs font-medium text-foreground">
          {persona.name}
          {persona.title ? (
            <span className="font-normal text-muted-foreground"> · {persona.title}</span>
          ) : null}
        </span>
        <span className="block truncate text-[11px] text-muted-foreground">
          {[
            tags || null,
            persona.voice ? t("composer.voiceBound") : t("composer.voiceMissing"),
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </span>
      {selected && <Check className="h-3.5 w-3.5 flex-none" />}
    </button>
  )
}
