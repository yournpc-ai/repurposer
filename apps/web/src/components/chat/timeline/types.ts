import type { Output } from "@/lib/types"
import type { CreditTopupRequest } from "@/lib/credits"
import type { SkillReference } from "@/lib/skills"

/** Shared Chat timeline vocabulary. Pure types only: no React, transport, or
 * layout dependency. Persisted array order and `birthKey ?? id` remain the
 * identity laws for every projection consuming these rows. */

/** One user-safe activity frame (ADR-087 §3 Phase 2 — the append-oriented
 * Activity Stream). Status flips arrive as NEW frames carrying the same
 * `activity_id` (append-only wire; the client keeps an ordered map keyed by
 * id). `kind` is a user-semantic category — never a tool name; `key` is the
 * i18n copy identity for THAT status (active = progressive form, completed =
 * past-tense form, failed/cancelled = the active form, the ✗ says the rest).
 * The field set is the contract's whitelist — no params, raw results, or
 * reasoning; the accepted video review's typed receipt is the sole exception. */
export interface ActivityFramePayload {
  activity_id: string
  seq: number
  kind: "read" | "draft" | "run" | "repair"
  status: "active" | "completed" | "failed" | "cancelled"
  key: string | null
  /** 工作会话里程碑 (iter-2 ⑥, N-57): the whitelist's one extension — the
   * artifact count on `chat.explore.*Ready` frames, absent elsewhere. */
  count?: number
  /** iter-3 S7 (E7, N-58 ⑥): the frame's birth stamp (ISO, every frame).
   * ADR-108 后它是**展示戳**——持久化行的诚实出生时刻（open append 的
   * `at` = execute 入口重锚点）；渲染顺序永远来自数组位置（seq），此戳
   * 不参与排序。The reducer replaces frames wholesale — the latest frame's
   * `at` wins, no field-level merging. */
  at?: string
  /** iter-3 S7 (E7): the real elapsed of a genuinely-active span, present
   * only on its settling frame — a born-completed milestone is an instant
   * fact and carries none. Read/repair spans anchor the elapsed at EXECUTE
   * entry (the honest-duration re-anchor), not at the mid-generation
   * name_known beat. */
  duration_ms?: number
  /** Accepted video review's typed evidence; never a raw tool result dump. */
  receipt?: VideoReviewReceipt
}

export type VideoReviewIssueCode =
  | "AUDIO_MISSING"
  | "AUDIO_DECODE_FAILED"
  | "AUDIO_SILENT"
  | "AUDIO_QUIET"
  | "AUDIO_CLIPPED"

export interface VideoReviewReceipt {
  kind: "video_review"
  frames: { frame_id: string; time_seconds: number }[]
  findings: {
    kind: "observed_issue" | "aesthetic_suggestion"
    frame_id: string
    observed: string
  }[]
  output_issue_codes: VideoReviewIssueCode[]
  scope: {
    actual_output_decoded: boolean
    static_frames_checked: boolean
    deterministic_output_checks: boolean
    sampled_frame_signals_checked: boolean
    audio_signal_checked: boolean
    motion_and_transitions_checked: boolean
    audio_and_av_sync_checked: boolean
  }
}

/** Candidate Surface (Workspace 合同 v4.2 C8-c, 2026-09-26) — one candidate
 * member: the source range + the source-faithful excerpt (C4 锚链) + the
 * speaker when the ASR named one. The ordinal IS the member's array index
 * (0-based on the wire; the card renders the two-digit visual address). */
export interface CandidateMemberPayload {
  start: number
  end: number
  excerpt: string
  speaker?: string | null
  /** Optional SFX facts. Their presence never changes transcript candidates. */
  provider?: "freesound" | string | null
  provider_id?: string | null
  title?: string | null
  author?: string | null
  duration_seconds?: number | null
  source_url?: string | null
  preview_url?: string | null
  license?: string | null
  attribution?: string | null
  query?: string | null
}

/** The typed answer payload mirrored from the API (messages.answer). */
export interface QuestionAnswer {
  kind: "option" | "freeform" | "bail" | "start"
  option_id?: string | null
  text?: string | null
  answered_at?: string
}

/** One persisted activity row's render frame (ADR-108 数组行): the
 * transcript array's activity entries — per-frame rows written at
 * open/settle (intent.type === "activity") and the born-settled material
 * beats (intent.type === "material_beat") share this shape. Array position
 * IS the order, so the live-channel `seq` bookkeeping is optional here;
 * `name`/`total` ride the beats' interpolation fields. */
export type ActivityRowFrame = Omit<ActivityFramePayload, "seq"> & {
  seq?: number
  name?: string
  total?: number
  /** The material beat's asset type (回放层解析字段, never on the SSE wire
   * whitelist): the settled surface's category fork needs it for web_page
   * beats — their row key falls to the base form (the verb fork predates
   * the web_page type). */
  assetType?: string
}

/** A structured presentation block stamped on an assistant row (Video
 * Project phase B): a REFERENCE the named component resolves to its server
 * DTO — never the payload itself. Unknown kinds render nothing (读容忍). */
export interface VideoStoryboardBlock {
  presented_message_id?: string
  kind: "video_storyboard"
  composition_id: string
  composition_version_id: string
  version: number
  content_digest?: string
  presentation_digest?: string
  /** Server-persisted completion receipt; old/live blocks omit it until the
   * presentation ACK lands. */
  presentation_complete?: boolean
}

/** One message row in the dock's flow (live-pushed or replayed). */
export interface OverlayMessage {
  id: string
  /** The RENDER key law (2026-10-19 interim_prose-flicker fix): React keys the
   * flow by `birthKey ?? id`. Stamped ONCE at birth for rows whose semantic
   * id can be PROMOTED mid-life — the interim_prose settle renames a streamed
   * bubble `streamId → ${streamId}#ipN` (settleStreamedSegment), and an
   * id-keyed list remounts there, replaying the entrance animation (the
   * visible blink). The rename spreads `...m`, so the birthKey survives the
   * promotion and the row never remounts. Rows without it key by `id`,
   * which never changes for them. */
  birthKey?: string
  role: "user" | "assistant"
  content: string
  skill?: SkillReference
  /** Opening user-message id for facts born in that turn. Missing on legacy
   * rows and independent world facts; never inferred from adjacency. */
  turnId?: string
  /** A deterministic option answer's persisted question association. The real
   * user row still owns the Turn; only its duplicate visible bubble is suppressed. */
  answeredQuestionId?: string
  /** Facts that keep their own block type even when they carry a turn
   * association (QA/candidate), or have no user-turn owner (trigger/material). */
  independentKind?: "qa" | "candidate" | "trigger" | "material"
  runId?: string | null
  /** A trigger delivery row owns its Run's single historical card seat. */
  runDelivery?: boolean
  /** Persistent trigger ref; upload-retry-N identifies the recovery attempt. */
  runDeliveryRef?: string
  /** Exact products delivered by THIS message. An empty array is an honest
   * zero-delivery result; missing refs never reopen Run-level ownership. */
  outputRefs?: string[]
  /** Server-persisted message id for a live speech/structure row. The local id
   * keeps React/typewriter identity; this id is the only valid Stop frontier key. */
  serverMessageId?: string
  /** All real ids this local row has owned (partial then final). Local-only
   * slow-history dedupe; Stop still reads only serverMessageId above. */
  serverIdAliases?: string[]
  /** The persisted transcript position (messages.seq). Optimistic local rows
   * have none until their envelope stamps it; ordering never substitutes the
   * display timestamp for this server position. */
  seq?: number
  /** Chronological anchor (ISO) — the flow interleaves run blocks and
   * mid-run QA archives by real time (#5: the stream never scrambles).
   * Server-rebuilt items carry the row's created_at; live pushes stamp now. */
  at?: string
  /** Files uploaded mid-conversation (the chat's attach button) — rendered
   * as attachment chips on the user bubble. */
  assets?: ProjectAsset[]
  /** Live SSE preview bubble: deltas append until the turn.completed
   * envelope replaces it (the envelope always wins). */
  streaming?: boolean
  /** Mounted from the persisted history projection: hydrate current state
   * directly, never replay live entrance/typewriter choreography. */
  hydrated?: boolean
  /** CLIENT DISPLAY facts (epoch ms, never loaded from or written to the
   * server). clientVisibleAtMs is stamped when the first non-whitespace
   * prose fragment is actually released (or an optimistic QA block renders);
   * proseDrainedAtMs marks a interim_prose segment's own playback finishing.
   * They are display-lifecycle facts, NOT created_at stand-ins. */
  clientVisibleAtMs?: number
  proseDrainedAtMs?: number
  /** The CURRENT work segment's frozen wall clock, stamped on its first
   * activity host row. Start = send / previous prose drained / first tool
   * fallback; end = first visible following prose or a real terminal state.
   * Tool duration_ms stays independent. Refresh replay has no client display
   * facts and honestly falls back to the observable activity span. */
  workStartedAtMs?: number
  workEndedAtMs?: number
  /** Answered-question item (a settled question collapsing into the flow).
   * `questionId` = the settled row's id — the ask_user 不变量's join key:
   * a question whose QA archive is in the flow is DECIDED and must never
   * also render as the pending dock. */
  qa?: {
    question: string
    answer: string
    muted: boolean
    detail?: string
    questionId?: string
    answerKind?: QuestionAnswer["kind"]
  }
  /** The canvas product this turn was pointed at (ADR-041 D8, WRITE-RETIRED
   * ADR-058 — pointing is an @mention chip now): old server rows still carry
   * messages.focus_output, and the rebuilt history keeps rendering their gray
   * focus prefix row (read tolerance, never written again). */
  focus?: { id: string; label: string }
  /** A turn-failure system row (turn.failed / transport error): renders as
   * the gray MetaRow, never a toast. Local-only — the server commits nothing
   * on a failed turn, so a refresh drops it (the conversation stays honest:
   * nothing was answered). */
  meta?: "error"
  /** Local insufficient-credit action attached to a failed-turn gray row.
   * Never persisted; the row and its purchase context disappear on refresh. */
  creditTopup?: CreditTopupRequest
  /** Trigger-turn suggestion pills — LEGACY REPLAY ONLY (ADR-081,
   * 2026-09-17): rows docked before the option-grammar unification carry
   * pill-shaped suggestions in the intent dump and replay as chips; new
   * rows dock a REAL numbered options question (messages.question payload)
   * instead and this stays undefined/empty. Set only after the row's prose
   * has drained (散文永远在先、提问随后). */
  suggestions?: SuggestionPill[]
  /** 素材节拍 + activity 数组行回放 (ADR-108): a persisted activity entry
   * replays as a SETTLED (or honestly open) activity row IN ITS ARRAY
   * POSITION — never a bubble, never re-sorted. Two intent shapes share the
   * field: {type:"material_beat", …} (the pipeline's reading/understanding
   * beats) and {type:"activity", frame} (the turn's per-frame rows). */
  activity?: ActivityRowFrame
  /** Candidate Surface (Workspace 合同 v4.2 C8-c): the replayed (or live)
   * candidate card — the set's members + the CURRENT selection highlight
   * (folded from every selection event up to this point). The card renders
   * under its anchoring message; selection events from LATER turns repaint
   * it in place (chat 决策永不成节点 — the card is the selection state's
   * one seat). */
  candidates?: CandidateSurface
  /** Structured presentation blocks (Video Project phase B): the
   * storyboard card's resolve references, stamped on the presenting row
   * server-side. Absent/empty on every legacy row (读容忍). */
  blocks?: VideoStoryboardBlock[]
}

/** The candidate card's data (C8-c): ordinal = the member's array index
 * (the visual address the user's 「第二个」 speaks to); `selected` = the
 * set's current selection (0-based member indexes). Self-contained — the
 * payload carries every rendered fact, so a deleted source asset leaves
 * nothing dangling (读面容忍: an off-shape dump simply renders no card). */
export interface CandidateSurface {
  candidateSetId: string
  topic: string
  assetId: string | null
  members: CandidateMemberPayload[]
  selected: number[]
}

/** A legacy trigger row's suggestion pill (pre-ADR-081 rows only): "send"
 * fires the text verbatim as the user's next message; "download" one-taps
 * a landed output. New trigger rows never produce this shape. */
export interface SuggestionPill {
  label: string
  action: "send" | "download"
  text?: string | null
  output_id?: string | null
}

/** Derived preview row (ADR-043): the server dry-run-compiles the chain at
 * dock time and projects what it will MAKE — the card's "you'll get"
 * section. `video` = the whole-source materialization (整条视频). */
export interface DerivedRow {
  type: string
  variant?: "subs" | "dub" | null
  language?: string | null
  count?: number | null
  bilingual?: boolean
}

/** 决策包阅读层 (iter-2 ③, ADR-089 §4 R16): one Content Plan's user-safe
 * summary — the product semantics the agent named (title + outputs),
 * mirrored from the exploration rows. The compiled task chain stays the
 * EVIDENCE layer (expandable under the plans). */
export interface DecisionPlanRow {
  plan_id: string
  title: string
  state: string
  outputs: {
    kind: string
    language?: string | null
    caption_mode?: string | null
    dub?: boolean | null
    aspect?: string | null
    brief?: string | null
  }[]
  issues?: string[]
}

/** The typed question payload mirrored from the API (messages.question). */
export interface QuestionPayload {
  kind: "task_book" | "question"
  /** The BARE question (ask 三分解剖 ②): the dock's title and the QA
   * archive's Q line. Absent on legacy rows and task_book docks — those
   * store the question (or the echo prose) AS the content; every reader
   * falls back to `content`. */
  question?: string
  options?: { id: string; label: string; description?: string }[]
  /** 推荐标记 (2026-09-27 一问拍一体化): at most one option id the agent
   * recommends — the dock renders its muted suffix. Absent on question
   * rows from before B3 (normalizeBrief tolerates). */
  recommended_id?: string | null
  /** The dock's credits quotation (BILLING §7): task_book only — total
   * [low, high] + the per-task marginal range aligned by task index (Σ
   * per_task ≡ total exactly; null = the task adds no quoted cost). */
  estimate_credits?: {
    total: [number, number]
    per_task: ([number, number] | null)[]
  } | null
  /** 预填评审卡 (ADR-052 B3): task_book only — the merged brief at
   * dock time; the plan card renders its valued slots. Absent on question
   * rows from before B3 (normalizeBrief tolerates). */
  brief?: unknown
  /** 计划行自完备 (2026-09-08, 方案 B): task_book only — the derived
   * preview ("you'll get") stamped at dock time. Absent on rows docked
   * before the seal — the recovery pending-brief fetch is the fallback. */
  derived?: DerivedRow[]
  /** task_book only: the needs-clarification reason KEYS (data, localized
   * at render — never baked into the row's content). */
  reasons?: string[]
  /** 授权前移 (ADR-117 §4): task_book only — the presentation-time
   * confirmation stamp. `requires_confirmation` is the Start pill's render
   * source (the client never derives the need itself); absent on rows docked
   * before the stamp (读容忍 → treated as owed: those docks all predated
   * the auto regime). The legacy auto-only `first_draft_review` reason reads as
   * no independent debt. Other `confirm_reason` values key the pill's label
   * family; `quote_high` feeds the priced label; `unquotable` forces the
   * deferred-pricing label (never a fabricated number). */
  requires_confirmation?: boolean
  confirm_reason?: string
  quote_high?: number | null
  unquotable?: boolean
  /** 决策包阅读层 (iter-2 ③): task_book only — the Content Plans behind
   * the compiled chain; empty on the router-drafted docks (读容忍). */
  plans?: DecisionPlanRow[]
  /** 分镜 echo (dock echo 形态): task_book only — the row's content is the
   * film dock's echo (prose + the code-rendered storyboard markdown + the
   * estimate tail), which replays as a normal flow message even while the
   * dock is still pending (the dock itself revives via the pending
   * fetch). Absent on every other dock shape. */
  storyboard_echo?: boolean
}

/** A question-carrying chat message (the ask_user machinery): the dock's pending
 * question and, once answered, its collapsed form in the flow. */
export interface QuestionMessage {
  id: string
  content: string | null
  /** Server-resolved explicit Skill on a user row (including a unique
   * natural-language match); the live row replays this same reference. */
  skill?: SkillReference | null
  /** The row's intent JSONB: task_book docks stamp the presented chain
   * here (计划行自完备, 方案 B — the envelope's row IS the whole plan
   * card, no second fetch); ask questions stash their replay payload.
   * Null on rows docked before the seal. */
  intent?: unknown
  question: QuestionPayload | null
  answer: QuestionAnswer | null
  workflow_run_id: string | null
  /** Opening user-turn association, when this row belongs to one. */
  turn_id?: string | null
  /** 建议谱系交互块 (ADR-099 §4): the row's persisted non-blocking
   * suggestion records (empty on every older row — 读容忍). */
  suggestions?: unknown
  /** Structured presentation blocks (Video Project phase B): the
   * storyboard card's resolve references on the presenting row. */
  blocks?: VideoStoryboardBlock[]
  /** ask 预览帧的乐观 dock (2026-09-09): the ask object closed stream-side
   * but the turn's tail — and with it the row's server-side birth — is
   * still generating, so this id does NOT exist server-side yet. A click
   * stashes and fires at the envelope's authoritative dock; a flip or
   * turn.failed rolls the preview back. Never persisted anywhere. */
  preview?: boolean
  /** Per-conversation transcript position; null only on legacy rows. */
  seq?: number | null
  created_at?: string
}

/** A project asset row (the wire shape the dock's chips and the archive's
 * attachment payloads both speak). */
export interface ProjectAsset {
  id: string
  type: string
  file_url: string | null
  /** Browser-playable URL resolved server-side (AssetResponse's computed
   * field) — the message chip's media sliver reads it (2026-09-24: the sent
   * attachment degraded to a bare icon because only the storage KEY was
   * persisted; the send payload now rides stream_url). */
  stream_url?: string | null
  title: string | null
  processing_status: "pending" | "processing" | "completed" | "failed"
  /** The chain's live stage token (ADR-095 §2 — asr / speaker_map /
   * prosody / …): server-stamped from meta only mid-processing, cleared at
   * the terminal state. Absent on older rows and on message-persisted
   * attachment shapes — the now-line falls back to the type-verb line
   * (read tolerance). The token never renders; the client maps it to the
   * user-language label (内部工序名永不上屏). */
  processing_stage?: string | null
  /** Settlement / upload stamps (AssetResponse carries both; optional —
   * message-persisted attachment shapes are thinner). The watch windows'
   * recency gate reads processed_at, falling back to created_at. */
  processed_at?: string | null
  created_at?: string | null
}

/** One unit of the conversation timeline. An unsealed trailing fold is a
 * WORK SEGMENT, not a finished receipt: the dock lets its last current-turn
 * fold carry the live now label in place. Tool settlement alone never seals
 * that segment; the first visible prose fragment or the turn's real terminal
 * state does.
 *
 * rowKey law (行身份): an activity frame's `activity_id` is PER-TURN scoped
 * (two turns both have an "a1"), so it can never key the cross-turn list —
 * the React identity is the HOST MESSAGE ROW's stable id (`birthKey ?? id`,
 * the OverlayMessage render-key law), stamped here at projection time. A
 * settle merges into the same host row, so the identity survives updates; a
 * fold keys by its FIRST MEMBER's rowKey (the segment's head never changes
 * when later members join or settle). The same host carries the client-only
 * frozen work-segment clock; tool duration_ms remains the tool's own fact. */
export type ConversationUnit =
  | { kind: "message"; message: OverlayMessage }
  | {
      kind: "activity"
      activity: ActivityRowFrame
      rowKey: string
      turnId?: string
      independentKind?: OverlayMessage["independentKind"]
      workStartedAtMs?: number
      workEndedAtMs?: number
    }
  | {
      kind: "activityFold"
      rows: ActivityRowFrame[]
      /** A contiguous failure settles this same segment; isolated failures
       * remain standalone activity units instead. */
      failure: ActivityRowFrame | null
      /** First host's own activity stamp, retained even while every member
       * is still active and `rows` is empty (run receipt anchoring reads it). */
      firstActivityAt: string | undefined
      startedAtMs: number | null
      endedAtMs: number | null
      elapsedMs: number | null
      openTail: boolean
      rowKey: string
      turnId?: string
      independentKind?: OverlayMessage["independentKind"]
    }

export type ComponentSlot =
  | {
      kind: "storyboard"
      key: string
      message: OverlayMessage
      block: VideoStoryboardBlock
    }
  | {
      kind: "output"
      key: string
      outputs: Output[]
      priorDrained: boolean
      history?: boolean
    }

/** A ordered presentation block. Turn membership comes only from explicit
 * turnId; a legacy/independent fact never gets adopted by a neighbouring
 * TurnBlock. The key uses the first host row, not turnId, so reconciling an
 * optimistic turn id to its server id cannot remount the block. */
export type ConversationBlock =
  | {
      kind: "turn"
      key: string
      turnId: string
      units: ConversationUnit[]
    }
  | {
      kind: "standalone"
      key: string
      factKind: NonNullable<OverlayMessage["independentKind"]> | "legacy"
      units: ConversationUnit[]
    }
  | { kind: "runAnchor"; key: string; runId: string }
