/**
 * 提及注册表 (MENTION_REGISTRY, MENTIONS §4 双端注册表纪律) — the frontend
 * half of the dual-end mention architecture: every @-entity type is ONE
 * registry entry here (icon / i18n key / candidate source). The picker and
 * the chip read the registry only — zero type branches; a new @ type is a
 * new entry, never a patch.
 *
 * Members: `asset` (request family — context enrichment, the effect lives
 * server-side in `_build_context`) and `output` (reference family — the
 * pinned id resolves `target_output_id` deterministically server-side).
 * `recipe` is retired (MENTIONS §3 — a recipe is launch context riding the
 * `recipe_id` transport, never a mention); its type member stays on
 * `ChatMention` so historical messages still render their chips.
 *
 * Surfaces: one MentionEditor family serves the composer AND the persistent
 * chat surfaces (generation overlay, output ChatModal) — the registry's
 * candidate feeds differ per surface via `MentionContext`, the component
 * never does.
 */

import {
  Clapperboard,
  FileText,
  Layers,
  Paperclip,
  type LucideIcon,
} from "lucide-react"

import i18n from "@/lib/i18n"

/** An @ entity reference pinned to a definite id — same name, same shape as
 * the backend `ChatMention` schema (NAMING §1). `"recipe"` is a render
 * residue for historical messages — unregistered, never creatable. */
export interface ChatMention {
  type: "asset" | "output" | "transcript_segment" | "workflow_step" | "recipe"
  id: string
  label: string
}

/** One picker row. `hint` is the muted subtitle (asset: the file kind);
 * `icon` overrides the type's registry icon for this row (an output's kind
 * icon). */
export interface MentionCandidate {
  id: string
  label: string
  hint?: string
  icon?: LucideIcon
}

/** The file-kind vocabulary the asset feed speaks (the `mentions.fileType.*`
 * i18n keys). Surfaces map their own data (File.mime, Asset.type) into it. */
export type MentionFileKind = "video" | "audio" | "image" | "document"

/** A File's mime → the asset feed's kind (composers attach pre-upload
 * Files; chat surfaces carry settled assets whose type is already a kind
 * vocabulary). */
export function fileKindOf(mime: string): MentionFileKind {
  if (mime.startsWith("video/")) return "video"
  if (mime.startsWith("audio/")) return "audio"
  if (mime.startsWith("image/")) return "image"
  return "document"
}

/** A settled asset's type (server vocabulary) → the asset feed's kind. */
export function assetTypeKind(type: string): MentionFileKind {
  if (type === "video") return "video"
  if (type === "audio" || type === "voice_sample") return "audio"
  if (type === "image") return "image"
  return "document"
}

/** An output's mention label (shared by the chat surfaces' output feeds):
 * the clip's hook, truncated; the caller supplies the type-name fallback. */
export function outputMentionLabel(
  output: { payload: unknown; type: string },
  fallback: string,
): string {
  const hook = (output.payload as { hook?: string }).hook
  if (hook) return hook.length > 40 ? `${hook.slice(0, 40)}…` : hook
  return fallback
}

/** The live data a candidate source reads from — handed down from the
 * surface (composer/chat) through the picker, so registry entries stay
 * static config while their feeds stay dynamic. */
export interface MentionContext {
  /** The composer's attached files (pre-upload — the name IS the identity,
   * deduped on attach). */
  files?: { name: string; kind: MentionFileKind }[]
  /** A project's settled assets (chat surfaces) — same asset family, named
   * by title. */
  assets?: { name: string; kind: MentionFileKind }[]
  /** A project's outputs (chat surfaces) — id is the real UUID: the server
   * resolves it into `target_output_id` deterministically. */
  outputs?: { id: string; label: string; kind: string }[]
}

export interface MentionTypeDef {
  type: ChatMention["type"]
  icon: LucideIcon
  /** i18n key root for the type's display name: mentions.types.<type>. */
  i18nKey: string
  /** Candidate supply for the picker (asset: the surface's files/assets via
   * the context; output: the project's outputs). */
  source: (ctx: MentionContext) => Promise<MentionCandidate[]>
  /** Exclusive types allow at most one chip per message — inserting
   * replaces the previous chip of the same type. */
  exclusive?: boolean
}

/** Asset candidates = the surface's files (composer) + settled project
 * assets (chat surfaces). Effect family: context enrichment — the chip
 * serializes into the sentence as `@label`, so the intent agent reads which
 * file the instruction points at. */
async function assetSource(ctx: MentionContext): Promise<MentionCandidate[]> {
  return [...(ctx.files ?? []), ...(ctx.assets ?? [])].map((f) => ({
    id: f.name,
    label: f.name,
    hint: i18n.t(`mentions.fileType.${f.kind}`),
  }))
}

/** Output candidates = the project's outputs (reference family, MENTIONS
 * §2): a pinned output id lands in ChatRequest.mentions and resolves the
 * revision target deterministically — the LLM never guesses which "second
 * clip" the user means. */
async function outputSource(ctx: MentionContext): Promise<MentionCandidate[]> {
  return (ctx.outputs ?? []).map((o) => ({
    id: o.id,
    label: o.label,
    icon: o.kind === "clip" ? Clapperboard : FileText,
  }))
}

export const MENTION_REGISTRY: MentionTypeDef[] = [
  {
    type: "asset",
    icon: Paperclip,
    i18nKey: "mentions.types.asset",
    source: assetSource,
  },
  {
    type: "output",
    icon: Layers,
    i18nKey: "mentions.types.output",
    source: outputSource,
  },
]

/** Registry lookup shared by chip and picker — never a per-type branch at
 * the call site. */
export function mentionTypeDef(type: ChatMention["type"]): MentionTypeDef | undefined {
  return MENTION_REGISTRY.find((d) => d.type === type)
}
