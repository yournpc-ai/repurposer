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
  // quote_frame (single card: quote + attribution mirror the baked PNG's
  // text; aspect pin feeds the server-derived Output.aspect)
  quote?: string
  attribution?: string
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
  /** Lineage (quote-cards §2.2, 2026-08-28): parent Output ids this
   * product derives from — the chain composite names its frame cards,
   * the motion clip names the composite. The flow canvas draws N→1
   * lineage edges off this. */
  parents?: string[]
  /** quote_frame / quote_chain markers ride source_ref verbatim — the
   * canvas distinguishes the composite (quote_chain) from frame cards. */
  quote_frame?: boolean
  quote_chain?: boolean
  /** Fork lineage (translate/dub "再来一版"): the output THIS row was
   * derived from. The fork family it forms (ADR-051 F2 变体分页) is the
   * version-pager's data — distinct from `parents` (sub-artifact lineage). */
  derived_from_output_id?: string
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
/** 质检裁决 (产物质量线期 3): the verify node's verdict on the product row.
 * null = never verified (legacy rows / verify-less graphs). needs_human is
 * non-blocking — the badge is the only surface (成功安静). */
export interface OutputQuality {
  status: "passed" | "needs_human"
  checks: { id: string; ok: boolean | null; detail: string; cls: string }[]
  attempt: number
  checked_at: string
}

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
  quality: OutputQuality | null
  publishing: OutputPublishing
  /** Server-derived display aspect (产物展示统一, 2026-08-27): "9:16" |
   * "1:1" | "16:9" | arbitrary "W:H"; null = unknown/original frame —
   * surfaces fall back to their default tier. Never probe when set. */
  aspect?: string | null
  /** The product's own spec as a prompt-style line (ADR-051 F — hover
   * prompt 框): composed server-side from the producing step's slot/params
   * in the run's pinned ui_language; stamped only by /results. The card's
   * hover 框 prefills with it; null = carried row (the 框 opens empty). */
  spec_prompt?: string | null
  /** The product's model/provider facts (ADR-051 H — 详情面模型事实):
   * server-projected from the producing step's kind (a fact registry, never
   * a selector); stamped only by /results. The lightbox info column is the
   * display surface — the node caption never carries a model name. */
  model_facts?: ModelFact[] | null
  created_at: string
  updated_at: string | null
}

/** One model/provider fact about a product (ADR-051 H): `modality` is the
 * grouping key (copy / voice / captions / music — localized via the composer
 * models panel's keys); `model` is the display name, DATA (a proper noun). */
export interface ModelFact {
  modality: string
  model: string
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
}

/** The project graph (ADR-057) — the persistent, mutable product object the
 * canvas reads directly (`GET /projects/{id}/graph`; zero projection — the
 * display model IS the domain model). Node five-types; state is an
 * orthogonal dimension; edges are typed flows (the port law: in = the
 * consumption region's bottom-left, out = the production region's
 * top-right). */
export type GraphNodeKind = "asset" | "document" | "generator" | "processor" | "agent"

export type GraphNodeState =
  | "draft"
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "skipped"
  | "stale"

export type GraphEdgeType = "video" | "audio" | "text" | "ctx"

/** The asset row joined onto an asset node (AssetResponse passthrough). */
export interface GraphNodeAsset {
  id: string
  type: string
  title: string | null
  file_url: string | null
  stream_url?: string | null
  duration_seconds?: number | null
  created_at?: string
}

export interface GraphNode {
  id: string
  kind: GraphNodeKind
  state: GraphNodeState
  /** The node's program: prompt / params / role / fill_key / frame_class /
   * summary — the node type's own shape, rendered as-is. */
  spec: {
    summary?: string | null
    prompt?: string | null
    params?: Record<string, unknown> | null
    role?: string | null
    text?: string | null
    asset_id?: string | null
    asset_type?: string | null
    title?: string | null
    output_ids?: string[]
    frame_class?: string | null
    [key: string]: unknown
  }
  /** 画布定居取景: the settled frame {x, y, w, h} — server-assigned once,
   * append-only; existing frames never move. */
  layout: { x?: number; y?: number; w?: number; h?: number }
  /** The node's quotation folded to credits at read time (BILLING §7);
   * null = unquoted. */
  estimate_credits?: [number, number] | null
  /** Asset nodes: the joined asset row. */
  asset?: GraphNodeAsset | null
  /** Producer nodes: the joined visible product rows (created_at asc — the
   * card's pager order). */
  outputs?: Output[]
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

