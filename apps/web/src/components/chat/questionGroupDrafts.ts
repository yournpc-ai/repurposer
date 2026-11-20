import type { BriefAnswerItem } from "./timeline/types"

const PREFIX = "repurposer.chat.question-group-drafts.v1"

function storageKey(projectId: string) {
  return `${PREFIX}:${projectId}`
}

export function loadQuestionGroupDrafts(projectId: string): Record<string, BriefAnswerItem[]> {
  if (typeof window === "undefined") return {}
  try {
    const raw = window.sessionStorage.getItem(storageKey(projectId))
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed).filter((entry): entry is [string, BriefAnswerItem[]] =>
        !!entry[0] && Array.isArray(entry[1])
      ),
    )
  } catch {
    return {}
  }
}

export function saveQuestionGroupDrafts(
  projectId: string,
  drafts: Record<string, BriefAnswerItem[]>,
) {
  if (typeof window === "undefined") return
  try {
    if (Object.keys(drafts).length === 0) {
      window.sessionStorage.removeItem(storageKey(projectId))
    } else {
      window.sessionStorage.setItem(storageKey(projectId), JSON.stringify(drafts))
    }
  } catch {
    // Storage quotas or privacy settings must not block answering the question.
  }
}
