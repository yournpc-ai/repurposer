import { apiFetch } from "@/lib/api"

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

export interface SkillOption {
  reference: SkillReference
  skill_id: string
  name: string
  description: string
  capabilities: string[]
  version_number?: number | null
}

export interface ChatSkillsResponse {
  items: SkillOption[]
}

/** Silent picker read: the picker owns its loading/error presentation. */
export async function fetchChatSkills(
  signal?: AbortSignal,
): Promise<ChatSkillsResponse> {
  const res = await apiFetch("/api/v1/chat/skills", {
    method: "GET",
    toast: false,
    signal,
  })
  if (!res.ok) throw new Error("chat_skills_unavailable")
  return (await res.json()) as ChatSkillsResponse
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
): SkillOption[] {
  const q = query.trim().toLowerCase()
  if (!q) return options
  return options.filter((option) =>
    [option.name, option.skill_id, option.description, ...option.capabilities]
      .join(" ")
      .toLowerCase()
      .includes(q),
  )
}
