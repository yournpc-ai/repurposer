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
  speaker_id: string | null
  event_name: string | null
  language: string
  created_at: string
  is_demo?: boolean
}

export interface Speaker {
  id: string
  name: string
  title?: string | null
  persona?: {
    emotional_tone?: string
    sentence_style?: string
  } | null
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

/** Unified product row (ADR-030): a clip is the type carrying timeline
 * semantics (source_ref) and the render pipeline; derivatives are plain
 * types. Creative fields live in payload, artifacts in files, publish
 * metadata in publishing. */
export interface Output {
  id: string
  project_id: string
  plan_node_id: string | null
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
  score: Record<string, unknown> | null
  publishing: OutputPublishing
  created_at: string
  updated_at: string | null
}

export type PlanNodeStatus = "pending" | "running" | "done" | "failed" | "skipped"

/** One node of a run's execution plan (ADR-028) — the user-facing step. */
export interface PlanNode {
  id: string
  kind: string
  status: PlanNodeStatus
  seq: number
  error: string | null
  cost: Record<string, number> | null
  stage?: string | null
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
