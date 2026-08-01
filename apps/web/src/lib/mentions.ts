/**
 * 提及注册表 (MENTION_REGISTRY, docs/tasks/recipe-mention.md §2.1) — the
 * frontend half of the dual-end mention architecture: every @-entity type is
 * ONE registry entry here (icon / i18n key / candidate source). The picker
 * and the chip read the registry only — zero type branches; a new @ type is
 * a new entry, never a patch.
 *
 * Effect families live server-side: context enrichment is already generic
 * (`_build_context`), the task-book pin is recipe-exclusive
 * (`resolve_recipe_mentions`). `recipe` is the first registered type; its
 * candidates come from the public `GET /api/v1/recipes` (pin substance never
 * leaves the server).
 */

import { Wand2, type LucideIcon } from "lucide-react"

import { apiFetch } from "@/lib/api"
import i18n from "@/lib/i18n"

/** An @ entity reference pinned to a definite id — same name, same shape as
 * the backend `ChatMention` schema (NAMING §1). */
export interface ChatMention {
  type: "asset" | "output" | "transcript_segment" | "workflow_step" | "recipe"
  id: string
  label: string
}

/** One picker row. `hint` is the muted subtitle (recipe: derived from the
 * card's input_slots, e.g. "Needs a talk video"). */
export interface MentionCandidate {
  id: string
  label: string
  hint?: string
}

export interface MentionTypeDef {
  type: ChatMention["type"]
  icon: LucideIcon
  /** i18n key root for the type's display name: mentions.types.<type>. */
  i18nKey: string
  /** Candidate supply for the picker (recipe: the public card catalogue). */
  source: () => Promise<MentionCandidate[]>
  /** Exclusive types allow at most one chip per message — inserting
   * replaces the previous chip of the same type (v1: one recipe per run,
   * mirroring the server-side rejection). */
  exclusive?: boolean
}

/** Shape of the public `GET /api/v1/recipes` payload (pin substance — the
 * outputs / dub languages — is deliberately not served). */
interface RecipePublic {
  id: string
  status: "live" | "reserved"
  input_slots: { type: string; required: boolean }[]
}

async function recipeSource(): Promise<MentionCandidate[]> {
  const res = await apiFetch("/api/v1/recipes")
  if (!res.ok) return []
  const recipes = (await res.json()) as RecipePublic[]
  return recipes
    .filter((r) => r.status === "live")
    .map((r) => ({
      id: r.id,
      label: i18n.t(`recipes.${r.id}.title`),
      hint: r.input_slots
        .filter((s) => s.required)
        .map((s) => i18n.t(`mentions.input.${s.type}`))
        .join(" + "),
    }))
}

export const MENTION_REGISTRY: MentionTypeDef[] = [
  {
    type: "recipe",
    icon: Wand2,
    i18nKey: "mentions.types.recipe",
    source: recipeSource,
    exclusive: true,
  },
]

/** Registry lookup shared by chip and picker — never a per-type branch at
 * the call site. */
export function mentionTypeDef(type: ChatMention["type"]): MentionTypeDef | undefined {
  return MENTION_REGISTRY.find((d) => d.type === type)
}
