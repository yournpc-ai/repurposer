export type MessageRole = "user" | "assistant" | "system"

export type MessageStatus = "pending" | "running" | "completed" | "failed"

export interface ChatAttachment {
  id: string
  name: string
  type: "file" | "image" | "video" | "audio"
  url?: string
  size?: number
  status: "uploading" | "uploaded" | "failed"
}

export interface ChatMarker {
  id: string
  type: "status" | "tool" | "separator" | "error"
  label: string
  timestamp?: string
  meta?: Record<string, unknown>
}

export interface ChatMessageMeta {
  status?: MessageStatus
  progress?: number
  currentStep?: string
  markers?: ChatMarker[]
  results?: {
    clip_ids?: string[]
    derivative_ids?: string[]
  }
  error?: string
  params?: Record<string, unknown>
}

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  attachments: ChatAttachment[]
  meta: ChatMessageMeta
  parentMessageId?: string
  createdAt: string
  updatedAt?: string
}

export interface ChatThread {
  projectId: string | null
  title: string
  messages: ChatMessage[]
  isGenerating: boolean
  error: string | null
}

export type Tone =
  | "professional"
  | "thoughtLeadership"
  | "conversational"
  | "academic"

export interface Project {
  id: string
  title: string
  status: string
  persona_id: string | null
  event_name: string | null
  language: string
  created_at: string
}

export interface Persona {
  id: string
  name: string
  title?: string | null
  avatar_url?: string | null
  sentence_style?: string
  emotional_tone?: "rational" | "passionate" | "gentle" | "sharp" | "humorous"
}

export interface Asset {
  id: string
  type: string
  file_url: string | null
  extracted_text: string | null
  transcript: string | null
  processing_status: string
  processing_error: string | null
  created_at: string
}

export interface OutputPayload {
  // clip
  hook?: string
  title_options?: string[]
  music_mood?: string
  duration?: number
  // post / article
  content?: string
  hashtags?: string[]
  title?: string
  // quotes
  quotes?: { quote: string; attribution: string }[]
  // carousel
  slides?: { title: string; body?: string }[]
  // article extras
  tldr?: string
  key_points?: string[]
  full?: string
}

export interface OutputFiles {
  video?: string
  srt?: string
  image?: string
}

export interface OutputSourceRef {
  segment?: Record<string, unknown>
  start_seconds?: number | null
  end_seconds?: number | null
  asset_id?: string | null
}

export interface OutputPublishing {
  title?: string | null
  description?: string | null
  hashtags?: string[] | null
  cover_image_url?: string | null
  topic?: string | null
}

/** First-post recommendation score (1-100) + one-sentence reason — answers
 * "which clip is most worth posting first", never predicts views/reach. */
export interface OutputScore {
  value?: number
  reason?: string | null
}

/** Unified product row (ADR-030): a clip is the type carrying timeline
 * semantics (source_ref) and the render pipeline; derivatives are plain
 * types. Creative fields live in payload, artifacts in files, publish
 * metadata in publishing. */
export interface Output {
  id: string
  project_id: string
  workflow_step_id: string | null
  type: string
  language: string
  status: string
  provenance: string
  payload: OutputPayload
  files: OutputFiles
  source_ref: OutputSourceRef | null
  render_spec: unknown | null
  render_status: string | null
  render_error: string | null
  score: OutputScore | null
  publishing: OutputPublishing
  created_at: string
  updated_at: string | null
}

export type StepStatus = "pending" | "running" | "done" | "failed" | "skipped" | "waiting"

export type IntentSlotType = "clips" | "post" | "quotes" | "carousel" | "article"

/** 任务槽 (IntentSlot, N-20 request layer): one line of the task book — one
 * requested output. `null` fields mean task-book defaults (count → per-type
 * default, language → the run's target language); `explicit` marks
 * user-edited slots that pin through re-inference. */
export interface IntentSlot {
  type: IntentSlotType
  count: number | null
  focus: string | null
  language: string | null
  tone_override: string | null
  explicit: boolean
}

/** One step of a run's execution plan (ADR-028) — the user-facing step. */
export interface WorkflowStep {
  id: string
  kind: string
  status: StepStatus
  seq: number
  error: string | null
  cost: Record<string, number> | null
  stage?: string | null
  /** Quantified one-liner (e.g. "Selected 3 clips · 87s total"). */
  summary?: string | null
  /** Output row ids this node produced (RunCard inlines these on completion). */
  output_refs?: string[]
  started_at: string | null
  finished_at: string | null
}

export interface BrandTemplate {
  id: string
  name: string
  config: {
    captionColor?: string
  }
}

// ── Distribution ────────────────────────────────────────────────────────────

export type ChannelPlatform = "linkedin" | "tiktok"

export interface ChannelAccount {
  id: string
  platform: ChannelPlatform
  platform_user_id: string
  display_name: string
  avatar_url: string | null
  scopes: string[]
  status: "active" | "expired" | "revoked"
  token_expires_at: string | null
  created_at: string | null
}

export interface PlatformAvailability {
  platform: ChannelPlatform
  configured: boolean
}

export type PublicationState =
  | "draft"
  | "pending_review"
  | "approved"
  | "scheduled"
  | "publishing"
  | "published"
  | "failed"
  | "cancelled"

// ── Notifications ───────────────────────────────────────────────────────────

export type NotificationType =
  | "publish_succeeded"
  | "publish_failed"
  | "channel_expired"

export interface NotificationPayload {
  publication_id?: string
  project_id?: string
  output_id?: string
  platform?: ChannelPlatform
  title?: string
  platform_post_url?: string | null
  channel_account_id?: string
  error?: string
}

export interface AppNotification {
  id: string
  type: NotificationType | string
  payload: NotificationPayload
  read_at: string | null
  created_at: string | null
}

export interface NotificationList {
  items: AppNotification[]
  unread_count: number
}

