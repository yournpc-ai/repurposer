import { apiFetch } from "@/lib/api"
import type { SkillOption } from "@/lib/skills"

export type StepPlanStatus = "pending" | "in_progress" | "done" | "skipped" | "failed"

export interface StepPlanItem {
  title: string
  status: StepPlanStatus
}

export type MessageFeedbackRating = "good" | "bad"

export const FEEDBACK_TAGS = [
  "visual_quality",
  "pacing",
  "copy",
  "misunderstood",
  "tool_error",
] as const

export type FeedbackTag = (typeof FEEDBACK_TAGS)[number]

export interface MessageFeedbackSummary {
  rating: MessageFeedbackRating
  reason?: string | null
  tags: string[]
  updated_at?: string | null
}

export interface CompactSummary {
  summary: string
  key_decisions: string[]
  compacted_through_seq: number
  compacted_at: string
  message_count: number
}

export interface CompactConversationResponse extends CompactSummary {
  conversation_id: string
}

export interface ProjectConversationSummary {
  id: string
  project_id: string
  title: string
  created_at: string
  updated_at: string | null
  message_count: number
  has_active_job: boolean
  compacted: boolean
  compacted_at: string | null
}

export interface WorkbenchVersion {
  version_id: string
  version: number
  duration_seconds: number
  style_preset: string | null
  is_head: boolean
  created_at: string | null
}

export interface WorkbenchComposition {
  composition_id: string
  name: string | null
  current_version_id: string | null
  versions: WorkbenchVersion[]
}

export interface WorkbenchOutput {
  id: string
  type: string
  status: string
  files: Record<string, string | null | undefined>
  composition_id: string | null
  composition_version_id: string | null
  created_at: string | null
}

export interface WorkbenchAsset {
  id: string
  type: string
  title: string | null
  file_url: string | null
  processing_status: string
  meta: Record<string, unknown>
  created_at: string | null
}

export type WorkbenchActiveJobKind =
  | "export"
  | "image"
  | "voice"
  | "music"
  | "asset_processing"
  | string

export interface WorkbenchActiveJob {
  job_id: string
  kind: WorkbenchActiveJobKind
  status: "queued" | "running" | string
  label_key?: string
  conversation_id: string | null
  receipt_id: string | null
  target_version_id: string | null
  created_at: string | null
}

export interface WorkbenchData {
  project: {
    id: string
    title: string
    language: string | null
    status: string
    updated_at: string | null
  }
  compositions: WorkbenchComposition[]
  outputs: WorkbenchOutput[]
  assets: WorkbenchAsset[]
  active_jobs: WorkbenchActiveJob[]
  skills: SkillOption[]
}

export const CONVERSATIONS_CHANGED_EVENT = "repurposer:conversations-changed"

export function notifyConversationsChanged(projectId: string) {
  if (typeof window === "undefined") return
  window.dispatchEvent(
    new CustomEvent(CONVERSATIONS_CHANGED_EVENT, { detail: { projectId } }),
  )
}

export async function listProjectConversations(
  projectId: string,
  signal?: AbortSignal,
): Promise<ProjectConversationSummary[]> {
  const res = await apiFetch(`/api/v1/projects/${projectId}/conversations`, {
    toast: false,
    signal,
  })
  if (!res.ok) throw new Error("Failed to load conversations")
  return (await res.json()) as ProjectConversationSummary[]
}

export async function createProjectConversation(
  projectId: string,
  title?: string,
): Promise<ProjectConversationSummary> {
  const res = await apiFetch(`/api/v1/projects/${projectId}/conversations`, {
    method: "POST",
    body: title ? { title } : {},
  })
  if (!res.ok) throw new Error("Failed to create conversation")
  const created = (await res.json()) as ProjectConversationSummary
  notifyConversationsChanged(projectId)
  return created
}

export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<ProjectConversationSummary> {
  const res = await apiFetch(`/api/v1/chat/conversations/${conversationId}`, {
    method: "PATCH",
    body: { title },
  })
  if (!res.ok) throw new Error("Failed to rename conversation")
  const updated = (await res.json()) as ProjectConversationSummary
  notifyConversationsChanged(updated.project_id)
  return updated
}

export async function compactConversation(
  conversationId: string,
  projectId?: string,
): Promise<CompactConversationResponse> {
  const res = await apiFetch(`/api/v1/chat/conversations/${conversationId}/compact`, {
    method: "POST",
  })
  if (!res.ok) throw new Error("Failed to compact conversation")
  const data = (await res.json()) as CompactConversationResponse
  if (projectId) notifyConversationsChanged(projectId)
  return data
}

export async function submitMessageFeedback(
  messageId: string,
  payload: {
    rating: MessageFeedbackRating | null
    reason?: string | null
    tags?: string[]
  },
): Promise<{ message_id: string; feedback: MessageFeedbackSummary | null }> {
  const res = await apiFetch(`/api/v1/chat/messages/${messageId}/feedback`, {
    method: "POST",
    body: payload,
    toast: false,
  })
  if (!res.ok) throw new Error("Failed to submit feedback")
  return (await res.json()) as {
    message_id: string
    feedback: MessageFeedbackSummary | null
  }
}

export async function fetchProjectWorkbench(
  projectId: string,
  signal?: AbortSignal,
): Promise<WorkbenchData> {
  const res = await apiFetch(`/api/v1/projects/${projectId}/workbench`, {
    toast: false,
    signal,
  })
  if (!res.ok) throw new Error("Failed to load workbench")
  return (await res.json()) as WorkbenchData
}

/** Concise relative timestamp shared by message action bars and conversation rows. */
export function formatRelativeTime(
  iso: string | null | undefined,
  t: (key: string, options?: Record<string, unknown>) => string,
  nowMs: number = Date.now(),
): string {
  if (!iso) return ""
  const parsed = Date.parse(iso)
  if (Number.isNaN(parsed)) return ""
  const diffSec = Math.max(0, Math.floor((nowMs - parsed) / 1000))
  if (diffSec < 45) return t("notifications.justNow")
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return t("notifications.minutesAgo", { count: diffMin })
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return t("notifications.hoursAgo", { count: diffHr })
  const diffDays = Math.floor(diffHr / 24)
  return t("notifications.daysAgo", { count: diffDays })
}
