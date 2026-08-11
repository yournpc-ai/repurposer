/**
 * 提及注册表 (MENTION_REGISTRY, MENTIONS §4 双端注册表纪律) — the frontend
 * half of the dual-end mention architecture: every @-entity type is ONE
 * registry entry here (icon / i18n key / candidate source). The picker and
 * the chip read the registry only — zero type branches; a new @ type is a
 * new entry, never a patch.
 *
 * `asset` is the sole registered type (context enrichment — the effect lives
 * server-side in `_build_context`). `recipe` is retired (MENTIONS §3 — a
 * recipe is launch context riding the `recipe_id` transport, never a
 * mention); its type member stays on `ChatMention` so historical messages
 * still render their chips.
 */

import { Paperclip, type LucideIcon } from "lucide-react"

import i18n from "@/lib/i18n"

/** An @ entity reference pinned to a definite id — same name, same shape as
 * the backend `ChatMention` schema (NAMING §1). `"recipe"` is a render
 * residue for historical messages — unregistered, never creatable. */
export interface ChatMention {
  type: "asset" | "output" | "transcript_segment" | "workflow_step" | "recipe"
  id: string
  label: string
}

/** One picker row. `hint` is the muted subtitle (asset: the file kind). */
export interface MentionCandidate {
  id: string
  label: string
  hint?: string
}

/** The live data a candidate source reads from — handed down from the
 * surface (composer/chat) through the picker, so registry entries stay
 * static config while their feeds stay dynamic. */
export interface MentionContext {
  /** Files attached in the composer (the asset type's candidate feed). */
  files?: { name: string; type: string }[]
}

export interface MentionTypeDef {
  type: ChatMention["type"]
  icon: LucideIcon
  /** i18n key root for the type's display name: mentions.types.<type>. */
  i18nKey: string
  /** Candidate supply for the picker (asset: the surface's attached files
   * via the context). */
  source: (ctx: MentionContext) => Promise<MentionCandidate[]>
  /** Exclusive types allow at most one chip per message — inserting
   * replaces the previous chip of the same type. */
  exclusive?: boolean
}

function fileKind(mime: string): "video" | "audio" | "image" | "document" {
  if (mime.startsWith("video/")) return "video"
  if (mime.startsWith("audio/")) return "audio"
  if (mime.startsWith("image/")) return "image"
  return "document"
}

/** Asset candidates = the surface's attached files (id = filename — the
 * composer's files have no UUID until the project exists; the name IS the
 * identity, deduped on attach). Effect family: context enrichment — the
 * chip serializes into the sentence as `@label`, so the intent agent reads
 * which file the instruction points at. */
async function assetSource(ctx: MentionContext): Promise<MentionCandidate[]> {
  return (ctx.files ?? []).map((f) => ({
    id: f.name,
    label: f.name,
    hint: i18n.t(`mentions.fileType.${fileKind(f.type)}`),
  }))
}

export const MENTION_REGISTRY: MentionTypeDef[] = [
  {
    type: "asset",
    icon: Paperclip,
    i18nKey: "mentions.types.asset",
    source: assetSource,
  },
]

/** Registry lookup shared by chip and picker — never a per-type branch at
 * the call site. */
export function mentionTypeDef(type: ChatMention["type"]): MentionTypeDef | undefined {
  return MENTION_REGISTRY.find((d) => d.type === type)
}
