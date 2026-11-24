import type { VideoSpec } from "@repurposer/video-spec"

import { API_URL, apiFetch } from "@/lib/api"

/** The exact versioned Skill binding accepted by POST /chat. Skills are a
 * dedicated creation binding, never an @mention or a hidden recipe id. */
export type BuiltInSkillReference = {
  kind: "builtin"
  skill_id: string
  version: string
}

export type ExternalSkillReference = {
  kind: "external"
  skill_version_id: string
}

export type SkillReference = BuiltInSkillReference | ExternalSkillReference

export type StylePresetId =
  | "institutional_dark"
  | "swiss_paper"
  | "vox_editorial"
  | "kinetic_anime"

export interface SkillBlueprintSummary {
  act_count: number
  slot_count: number
  duration_s: number
  style_preset?: StylePresetId | string | null
}

export interface SkillOption {
  reference: SkillReference
  skill_id: string
  name: string
  description: string
  capabilities: string[]
  version_number?: number | null
  blueprint_summary?: SkillBlueprintSummary | null
}

export interface ChatSkillsResponse {
  items: SkillOption[]
}

export interface SlotManifestItem {
  slot_number: number
  code: string
  act_index: number
  act_id: string
  block_id: string
  slot_key: string
  kind: "text" | "image" | "metric" | "chart_point" | "message" | "callout"
  label_zh: string
  label_en: string
  example_value: string
  aspect_ratio?: string | null
}

export interface SlotPreviewResponse {
  skill_version_id: string
  name: string
  duration_s: number
  style_preset: StylePresetId
  locale: "zh" | "en"
  video_spec: VideoSpec
  slots: SlotManifestItem[]
  copyable_checklist: string
}

/** Immutable first-version identities mirrored from the deployed built-in
 * packs. They keep Home and Slash usable during a catalog-network outage;
 * the server still validates the exact version on POST /chat. */
export const BUILTIN_SKILL_VERSIONS = {
  "promo-video": "bdd94be16d60fa8f",
  "talking-head-video": "1.0.0",
  "text-animation": "1.0.0",
  "knowledge-explainer": "1.0.0",
} as const

export function localBuiltinSkillOptions(): SkillOption[] {
  return Object.entries(BUILTIN_SKILL_VERSIONS).map(([skill_id, version]) => ({
    reference: { kind: "builtin", skill_id, version },
    skill_id,
    name: skill_id,
    description: "",
    capabilities: [],
  }))
}

/** Silent picker read: the picker owns its loading/error presentation. */
export async function fetchChatSkills(
  signal?: AbortSignal,
): Promise<ChatSkillsResponse> {
  try {
    const res = await apiFetch("/api/v1/chat/skills", {
      method: "GET",
      toast: false,
      signal,
    })
    if (res.ok) return (await res.json()) as ChatSkillsResponse
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error
  }
  return { items: localBuiltinSkillOptions() }
}

/** A slash command starts only at a token boundary. Restricting the query to
 * one path-free token keeps URLs and multi-segment paths out of the picker. */
const SKILL_TRIGGER = /(?:^|\s)\/([\p{L}\p{N}_-]*)$/u

export function skillTriggerQuery(textBeforeCaret: string): string | null {
  const match = textBeforeCaret.match(SKILL_TRIGGER)
  return match ? match[1] : null
}

export function sameSkillReference(
  left: SkillReference,
  right: SkillReference,
): boolean {
  if (left.kind === "builtin" && right.kind === "builtin") {
    return left.skill_id === right.skill_id && left.version === right.version
  }
  if (left.kind === "external" && right.kind === "external") {
    return left.skill_version_id === right.skill_version_id
  }
  return false
}

export function skillOptionForReference(
  reference: SkillReference,
  options: SkillOption[] = [],
): SkillOption {
  const match = options.find((option) =>
    sameSkillReference(reference, option.reference),
  )
  if (match) return match
  return {
    reference,
    skill_id: reference.kind === "builtin" ? reference.skill_id : "",
    name: reference.kind === "builtin" ? reference.skill_id : "",
    description: "",
    capabilities: [],
  }
}

export function filterSkillOptions(
  options: SkillOption[],
  query: string,
  displayName: (option: SkillOption) => string = (option) => option.name,
): SkillOption[] {
  const q = query.trim().toLowerCase()
  if (!q) return options
  return options.filter((option) =>
    [displayName(option), option.name, option.skill_id, option.description, ...option.capabilities]
      .join(" ")
      .toLowerCase()
      .includes(q),
  )
}

/** One localized display face for picker, live chip, Home product tabs and
 * history fallback. The immutable reference and server name stay unchanged. */
export function skillDisplayName(
  option: SkillOption,
  t: (key: string, options?: { defaultValue?: string }) => string,
  form: "full" | "short" = "full",
): string {
  if (option.reference.kind === "builtin") {
    const id = option.reference.skill_id
    return t(`skills.builtin.${id}.${form === "short" ? "shortName" : "name"}`, {
      defaultValue: option.name || id,
    })
  }
  return option.name || t("skills.external")
}

function absolutizeFontUrls(spec: VideoSpec): VideoSpec {
  const base = API_URL.replace(/\/$/, "")
  return {
    ...spec,
    fonts: spec.fonts.map((font) => ({
      ...font,
      url: font.url.startsWith("/") ? `${base}${font.url}` : font.url,
    })),
  }
}

export async function fetchSlotPreview(
  skillVersionId: string,
  params: {
    stylePreset?: StylePresetId
    accentColor?: string
    locale?: "zh" | "en"
  } = {},
  signal?: AbortSignal,
): Promise<SlotPreviewResponse> {
  const search = new URLSearchParams()
  if (params.stylePreset) search.set("style_preset", params.stylePreset)
  if (params.accentColor) search.set("accent_color", params.accentColor)
  if (params.locale) search.set("locale", params.locale)
  const qs = search.toString()
  const res = await apiFetch(
    `/api/v1/skills/${encodeURIComponent(skillVersionId)}/slot-preview${qs ? `?${qs}` : ""}`,
    {
      method: "GET",
      toast: false,
      signal,
    },
  )
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail =
      body && typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`
    throw new Error(detail)
  }
  const data = (await res.json()) as SlotPreviewResponse
  return {
    ...data,
    video_spec: absolutizeFontUrls(data.video_spec),
  }
}

export async function exportSlotPreviewMp4(
  skillVersionId: string,
  body: {
    style_preset?: StylePresetId
    accent_color?: string
    locale: "zh" | "en"
    include_sfx?: boolean
  },
): Promise<{ blob: Blob; filename: string }> {
  const res = await apiFetch(
    `/api/v1/skills/${encodeURIComponent(skillVersionId)}/slot-preview/export`,
    {
      method: "POST",
      body,
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => null)
    const detail =
      err && typeof err.detail === "string" ? err.detail : `HTTP ${res.status}`
    throw new Error(detail)
  }
  const disposition = res.headers.get("content-disposition") || ""
  const match = /filename="([^"]+)"/.exec(disposition)
  const filename = match?.[1] || `slot-promo-${body.locale}.mp4`
  const blob = await res.blob()
  return { blob, filename }
}
