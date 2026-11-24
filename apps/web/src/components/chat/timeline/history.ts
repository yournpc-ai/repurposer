/** Conversation archive → flow rows (Phase 3 Batch A test seam): the
 * confirm-phase replay mapping, extracted from ChatDock as a PURE function
 * (行为零变化 — the same branches, the same ids, the same read tolerance).
 *
 * The mapping is a PRESENTATION projection of persisted message rows: it
 * rebuilds what the live flow showed (echo prose, QA archives, attachment
 * chips, legacy trigger pills) and nothing more — it NEVER derives
 * lifecycle (恢复不推导 lifecycle, ADR-087 原则 2: readiness comes from the
 * server-named stamp, never from which rows exist).
 *
 * Shared wire and overlay types live in `./types`; this module only adapts
 * persisted rows and never owns layout. */

import { messageAssetsFromAttachments, type MessageAttachment } from "@/lib/chatAttachments"
import type { SkillReference } from "@/lib/skills"
import type {
  ActivityReceipt,
  ActivityRowFrame,
  ActivitySemanticDetail,
  ActivitySemanticDetailKind,
  AudioCandidateReceipt,
  BriefAnswerItem,
  CandidateMemberPayload,
  CandidateSurface,
  ComponentClipReceipt,
  MessageFeedbackSummary,
  NativeJobReceipt,
  OverlayMessage,
  QuestionAnswer,
  QuestionMessage,
  StepPlanItem,
  StepPlanStatus,
  VideoReviewIssueCode,
  VideoReviewReceipt,
  VideoRevisionReceipt,
} from "./types"

const VALID_STEP_STATUSES = new Set<StepPlanStatus>([
  "pending",
  "in_progress",
  "done",
  "skipped",
  "failed",
])

/** Parse user-safe step checklist from either message.steps or intent.steps. */
export function parseStepsPlan(
  stepsField: unknown,
  intent?: unknown,
): StepPlanItem[] | undefined {
  const raw = Array.isArray(stepsField)
    ? stepsField
    : Array.isArray((intent as Record<string, unknown> | null)?.steps)
      ? (intent as Record<string, unknown>).steps
      : null
  if (!Array.isArray(raw) || raw.length === 0) return undefined
  const out: StepPlanItem[] = []
  for (const item of raw) {
    if (!item || typeof item !== "object") continue
    const rec = item as Record<string, unknown>
    const title = typeof rec.title === "string" ? rec.title.trim() : ""
    const status = typeof rec.status === "string" ? (rec.status as StepPlanStatus) : null
    if (!title || !status || !VALID_STEP_STATUSES.has(status)) continue
    out.push({ title, status })
  }
  return out.length > 0 ? out : undefined
}

/** Parse optional persisted feedback summary with read tolerance. */
export function parseFeedbackSummary(raw: unknown): MessageFeedbackSummary | null | undefined {
  if (raw === null) return null
  if (!raw || typeof raw !== "object") return undefined
  const rec = raw as Record<string, unknown>
  if (rec.rating !== "good" && rec.rating !== "bad") return undefined
  const tags = Array.isArray(rec.tags)
    ? rec.tags.filter((item): item is string => typeof item === "string" && item.length > 0)
    : []
  return {
    rating: rec.rating,
    reason: typeof rec.reason === "string" ? rec.reason : null,
    tags,
    updated_at: typeof rec.updated_at === "string" ? rec.updated_at : null,
  }
}

/** Resolve an answer payload to its display line. Bail variants are
 * localized (a graceful exit, never an error); freeform shows its text. */
export function answeredQuestionText(
  answer: QuestionAnswer,
  t: (key: string) => string,
): { text: string; muted: boolean } {
  if (answer.kind === "bail") {
    if (answer.text === "superseded") {
      return { text: t("chat.qa.superseded"), muted: true }
    }
    return { text: t("chat.qa.cancelled"), muted: true }
  }
  // The interrupt expiry sweep's auto-answer (machine marker, same pattern
  // as "superseded") — a system decision, rendered muted.
  if (answer.kind === "option" && answer.text === "expired") {
    return { text: t("chat.qa.expired"), muted: true }
  }
  // start 类 QA 退役 (Workspace 合同 v4.2 C8, 2026-09-26 封板): the
  // confirmation beat archives as a plain user bubble (「确认生成」via the
  // sendChat channel), never as a Q&A block — task_book answers bypass
  // this resolver entirely (history replay the echo only), so no
  // "start" branch lives here anymore. QA blocks serve genuine Q&A only.
  return { text: answer.text || answer.option_id || "", muted: false }
}

export function groupAnswerDisplay(
  question: QuestionMessage,
  answers: BriefAnswerItem[],
) {
  const items = (question.question?.items ?? []).map((item) => {
    const answer = answers.find((candidate) => candidate.slot === item.slot)
    const selected = answer?.kind === "option"
      ? item.options?.find((option) => option.id === answer.option_id)
      : undefined
    return { question: item.question, answer: selected?.label || answer?.text || "" }
  })
  return { items }
}

/** The explicit deterministic-option association persisted on the real user row. */
export function answeredQuestionIdFromIntent(intent: unknown): string | undefined {
  const data = (intent ?? {}) as Record<string, unknown>
  return typeof data.answered_question_id === "string" && data.answered_question_id
    ? data.answered_question_id
    : undefined
}

export function nativeJobReceipt(intent: unknown): NativeJobReceipt | undefined {
  const data = intent as Record<string, unknown> | null
  if (typeof data?.native_call_id !== "string") return
  const result = data.media_result as Record<string, unknown> | undefined
  const status = result?.status ?? data.media_status
  if (typeof status !== "string") return
  return {
    callId: data.native_call_id,
    operation:
      typeof data.operation === "string"
        ? data.operation
        : typeof data.tool === "string"
          ? data.tool
          : undefined,
    status,
    role: typeof result?.role === "string" ? result.role : undefined,
    error: typeof result?.error === "string" ? result.error : undefined,
    outputId: typeof result?.output_id === "string" ? result.output_id : undefined,
    chargedCredits: typeof result?.charged_credits === "number" ? result.charged_credits : undefined,
    reservedCredits: typeof result?.reserved_credits === "number" ? result.reserved_credits : undefined,
  }
}

export function messageReceiptFacts(intent: unknown) {
  const jobReceipt = nativeJobReceipt(intent)
  const reviewed = (intent as { reviewed_version?: { composition_version_id?: unknown } } | null)?.reviewed_version
  return {
    ...(jobReceipt && { jobReceipt }),
    ...(typeof reviewed?.composition_version_id === "string" && { reviewedVersionId: reviewed.composition_version_id }),
  }
}

export function deliveryOutputRefs(intent: unknown): string[] {
  const data = (intent ?? {}) as Record<string, unknown>
  if (!Array.isArray(data.output_refs)) {
    return []
  }
  return data.output_refs.filter((ref): ref is string => typeof ref === "string" && ref.length > 0)
}

const VIDEO_REVIEW_SCOPES = [
  "actual_output_decoded",
  "static_frames_checked",
  "deterministic_output_checks",
  "sampled_frame_signals_checked",
  "audio_signal_checked",
  "motion_and_transitions_checked",
  "audio_and_av_sync_checked",
] as const
const VIDEO_REVIEW_ISSUE_CODES = new Set<VideoReviewIssueCode>([
  "AUDIO_MISSING",
  "AUDIO_DECODE_FAILED",
  "AUDIO_SILENT",
  "AUDIO_QUIET",
  "AUDIO_CLIPPED",
])

function receiptRecord(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
}

function receiptString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined
}

function receiptNumber(value: unknown, positive = false): number | undefined {
  return typeof value === "number" && Number.isFinite(value) &&
    (positive ? value > 0 : value >= 0)
    ? value
    : undefined
}

function receiptStrings(value: unknown): string[] | undefined {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? value as string[]
    : undefined
}

function receiptFrames(value: unknown): number[] | undefined {
  return Array.isArray(value) && value.length >= 2 &&
    value.every((item) => typeof item === "number" && Number.isInteger(item) && item >= 0)
    ? value as number[]
    : undefined
}

function parseComponentClips(value: unknown): ComponentClipReceipt[] | undefined {
  if (!Array.isArray(value)) return undefined
  const components: ComponentClipReceipt[] = []
  for (const raw of value) {
    const item = receiptRecord(raw)
    if (!item) return undefined
    const clipId = receiptString(item.clip_id)
    const programDigest = receiptString(item.program_digest)
    const mediaDigest = receiptString(item.media_digest)
    const posterUrl = receiptString(item.poster_url)
    const previewFrame = receiptNumber(item.preview_frame)
    const dynamicFrames = receiptFrames(item.dynamic_sample_frames)
    const durationFrames = receiptNumber(item.duration_frames, true)
    const fps = receiptNumber(item.fps, true)
    if (!clipId || !programDigest || !mediaDigest || !posterUrl ||
        previewFrame === undefined || !dynamicFrames || durationFrames === undefined ||
        fps === undefined) return undefined
    components.push({
      clip_id: clipId,
      program_digest: programDigest,
      media_digest: mediaDigest,
      poster_url: posterUrl,
      preview_frame: previewFrame,
      dynamic_sample_frames: dynamicFrames,
      duration_frames: durationFrames,
      fps,
    })
  }
  return components
}

function parseVideoReviewReceipt(root: Record<string, unknown>): VideoReviewReceipt | undefined {
  if (!Array.isArray(root.frames) || !Array.isArray(root.findings) ||
      !Array.isArray(root.output_issue_codes)) return undefined

  const frames: VideoReviewReceipt["frames"] = []
  for (const raw of root.frames) {
    const frame = receiptRecord(raw)
    if (!frame || typeof frame.frame_id !== "string" || !frame.frame_id ||
        typeof frame.time_seconds !== "number" ||
        !Number.isFinite(frame.time_seconds) || frame.time_seconds < 0) return undefined
    frames.push({ frame_id: frame.frame_id, time_seconds: frame.time_seconds })
  }

  const findings: VideoReviewReceipt["findings"] = []
  for (const raw of root.findings) {
    const finding = receiptRecord(raw)
    if (!finding ||
        (finding.kind !== "observed_issue" && finding.kind !== "aesthetic_suggestion") ||
        typeof finding.frame_id !== "string" || !finding.frame_id ||
        typeof finding.observed !== "string" || !finding.observed) return undefined
    findings.push({
      kind: finding.kind,
      frame_id: finding.frame_id,
      observed: finding.observed,
    })
  }

  const rawScope = receiptRecord(root.scope)
  if (!rawScope) return undefined
  const scope = {} as VideoReviewReceipt["scope"]
  for (const key of VIDEO_REVIEW_SCOPES) {
    if (typeof rawScope[key] !== "boolean") return undefined
    scope[key] = rawScope[key] as boolean
  }

  return {
    kind: "video_review",
    frames,
    findings,
    output_issue_codes: root.output_issue_codes.filter(
      (code): code is VideoReviewIssueCode =>
        typeof code === "string" && VIDEO_REVIEW_ISSUE_CODES.has(code as VideoReviewIssueCode),
    ),
    scope,
  }
}

function parseVideoRevisionReceipt(root: Record<string, unknown>): VideoRevisionReceipt | undefined {
  const version = receiptNumber(root.version, true)
  const settings = receiptStrings(root.settings)
  const scenes = receiptRecord(root.scenes)
  const clips = receiptRecord(root.clips)
  const components = parseComponentClips(root.components)
  if (version === undefined || !Number.isInteger(version) || !settings || !scenes || !clips ||
      !components || typeof root.transitions_changed !== "boolean") return undefined
  const addedScenes = receiptStrings(scenes.added)
  const removedScenes = receiptStrings(scenes.removed)
  if (!addedScenes || !removedScenes || !Array.isArray(scenes.moved)) return undefined
  const moved: VideoRevisionReceipt["scenes"]["moved"] = []
  for (const raw of scenes.moved) {
    const move = receiptRecord(raw)
    const sceneId = receiptString(move?.scene_id)
    const from = receiptNumber(move?.from_seconds)
    const to = receiptNumber(move?.to_seconds)
    if (!sceneId || from === undefined || to === undefined) return undefined
    moved.push({ scene_id: sceneId, from_seconds: from, to_seconds: to })
  }
  const removedClips = receiptStrings(clips.removed)
  if (!removedClips || !Array.isArray(clips.added) || !Array.isArray(clips.updated)) return undefined
  const added: VideoRevisionReceipt["clips"]["added"] = []
  for (const raw of clips.added) {
    const clip = receiptRecord(raw)
    const clipId = receiptString(clip?.clip_id)
    const kind = receiptString(clip?.kind)
    if (!clipId || !kind) return undefined
    added.push({ clip_id: clipId, kind })
  }
  const allowedChanges = new Set(["range", "object", "animations", "scene_id", "source", "linked_group_id"])
  const updated: VideoRevisionReceipt["clips"]["updated"] = []
  for (const raw of clips.updated) {
    const clip = receiptRecord(raw)
    const clipId = receiptString(clip?.clip_id)
    const changes = receiptStrings(clip?.changes)
    if (!clipId || !changes || changes.length === 0 ||
        !changes.every((change) => allowedChanges.has(change))) return undefined
    updated.push({ clip_id: clipId, changes: changes as VideoRevisionReceipt["clips"]["updated"][number]["changes"] })
  }
  return {
    kind: "video_revision",
    version,
    settings,
    scenes: { added: addedScenes, removed: removedScenes, moved },
    clips: { added, removed: removedClips, updated },
    transitions_changed: root.transitions_changed,
    components,
  }
}

function parseAudioCandidates(value: unknown): AudioCandidateReceipt[] | undefined {
  if (!Array.isArray(value) || value.length === 0) return undefined
  const members: AudioCandidateReceipt[] = []
  for (const raw of value) {
    const member = receiptRecord(raw)
    const index = receiptNumber(member?.member_index)
    const ordinal = receiptNumber(member?.ordinal, true)
    const title = receiptString(member?.title)
    const duration = receiptNumber(member?.duration_seconds, true)
    if (index === undefined || !Number.isInteger(index) || ordinal === undefined ||
        !Number.isInteger(ordinal) || !title || duration === undefined) return undefined
    members.push({ member_index: index, ordinal, title, duration_seconds: duration })
  }
  return members
}

/** Shared live/history receipt reader. Malformed evidence degrades to the
 * ordinary Activity category; unknown audio codes alone are ignored. */
export function parseActivityReceipt(value: unknown): ActivityReceipt | undefined {
  const root = receiptRecord(value)
  if (!root) return undefined
  if (root.kind === "video_review") return parseVideoReviewReceipt(root)
  if (root.kind === "component") {
    const components = parseComponentClips(root.components)
    return components?.length ? { kind: "component", components } : undefined
  }
  if (root.kind === "video_revision") return parseVideoRevisionReceipt(root)
  if (root.kind === "sfx_search") {
    const candidateSetId = receiptString(root.candidate_set_id)
    const topic = receiptString(root.topic)
    const members = parseAudioCandidates(root.members)
    return candidateSetId && topic && members
      ? { kind: "sfx_search", candidate_set_id: candidateSetId, topic, members }
      : undefined
  }
  if (root.kind === "sfx_import") {
    const candidateSetId = receiptString(root.candidate_set_id)
    const memberIndex = receiptNumber(root.member_index)
    const assetId = receiptString(root.asset_id)
    const snapshotId = receiptString(root.snapshot_id)
    const snapshotDigest = receiptString(root.snapshot_digest)
    const title = receiptString(root.title)
    const duration = receiptNumber(root.duration_seconds, true)
    return candidateSetId && memberIndex !== undefined && Number.isInteger(memberIndex) &&
      assetId && snapshotId && snapshotDigest && title && duration !== undefined
      ? {
          kind: "sfx_import",
          candidate_set_id: candidateSetId,
          member_index: memberIndex,
          asset_id: assetId,
          snapshot_id: snapshotId,
          snapshot_digest: snapshotDigest,
          title,
          duration_seconds: duration,
        }
      : undefined
  }
  if (root.kind === "music_search") {
    const candidateSetId = receiptString(root.candidate_set_id)
    const topic = receiptString(root.topic)
    const members = parseAudioCandidates(root.members)
    return candidateSetId && topic && members
      ? { kind: "music_search", candidate_set_id: candidateSetId, topic, members }
      : undefined
  }
  if (root.kind === "music_selection") {
    const candidateSetId = receiptString(root.candidate_set_id)
    const memberIndex = receiptNumber(root.member_index)
    const musicId = receiptString(root.music_id)
    const title = receiptString(root.title)
    const duration = receiptNumber(root.duration_seconds, true)
    return candidateSetId && memberIndex !== undefined && Number.isInteger(memberIndex) &&
      musicId && title && duration !== undefined
      ? {
          kind: "music_selection",
          candidate_set_id: candidateSetId,
          member_index: memberIndex,
          music_id: musicId,
          title,
          duration_seconds: duration,
        }
      : undefined
  }
  if (root.kind === "skill_saved") {
    const skillId = receiptString(root.skill_id)
    const skillVersionId = receiptString(root.skill_version_id)
    const name = receiptString(root.name)
    const version = receiptNumber(root.version, true)
    const actsCount = receiptNumber(root.acts_count, true)
    const sfxCuesCount = receiptNumber(root.sfx_cues_count)
    return skillId && skillVersionId && name && version !== undefined && Number.isInteger(version) &&
      actsCount !== undefined && Number.isInteger(actsCount) &&
      sfxCuesCount !== undefined && Number.isInteger(sfxCuesCount)
      ? {
          kind: "skill_saved",
          skill_id: skillId,
          skill_version_id: skillVersionId,
          name,
          version,
          acts_count: actsCount,
          sfx_cues_count: sfxCuesCount,
        }
      : undefined
  }
  return undefined
}

/** A persisted activity array row (ADR-108 §2 — 每帧一行): intent =
 * {type:"activity", frame}. The frame is the server's open/settle dump —
 * its `at` is the birth stamp (execute entry for a read span), a settle
 * merge adds the terminal status / past-tense key / duration_ms IN PLACE.
 * Read tolerance: an off-shape frame parses to undefined and the ROW is
 * skipped by the caller (a malformed activity entry never becomes an empty
 * bubble). */
const SEMANTIC_DETAIL_KINDS = new Set<ActivitySemanticDetailKind>([
  "style",
  "motion_block_insert",
  "motion_block_update",
  "text_insert",
  "text_caption_from_audio",
  "text_edit",
  "sfx",
  "audio_edit",
  "transition",
])

export function parseActivitySemanticDetail(value: unknown): ActivitySemanticDetail | undefined {
  const root = receiptRecord(value)
  if (!root || typeof root.kind !== "string" || !SEMANTIC_DETAIL_KINDS.has(root.kind as ActivitySemanticDetailKind)) {
    return undefined
  }
  const aspects = receiptStrings(root.aspects)?.filter((s) => s.length > 0)
  return {
    kind: root.kind as ActivitySemanticDetailKind,
    preset: receiptString(root.preset),
    block: receiptString(root.block),
    recipe: receiptString(root.recipe),
    position: receiptString(root.position),
    role: receiptString(root.role),
    scope: receiptString(root.scope),
    snippet: receiptString(root.snippet),
    window: receiptString(root.window),
    aspects: aspects?.length ? aspects : undefined,
    bilingual: root.bilingual === true ? true : undefined,
  }
}

export function activityRowFrame(intent: unknown): ActivityRowFrame | undefined {
  const data = (intent ?? {}) as Record<string, unknown>
  if (data.type !== "activity") return undefined
  const d = (data.frame ?? {}) as Record<string, unknown>
  const KINDS = new Set(["read", "draft", "run", "repair"])
  const STATUSES = new Set(["active", "completed", "failed", "cancelled"])
  if (
    typeof d.activity_id !== "string" ||
    typeof d.kind !== "string" ||
    !KINDS.has(d.kind) ||
    typeof d.status !== "string" ||
    !STATUSES.has(d.status)
  ) {
    return undefined
  }
  return {
    activity_id: d.activity_id,
    group_id: typeof d.group_id === "string" ? d.group_id : undefined,
    call_id: typeof d.call_id === "string" ? d.call_id : undefined,
    tool_name: typeof d.tool_name === "string" ? d.tool_name : undefined,
    error: typeof d.error === "string" ? d.error : undefined,
    call_state: typeof d.call_state === "string" ? d.call_state : undefined,
    call_count: typeof d.call_count === "number" ? d.call_count : undefined,
    call_index: typeof d.call_index === "number" ? d.call_index : undefined,
    kind: d.kind as ActivityRowFrame["kind"],
    status: d.status as ActivityRowFrame["status"],
    key: typeof d.key === "string" ? d.key : null,
    at: typeof d.at === "string" ? d.at : undefined,
    count: typeof d.count === "number" ? d.count : undefined,
    total: typeof d.total === "number" ? d.total : undefined,
    name: typeof d.name === "string" ? d.name : undefined,
    duration_ms: typeof d.duration_ms === "number" ? d.duration_ms : undefined,
    assetType: typeof d.asset_type === "string" ? d.asset_type : undefined,
    receipt: parseActivityReceipt(d.receipt),
    detail: parseActivitySemanticDetail(d.detail),
  }
}

export function isNonRenderIntent(intent: unknown): boolean {
  const data = (intent ?? {}) as Record<string, unknown>
  return data.type === "activity_forensics"
}

export function activityAssetKey(base: string, assetType?: string | null): string {
  return assetType === "video" || assetType === "audio"
    ? `${base}_${assetType}`
    : base
}

/** One parsed candidates_log event (the replay-fold input). */
export type CandidatesLogEvent =
  | { kind: "set"; surface: CandidateSurface }
  | { kind: "selection"; candidateSetId: string; selected: number[] }

/** A persisted turn's candidate-surface events (intent.type ===
 * "candidates_log" — the activity-row precedent's twin, v4.2 C8-c): the
 * SSE ``assistant.candidates`` payloads the turn emitted, in order. The
 * replay folds them: a ``set`` event births the card row, a ``selection``
 * event repaints the anchoring card's highlight. Read tolerance: the shell
 * or a malformed event drops to undefined / skips (a plain assistant row,
 * never a crash); unknown member fields read as empty. */
export function candidatesLog(intent: unknown): CandidatesLogEvent[] | undefined {
  const data = (intent ?? {}) as Record<string, unknown>
  if (data.type !== "candidates_log") return undefined
  const raw = Array.isArray(data.events) ? data.events : null
  if (raw === null) return undefined
  const events: CandidatesLogEvent[] = []
  for (const e of raw) {
    const d = (e ?? {}) as Record<string, unknown>
    const setId = typeof d.candidate_set_id === "string" ? d.candidate_set_id : null
    if (setId === null) continue
    if (d.kind === "video_preset_set") {
      const rawMembers = Array.isArray(d.members) ? d.members : []
      const members: CandidateMemberPayload[] = []
      for (const value of rawMembers) {
        const md = (value ?? {}) as Record<string, unknown>
        if (
          typeof md.preset_id !== "string" ||
          typeof md.preview_url !== "string" ||
          typeof md.preview_digest !== "string" ||
          typeof md.duration_seconds !== "number" ||
          !Number.isFinite(md.duration_seconds) || md.duration_seconds <= 0 ||
          typeof md.aspect !== "string" ||
          typeof md.width !== "number" || md.width <= 0 ||
          typeof md.height !== "number" || md.height <= 0
        ) {
          members.length = 0
          break
        }
        members.push({
          start: 0,
          end: md.duration_seconds,
          excerpt: md.preset_id,
          speaker: null,
          provider: "native",
          preset_id: md.preset_id,
          title: typeof md.title === "string" ? md.title : md.preset_id,
          preview_url: md.preview_url,
          preview_digest: md.preview_digest,
          duration_seconds: md.duration_seconds,
          aspect: md.aspect,
          width: md.width,
          height: md.height,
        })
      }
      if (members.length < 2 || members.length > 4 || members.length !== rawMembers.length) continue
      events.push({
        kind: "set",
        surface: {
          kind: "video_preset_set",
          candidateSetId: setId,
          topic: typeof d.topic === "string" ? d.topic : "",
          assetId: null,
          members,
          selected: [],
        },
      })
    } else if (d.kind === "music_set") {
      const members: CandidateMemberPayload[] = []
      for (const m of Array.isArray(d.members) ? d.members : []) {
        const md = (m ?? {}) as Record<string, unknown>
        if (typeof md.start !== "number" || typeof md.end !== "number") continue
        members.push({
          start: md.start,
          end: md.end,
          excerpt: typeof md.excerpt === "string" ? md.excerpt : "",
          speaker: typeof md.speaker === "string" ? md.speaker : null,
          provider: typeof md.provider === "string" ? md.provider : null,
          provider_id: typeof md.provider_id === "string" ? md.provider_id : null,
          music_id: typeof md.music_id === "string" ? md.music_id : null,
          title: typeof md.title === "string" ? md.title : null,
          author: typeof md.author === "string" ? md.author : null,
          duration_seconds:
            typeof md.duration_seconds === "number" ? md.duration_seconds : null,
          source_url: typeof md.source_url === "string" ? md.source_url : null,
          preview_url: typeof md.preview_url === "string" ? md.preview_url : null,
          license: typeof md.license === "string" ? md.license : null,
          attribution: typeof md.attribution === "string" ? md.attribution : null,
          query: typeof md.query === "string" ? md.query : null,
        })
      }
      events.push({
        kind: "set",
        surface: {
          kind: "music_set",
          candidateSetId: setId,
          topic: typeof d.topic === "string" ? d.topic : "",
          assetId: typeof d.asset_id === "string" ? d.asset_id : null,
          members,
          selected: [],
        },
      })
    } else if (d.kind === "set" || d.kind === "sfx_set") {
      const members: CandidateMemberPayload[] = []
      for (const m of Array.isArray(d.members) ? d.members : []) {
        const md = (m ?? {}) as Record<string, unknown>
        if (typeof md.start !== "number" || typeof md.end !== "number") continue
        members.push({
          start: md.start,
          end: md.end,
          excerpt: typeof md.excerpt === "string" ? md.excerpt : "",
          speaker: typeof md.speaker === "string" ? md.speaker : null,
          provider: typeof md.provider === "string" ? md.provider : null,
          provider_id: typeof md.provider_id === "string" ? md.provider_id : null,
          title: typeof md.title === "string" ? md.title : null,
          author: typeof md.author === "string" ? md.author : null,
          duration_seconds:
            typeof md.duration_seconds === "number" ? md.duration_seconds : null,
          source_url: typeof md.source_url === "string" ? md.source_url : null,
          preview_url: typeof md.preview_url === "string" ? md.preview_url : null,
          license: typeof md.license === "string" ? md.license : null,
          attribution: typeof md.attribution === "string" ? md.attribution : null,
          query: typeof md.query === "string" ? md.query : null,
        })
      }
      events.push({
        kind: "set",
        surface: {
          candidateSetId: setId,
          topic: typeof d.topic === "string" ? d.topic : "",
          assetId: typeof d.asset_id === "string" ? d.asset_id : null,
          members,
          selected: [],
        },
      })
    } else if (d.kind === "selection") {
      const selected = (Array.isArray(d.selected) ? d.selected : []).filter(
        (i): i is number => typeof i === "number" && Number.isInteger(i) && i >= 0,
      )
      events.push({ kind: "selection", candidateSetId: setId, selected })
    }
  }
  return events
}

/** ask 三分解剖 ①: the row's framing prose — its content when the ask
 * brought one (the content then differs from the bare question); null when
 * the row carries none (legacy rows, code-composed questions — their
 * content IS the bare question, and the pill's title already says it). */
export function questionEcho(m: QuestionMessage): string | null {
  const content = (m.content ?? "").trim()
  const bare = (m.question?.question ?? "").trim()
  if (bare && content.endsWith(`\n\n${bare}`)) {
    return content.slice(0, -(bare.length + 2)).trim() || null
  }
  return content && content !== bare ? content : null
}

/** ask 三分解剖 ②: the bare question — the payload's own field, falling
 * back to the content where legacy rows stored it (读容忍). */
export function bareQuestion(m: QuestionMessage): string {
  return (m.question?.question ?? "").trim() || (m.content ?? "").trim()
}

/** One archive row as the messages endpoint returns it (the mapper's input
 * wire — QuestionMessage plus the user-row extras). */
export interface HistoryRow extends QuestionMessage {
  turn_state?: string | null
  role: "user" | "assistant"
  focus_output?: { id: string; label: string } | null
  attachments?: MessageAttachment[]
  skill?: SkillReference | null
}

/** Map the conversation's message rows to flow items (confirm-phase archive
 * replay, B1): the durable record rebuilds the flow so a refresh or another
 * device no longer loses capability answers / past refinements. 形态律
 * (ADR-053 R1): a still-pending OPTIONS question docks above the input (the
 * pending fetch holds it), never in the flow; a TEXT question (options-
 * empty) IS a plain flow message, pending or answered. 归档单一源
 * (material-ui-convergence ①): EVERY row renders — the opener included;
 * there is no prop-rendered side lane and no skip predicate.
 *
 * @param rows   the server rows, oldest first
 * @param ctx.t  i18n for the QA archive's answer line
 */
export function mapHistoryRows(
  rows: HistoryRow[],
  ctx: { t: (key: string) => string },
): OverlayMessage[] {
  const history: OverlayMessage[] = []
  // C8-c fold: candidate set id → the OverlayMessage anchoring its card, so
  // a LATER turn's selection event repaints the earlier card's highlight
  // (the surface is one seat; rows never move).
  const cardBySetId = new Map<string, OverlayMessage>()
  for (const m of rows) {
    const facts = m.role === "assistant" ? messageReceiptFacts(m.intent) : undefined
    const rowSteps = m.role === "assistant" ? parseStepsPlan(m.steps, m.intent) : undefined
    const rowFeedback = m.role === "assistant" ? parseFeedbackSummary(m.feedback) : undefined
    const pushRow = (row: OverlayMessage): OverlayMessage => {
      const positioned = {
        ...row,
        ...(row.id === m.id && facts),
        ...(row.role === "assistant" && !row.qa && !row.activity && !row.candidates && rowSteps ? { steps: rowSteps } : {}),
        ...(row.role === "assistant" && !row.qa && !row.activity && !row.candidates && rowFeedback !== undefined ? { feedback: rowFeedback } : {}),
        turnId: m.turn_id ?? undefined,
        serverMessageId: m.id,
        hydrated: true,
      }
      const hydrated = m.seq == null ? positioned : { ...positioned, seq: m.seq }
      history.push(hydrated)
      return hydrated
    }
    if (m.role === "user") {
      pushRow({
        id: m.id,
        role: "user",
        content: m.content ?? "",
        skill: m.skill ?? undefined,
        answeredQuestionId: answeredQuestionIdFromIntent(m.intent),
        at: m.created_at,
        focus: m.focus_output ?? undefined,
        // Sent attachments persist on the message row — re-render the
        // chips so a refresh / another device keeps the record.
        assets: messageAssetsFromAttachments(m.attachments ?? []),
      })
    } else if (m.question) {
      const hasOptions = (m.question.options?.length ?? 0) > 0 || (m.question.items?.length ?? 0) > 0
      if (m.answer) {
        if (hasOptions) {
          // ask 三分解剖: the framing prose replays as its own flow
          // message first (it sat above the dock live), then the QA
          // block quotes the BARE question — a refresh reads like the
          // live flow did.
          const echo = questionEcho(m)
          if (echo || m.blocks?.length || deliveryOutputRefs(m.intent).length > 0) {
            pushRow({
              id: `${m.id}-echo`,
              role: "assistant",
              content: echo ?? "",
              outputRefs: deliveryOutputRefs(m.intent),
              blocks: m.blocks?.length ? m.blocks : undefined,
              at: m.created_at,
            })
          }
          const display = answeredQuestionText(
            m.answer,
            ctx.t,
          )
          pushRow({
            id: m.id,
            role: "assistant",
            content: "",
            at: m.created_at,
            independentKind: "qa",
            qa: {
              question: bareQuestion(m),
              answer: display.text,
              muted: display.muted,
              questionId: m.id,
              answerKind: m.answer.kind,
              ...(m.answer.answers?.length ? groupAnswerDisplay(m, m.answer.answers) : {}),
            },
          })
        } else {
          // 形态律 (ADR-053 R1): an options-empty question's answered
          // form is the plain message pair — the question line stays a
          // plain assistant message, no AnsweredQuestion block.
          pushRow({
            id: m.id,
            role: "assistant",
            content: m.content ?? "",
            outputRefs: deliveryOutputRefs(m.intent),
            blocks: m.blocks?.length ? m.blocks : undefined,
            at: m.created_at,
          })
        }
      } else if (m.question.kind === "question" && !hasOptions) {
        // 形态律 (ADR-053 R1): a pending TEXT question never docks —
        // it lives in the flow as a plain assistant message (only
        // options questions raise the pill).
        pushRow({
          id: m.id,
          role: "assistant",
          content: m.content ?? "",
          outputRefs: deliveryOutputRefs(m.intent),
          blocks: m.blocks?.length ? m.blocks : undefined,
          at: m.created_at,
        })
      } else if (m.question.kind === "question") {
        // A pending OPTIONS question docks (the pill revives via the
        // pending_question fetch) — its framing prose replays as a
        // flow message so the refresh reads like the live flow did.
        const echo = questionEcho(m)
        if (echo || m.blocks?.length || deliveryOutputRefs(m.intent).length > 0) {
          pushRow({
            id: `${m.id}-echo`,
            role: "assistant",
            content: echo ?? "",
            outputRefs: deliveryOutputRefs(m.intent),
            blocks: m.blocks?.length ? m.blocks : undefined,
            at: m.created_at,
          })
        }
      }
    } else {
      // 永不渲染行 (ADR-108): the rejection forensics ledger and legacy
      // aggregate logs skip silently — never an empty bubble.
      if (isNonRenderIntent(m.intent)) continue
      const intentType = ((m.intent ?? {}) as Record<string, unknown>).type
      // 失败行回放: a persisted turn-failure row replays as the SAME grey
      // meta row the live turn.failed frame renders — a refresh keeps the
      // failure's stage and its lawful next step instead of dropping them.
      if (intentType === "turn_failed") {
        if (!(m.content ?? "").trim()) continue // never an empty bubble
        pushRow({
          id: m.id,
          role: "assistant",
          content: m.content ?? "",
          meta: "error",
          at: m.created_at,
        })
        continue
      }
      const frame = activityRowFrame(m.intent)
      if (frame !== undefined) {
        pushRow({
          id: m.id,
          role: "assistant",
          content: "",
          at: m.created_at,
          activity: { ...frame, at: frame.at ?? m.created_at },
          blocks: m.blocks?.length ? m.blocks : undefined,
          outputRefs: deliveryOutputRefs(m.intent),
        })
        continue
      }
      if (intentType === "activity") {
        if (!(m.content ?? "").trim()) continue
      }
      // Candidate Surface 回放 (v4.2 C8-c): the turn's candidates_log events
      // fold — a set event births its card row (idempotent re-emits REPLACE
      // in place), a selection event repaints the anchoring card. A log
      // carrying only selection events pushes NO row (the repaint lands on
      // the earlier card; an unknown set id skips quietly).
      const candEvents = candidatesLog(m.intent)
      if (candEvents !== undefined) {
        for (const ev of candEvents) {
          if (ev.kind === "set") {
            const existing = cardBySetId.get(ev.surface.candidateSetId)
            if (existing !== undefined) {
              existing.candidates = {
                ...ev.surface,
                selected: existing.candidates?.selected ?? [],
              }
              continue
            }
            const row: OverlayMessage = {
              id: `${m.id}-cand-${ev.surface.candidateSetId}`,
              role: "assistant",
              content: "",
              at: m.created_at,
              independentKind: m.turn_id ? undefined : "candidate",
              candidates: ev.surface,
            }
            const positioned = pushRow(row)
            cardBySetId.set(ev.surface.candidateSetId, positioned)
          } else {
            const card = cardBySetId.get(ev.candidateSetId)
            if (card?.candidates !== undefined) {
              card.candidates = { ...card.candidates, selected: ev.selected }
            }
          }
        }
        continue
      }
      pushRow({
        id: m.id,
        role: "assistant",
        content: m.content ?? "",
        outputRefs: deliveryOutputRefs(m.intent),
        at: m.created_at,
        // The presenting row's storyboard block references replay with it
        // (the card resolves its DTO client-side; absent on legacy rows).
        blocks: m.blocks?.length ? m.blocks : undefined,
      })
    }
  }
  return history
}
