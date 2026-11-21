import type { BuiltInSkillReference } from "@/lib/skills"

const HANDOFF_KEY = "repurposer:landing-create"

export type LandingCreateHandoff = {
  skill: BuiltInSkillReference | null
  promptKey: string
}

/** The landing only stages a composer draft. Login/navigation never sends it. */
export function stageLandingCreate(handoff: LandingCreateHandoff): void {
  try {
    window.sessionStorage.setItem(HANDOFF_KEY, JSON.stringify(handoff))
  } catch {
    // A blocked store only loses the handoff; it never blocks login itself.
  }
}

export function consumeLandingCreate(): LandingCreateHandoff | null {
  try {
    const raw = window.sessionStorage.getItem(HANDOFF_KEY)
    if (!raw) return null
    window.sessionStorage.removeItem(HANDOFF_KEY)
    const value = JSON.parse(raw) as Partial<LandingCreateHandoff>
    if (
      (value.skill !== null && (value.skill?.kind !== "builtin" ||
        typeof value.skill.skill_id !== "string" || typeof value.skill.version !== "string")) ||
      typeof value.promptKey !== "string" ||
      !value.promptKey.startsWith("landing.gallery.items.")
    ) {
      return null
    }
    return { promptKey: value.promptKey, skill: value.skill?.skill_id === "text-animation" ? null : value.skill }
  } catch {
    return null
  }
}
