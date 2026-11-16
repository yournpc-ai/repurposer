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
  name?: string
  duration_seconds?: number
  duration?: number
  aspect?: string | null
  content_language?: string | null
  execution_digest?: string | null
  composition_digest?: string
  generator_media?: Record<string, unknown>
  speech_media?: Record<string, unknown>
  narration_policy?: Record<string, unknown> | null
}

export interface OutputFiles {
  video?: string
  image?: string
}

export interface OutputSourceRef {
  segment?: Record<string, unknown>
  start_seconds?: number | null
  end_seconds?: number | null
  asset_id?: string | null
  /** Lineage (quote-cards §2.2, 2026-08-28): parent Output ids this
   * product derives from — the chain composite names its frame cards,
   * the motion clip names the composite. The flow canvas draws N→1
   * lineage edges off this. */
  parents?: string[]
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
/** Advisory frame-evidenced review of one exact delivered video Output. */
export interface OutputContentReview {
  output_id: string
  composition_version_id: string
  video_sha256: string
  summary: string
  scope: {
    actual_output_decoded: boolean
    static_frames_checked: boolean
    motion_and_transitions_checked: boolean
    audio_and_av_sync_checked: boolean
  }
  limitations: string[]
  frames: { frame_id: string; time_seconds: number; frame: number }[]
  findings: {
    kind: "observed_issue" | "aesthetic_suggestion"
    frame_id: string
    time_seconds: number
    frame: number
    observed: string
    requirement: string
    evidence: string
    suggestion: string
    clip_id: string | null
    object_id: string | null
  }[]
}
export interface OutputQuality {
  content_review?: OutputContentReview
}

export interface Output {
  id: string
  project_id: string
  workflow_step_id: string | null
  type: string
  /** null = unpinned (legacy rows / the scrubbed null-as-string plan token)
   * — the factsbar's language chip simply stays off. */
  language: string | null
  status: string
  provenance: string
  /** Exact composition lineage; archived history remains readable by id. */
  work_id?: string | null
  archived_at?: string | null
  composition_id?: string | null
  composition_version_id?: string | null
  /** Real CompositionVersion.version; repeated deliveries may share it. */
  composition_version_number?: number | null
  payload: OutputPayload
  files: OutputFiles
  source_ref: OutputSourceRef | null
  render_spec: unknown | null
  render_status: string | null
  render_error: string | null
  quality: OutputQuality | null
  publishing: OutputPublishing
  /** Server-derived display aspect (产物展示统一, 2026-08-27): "9:16" |
   * "1:1" | "16:9" | arbitrary "W:H"; null = unknown/original frame —
   * surfaces fall back to their default tier. Never probe when set. */
  aspect?: string | null
  created_at: string
  updated_at: string | null
}

export interface ChatOutputEntry {
  output_id: string
  /** Null = the persisted exact reference is unavailable; never substitute latest. */
  output: Output | null
}

export type StepStatus = "pending" | "running" | "done" | "failed" | "skipped" | "waiting"

/** One safe, replayable produce_video stage inside a step attempt. */
export interface ProductionStage {
  event_id: string
  kind: string
  run_id: string
  step_id: string
  attempt: number
  seq: number
  status: "running" | "completed" | "failed"
  started_at: string
  finished_at: string | null
  reused?: boolean | null
  item_count?: number | null
  reused_count?: number | null
}

/** One step of a run's execution plan (ADR-028) — the user-facing step. */
export interface WorkflowStep {
  id: string
  kind: string
  status: StepStatus
  seq: number
  attempt?: number
  error: string | null
  cost: Record<string, number> | null
  stage?: string | null
  /** Quantified one-liner (e.g. "Selected 3 clips · 87s total"). */
  summary?: string | null
  /** The runner's structured "nothing to do" declaration (2026-09-10 receipt
   * whisper tier) — stamped at the same seat as the "…skipped" summary. */
  noop?: boolean | null
  /** Output row ids this node produced (execution/delivery facts, not Chat ownership). */
  output_refs?: string[]
  /** DAG edges: upstream step ids (the run's execution DAG). */
  inputs?: string[]
  /** Credits derivation (ADR-055, BILLING §7 — serialization-folded, never
   * persisted): the step's quotation [low, high] / metered actual in
   * credits. estimate_credits null = never quoted; cost_credits null =
   * nothing metered yet. */
  estimate_credits?: [number, number] | null
  cost_credits?: number | null
  started_at: string | null
  finished_at: string | null
  production_stages?: ProductionStage[]
}

/** The project graph (ADR-057) — the persistent, mutable product object the
 * canvas reads directly (`GET /projects/{id}/graph`; zero projection — the
 * display model IS the domain model). Node five-types; state is an
 * orthogonal dimension; edges are typed flows (the port law: in = the
 * consumption region's bottom-left, out = the production region's
 * top-right). */
// Source assets and ordinary manual nodes use these five media types.
export type GraphNodeType =
  | "text"
  | "table"
  | "image"
  | "video"
  | "audio"

export type GraphNodeState = "draft" | "done"

export type GraphEdgeType = "video" | "audio" | "text" | "ctx"

/** The asset row joined onto an asset node (AssetResponse passthrough). */
export interface GraphNodeAsset {
  id: string
  type: string
  title: string | null
  file_url: string | null
  stream_url?: string | null
  duration_seconds?: number | null
  /** The owning project — the transcript endpoint's path seat (ADR-113). */
  project_id?: string | null
  /** Processing truth (ADR-113): the transcript section gates its face on
   * it — mid-processing never shows the empty face (that would lie), and a
   * terminal flip invalidates the section's cached read. */
  processing_status?: string | null
  processing_stage?: string | null
  /** The media's real pixels (meta.width/height — probed at upload /
   * processing); the canvas's aspect truth for the asset node's shape. */
  width?: number | null
  height?: number | null
  created_at?: string
}

export interface GraphNode {
  id: string
  type: GraphNodeType
  state: GraphNodeState
  spec: {
    summary?: string | null
    title?: string | null
    prompt?: string | null
    text?: string | null
    prototype?: "manual"
    [key: string]: unknown
  }
  layout?: { x?: number; y?: number; w?: number; h?: number } | null
  asset?: GraphNodeAsset | null
  created_at: string
  updated_at?: string | null
}

export interface GraphEdge {
  id: string
  from_node: string
  from_port: string
  to_node: string
  to_port: string
  edge_type: GraphEdgeType
}

export interface ProjectGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  lifecycle?: LifecycleStamp | null
}

/** The server-named lifecycle projection (ADR-087 §2, Phase 1) — the ONE
 * readiness truth every client surface reads (canvas / confirm / chat);
 * clients never derive lifecycle from artifact existence. The four
 * CONFIRMATION_READY conjuncts are independent fields; `state` is the
 * presentation rollup, `blockers` the first-class reason channel. */
export interface LifecycleStamp {
  state: "preparing" | "plan_ready" | "confirmation_ready" | "running"
  material_ready: boolean
  plan_ready: boolean
  confirmation_scope_ready: boolean
  charge_semantics_ready: boolean
  no_active_conflicting_run: boolean
  confirmation_ready: boolean
  blockers: string[]
  charge: { known: [number, number] | null; deferred: boolean }
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

