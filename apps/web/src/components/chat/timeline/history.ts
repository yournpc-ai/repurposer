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
  ActivityRowFrame,
  CandidateMemberPayload,
  CandidateSurface,
  OverlayMessage,
  QuestionAnswer,
  QuestionMessage,
  SuggestionPill,
  VideoReviewIssueCode,
  VideoReviewReceipt,
} from "./types"

/** Resolve an answer payload to its display line. Bail variants are
 * localized (a graceful exit, never an error); freeform shows its text. */
export function answeredQuestionText(
  answer: QuestionAnswer,
  t: (key: string) => string,
  /** The answered question carried a run (interrupt): its bail stops the
   * run, it doesn't send the project back to draft — different copy. */
  hasRun?: boolean,
): { text: string; muted: boolean } {
  if (answer.kind === "bail") {
    if (answer.text === "superseded") {
      return { text: t("chat.qa.superseded"), muted: true }
    }
    return hasRun
      ? { text: t("chat.qa.stopped"), muted: true }
      : { text: t("chat.qa.cancelled"), muted: true }
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

/** The explicit deterministic-option association persisted on the real user row. */
export function answeredQuestionIdFromIntent(intent: unknown): string | undefined {
  const data = (intent ?? {}) as Record<string, unknown>
  return typeof data.answered_question_id === "string" && data.answered_question_id
    ? data.answered_question_id
    : undefined
}

/** The selected option's original label, never the formatted answer line. */
function selectedOptionLabel(message: QuestionMessage): string | undefined {
  if (message.answer?.kind !== "option" || !message.answer.option_id) return undefined
  return message.question?.options?.find((option) => option.id === message.answer?.option_id)?.label
}

/** The trigger dump on an assistant row's intent column ({type:
 * "trigger_review", trigger, ref, suggestions}). Read tolerance: anything
 * off-shape parses to undefined (a plain assistant row), never a crash. */
export function triggerSuggestions(intent: unknown): SuggestionPill[] | undefined {
  const data = (intent ?? {}) as Record<string, unknown>
  if (data.type !== "trigger_review") return undefined
  const raw = Array.isArray(data.suggestions) ? data.suggestions : []
  return raw
    .map((s) => (s ?? {}) as Record<string, unknown>)
    .filter(
      (s) =>
        typeof s.label === "string" &&
        (s.action === "send" || s.action === "download")
    )
    .map((s) => ({
      label: s.label as string,
      action: s.action as "send" | "download",
      text: (s.text as string | null) ?? null,
      output_id: (s.output_id as string | null) ?? null,
    }))
}

export function triggerDeliveryRef(intent: unknown): string | undefined {
  const data = (intent ?? {}) as Record<string, unknown>
  return data.type === "trigger_review" && typeof data.ref === "string"
    ? data.ref
    : undefined
}

export function triggerOutputRefs(intent: unknown): string[] {
  const data = (intent ?? {}) as Record<string, unknown>
  if (data.type !== "trigger_review" || !Array.isArray(data.output_refs)) {
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

/** Shared live/history receipt reader. Malformed evidence degrades to the
 * ordinary Activity category; unknown audio codes alone are ignored. */
export function parseActivityReceipt(value: unknown): VideoReviewReceipt | undefined {
  const root = receiptRecord(value)
  if (!root || root.kind !== "video_review") return undefined
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

/** A persisted activity array row (ADR-108 §2 — 每帧一行): intent =
 * {type:"activity", frame}. The frame is the server's open/settle dump —
 * its `at` is the birth stamp (execute entry for a read span), a settle
 * merge adds the terminal status / past-tense key / duration_ms IN PLACE.
 * Read tolerance: an off-shape frame parses to undefined and the ROW is
 * skipped by the caller (a malformed activity entry never becomes an empty
 * bubble). */
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
    kind: d.kind as ActivityRowFrame["kind"],
    status: d.status as ActivityRowFrame["status"],
    key: typeof d.key === "string" ? d.key : null,
    at: typeof d.at === "string" ? d.at : undefined,
    count: typeof d.count === "number" ? d.count : undefined,
    duration_ms: typeof d.duration_ms === "number" ? d.duration_ms : undefined,
    receipt: parseActivityReceipt(d.receipt),
  }
}

/** Intent types that never render (ADR-108 greenfield 口径):
 * ``activity_forensics`` rows are the server-side rejection ledger (audit
 * only); legacy ``activity_log`` aggregate rows were materialized into
 * per-frame rows by the W5 migration — an unmigrated leftover accepts the
 * loss rather than rendering an empty bubble. */
const NON_RENDER_INTENT_TYPES = new Set(["activity_forensics", "activity_log"])

export function isNonRenderIntent(intent: unknown): boolean {
  const data = (intent ?? {}) as Record<string, unknown>
  return typeof data.type === "string" && NON_RENDER_INTENT_TYPES.has(data.type)
}

/** A persisted material beat replayed as an activity row (2026-09-24
 * 素材节拍入库): wire-frame shape plus the beat's own interpolation fields
 * (the file's `name`, the batch progress `total` for the "N/M" label). */
type MaterialBeatRow = ActivityRowFrame

/** The material-beat dump on a message row's intent column ({type:
 * "material_beat", beat, status, name?, count?, total?, ref?, duration_ms?,
 * at?})
 * — the pipeline's settled reading/understanding rows (app/chat/service's
 * record_material_beat). Beats are BORN SETTLED (the live active row stays
 * the dock's synthesized now-line); the replay renders the past-tense key.
 * `duration_ms` carries the user-perceived reading span (upload→processed)
 * so the settled row whispers "· 41s" like every other settled row; `at`
 * carries the beat's real start when the span predates the
 * landing (the retired storyboard draft beat), feeding the fold's clock.
 * Same read tolerance as triggerSuggestions — anything off-shape parses to
 * undefined (a plain assistant row), never a crash. */
export function materialBeat(intent: unknown): MaterialBeatRow | undefined {
  const data = (intent ?? {}) as Record<string, unknown>
  if (data.type !== "material_beat") return undefined
  const status = data.status === "failed" ? ("failed" as const) : ("completed" as const)
  const count = typeof data.count === "number" ? data.count : undefined
  const total = typeof data.total === "number" ? data.total : undefined
  const name = typeof data.name === "string" ? data.name : undefined
  const duration_ms =
    typeof data.duration_ms === "number" ? data.duration_ms : undefined
  const ref = typeof data.ref === "string" ? data.ref : "beat"
  // The beat's own birth stamp: a beat whose span STARTS before
  // its row lands (the storyboard draft) carries `at` so the fold's clock
  // measures the real span, never the landing instant. Absent on beats
  // whose span starts at landing — the row's created_at falls in.
  const at = typeof data.at === "string" ? data.at : undefined
  if (data.beat === "reading") {
    // 动词分叉 (批「动词」): the persisted intent carries asset_type (absent
    // on rows predating the fork — read tolerance: they fall to the base key).
    const assetType =
      typeof data.asset_type === "string" ? data.asset_type : undefined
    return {
      activity_id: `beat-reading-${ref}`,
      seq: 0,
      kind: "read",
      status,
      key:
        status === "failed"
          ? materialBeatKey("chat.material.readingFailed", assetType)
          : total != null && total > 1
            ? materialBeatKey("chat.material.readingDoneProgress", assetType)
            : materialBeatKey("chat.material.readingDone", assetType),
      count,
      total,
      name,
      duration_ms,
      assetType,
    }
  }
  if (data.beat === "understanding") {
    return {
      activity_id: `beat-understanding-${ref}`,
      seq: 0,
      kind: "read",
      status,
      key: "chat.material.understandingDone",
      count,
    }
  }
  // 起草落定节拍（legacy 回放）: a film dock's deferred draft
  // settled — the row replays as this settled activity unit, its `at`
  // carrying the REAL drafting span's start. The draft KIND survives
  // 落定即退役's filter: that retirement keys on chat.activity.* plan-draft
  // spans, never on a born-settled beat.
  if (data.beat === "storyboard_drafting") {
    return {
      activity_id: `beat-storyboard-${ref}`,
      seq: 0,
      kind: "draft",
      status,
      key: "chat.storyboard.draftingDone",
      duration_ms,
      at,
    }
  }
  return undefined
}

/** 动词分叉 (2026-09-27 批「动词」): the material beat's verb follows the
 * asset type — video/audio get the typed key suffix, everything else the
 * base key. Both synthesis points fork alike (the live now-line reads the
 * asset's type; this replay reads the persisted beat's intent.asset_type);
 * the typed keys exist in every locale (zh.ts/en.ts are type-checked pairs),
 * so no missing-key fallback is needed. */
export function materialBeatKey(base: string, assetType?: string | null): string {
  return assetType === "video" || assetType === "audio"
    ? `${base}_${assetType}`
    : base
}

/** One parsed candidates_log event (the replay-fold input). */
export type CandidatesLogEvent =
  | { kind: "set"; surface: CandidateSurface }
  | { kind: "selection"; candidateSetId: string; selected: number[] }

/** A persisted turn's candidate-surface events (intent.type ===
 * "candidates_log" — the activity_log precedent's twin, v4.2 C8-c): the
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
    if (d.kind === "set") {
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
  role: "user" | "assistant"
  focus_output?: { id: string; label: string } | null
  attachments?: MessageAttachment[]
  skill?: SkillReference | null
}

/** Strict read tolerance for old rows only: the next persisted user row must
 * repeat the selected option label verbatim. This never assigns turn ownership. */
function legacyOptionAnswerAssociations(rows: HistoryRow[]): Map<string, string> {
  const associations = new Map<string, string>()
  for (let index = 0; index + 1 < rows.length; index += 1) {
    const question = rows[index]
    const user = rows[index + 1]
    if (
      question.role !== "assistant" ||
      question.question?.kind !== "question" ||
      question.answer?.kind !== "option" ||
      user.role !== "user"
    ) {
      continue
    }
    const label = selectedOptionLabel(question)
    const answerText = question.answer.text
    const isExactOptionAnswer =
      answerText == null || answerText === "" || answerText === label
    if (
      label !== undefined &&
      isExactOptionAnswer &&
      user.content === label
    ) {
      associations.set(user.id, question.id)
    }
  }
  return associations
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
  const legacyAnsweredQuestionIds = legacyOptionAnswerAssociations(rows)
  // C8-c fold: candidate set id → the OverlayMessage anchoring its card, so
  // a LATER turn's selection event repaints the earlier card's highlight
  // (the surface is one seat; rows never move).
  const cardBySetId = new Map<string, OverlayMessage>()
  for (const m of rows) {
    // Every projection of one persisted row carries its transcript position,
    // including an echo + QA pair. Recovered live rows can therefore find
    // their existing successor without re-deriving order from timestamps.
    const pushRow = (row: OverlayMessage): OverlayMessage => {
      const positioned = {
        ...row,
        turnId: m.turn_id ?? undefined,
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
        answeredQuestionId:
          answeredQuestionIdFromIntent(m.intent) ?? legacyAnsweredQuestionIds.get(m.id),
        at: m.created_at,
        focus: m.focus_output ?? undefined,
        // Sent attachments persist on the message row — re-render the
        // chips so a refresh / another device keeps the record.
        assets: messageAssetsFromAttachments(m.attachments ?? []),
      })
    } else if (m.question) {
      const hasOptions = (m.question.options?.length ?? 0) > 0
      if (m.answer) {
        if (m.question.kind === "task_book") {
          // echo 实体化 (2026-09-04, A3): the row's content IS the
          // echo prose (A1) — replay it as its own flow message so
          // the confirm beat survives a refresh. NO QA archive:
          // task_book 的 start 确认（chat 文本 / pill 手势同）不是
          // option 选择——QA 块只归真问答（2026-09-05 用户拍板），
          // 薄书的记录 = echo + 用户原话 + run 收据行。
          if ((m.content ?? "").trim()) {
            pushRow({
              id: `${m.id}-echo`,
              role: "assistant",
              content: m.content ?? "",
              // The start's workflow_run_id rides the replay (parity
              // with the plain-row branch): the stamp is the
              // run↔message association the detached RunBlock archive reads.
              runId: m.workflow_run_id,
              at: m.created_at,
              // The answered video dock's canonical storyboard block
              // replays with its echo (Video Project phase B) — the card
              // resolves the SAVED version's DTO, never the prose.
              blocks: m.blocks?.length ? m.blocks : undefined,
            })
          }
        } else if (hasOptions) {
          // ask 三分解剖: the framing prose replays as its own flow
          // message first (it sat above the dock live), then the QA
          // block quotes the BARE question — a refresh reads like the
          // live flow did.
          const echo = questionEcho(m)
          if (echo) {
            pushRow({
              id: `${m.id}-echo`,
              role: "assistant",
              content: echo,
              runId: m.workflow_run_id,
              runDelivery: triggerSuggestions(m.intent) !== undefined,
              runDeliveryRef: triggerDeliveryRef(m.intent),
              outputRefs: triggerOutputRefs(m.intent),
              independentKind: triggerSuggestions(m.intent) !== undefined ? "trigger" : undefined,
              at: m.created_at,
            })
          }
          const display = answeredQuestionText(
            m.answer,
            ctx.t,
            !!m.workflow_run_id,
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
            runId: m.workflow_run_id,
            at: m.created_at,
          })
        }
      } else if (m.question.kind === "task_book" && m.question.storyboard_echo) {
        // 分镜 echo 回放 (dock echo 形态): a PENDING film dock's echo —
        // prose + the code-rendered storyboard markdown + the estimate
        // tail — replays as a normal flow message while the dock itself
        // revives through the pending-question fetch. No run stamp: the
        // run only exists once the dock is answered.
        if ((m.content ?? "").trim()) {
          pushRow({
            id: `${m.id}-echo`,
            role: "assistant",
            content: m.content ?? "",
            at: m.created_at,
            blocks: m.blocks?.length ? m.blocks : undefined,
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
          runId: m.workflow_run_id,
          at: m.created_at,
        })
      } else if (m.question.kind === "task_book" && (m.blocks?.length ?? 0) > 0) {
        // Video Project phase B: a PENDING produce dock's turn replays its
        // reply prose AND its canonical storyboard block — the revived card
        // re-presents after a refresh/reconnect, and its presentation
        // completion ACK is the authorized delayed-start's only trigger.
        // Without this row the held start could never fire post-refresh.
        pushRow({
          id: `${m.id}-echo`,
          role: "assistant",
          content: m.content ?? "",
          at: m.created_at,
          blocks: m.blocks,
        })
      } else if (m.question.kind === "question") {
        // A pending OPTIONS question docks (the pill revives via the
        // pending_question fetch) — its framing prose replays as a
        // flow message so the refresh reads like the live flow did.
        const echo = questionEcho(m)
        if (echo) {
          pushRow({
            id: `${m.id}-echo`,
            role: "assistant",
            content: echo,
            runId: m.workflow_run_id,
            runDelivery: triggerSuggestions(m.intent) !== undefined,
            runDeliveryRef: triggerDeliveryRef(m.intent),
            outputRefs: triggerOutputRefs(m.intent),
            independentKind: triggerSuggestions(m.intent) !== undefined ? "trigger" : undefined,
            at: m.created_at,
          })
        }
      }
    } else {
      // 永不渲染行 (ADR-108): the rejection forensics ledger and legacy
      // aggregate logs skip silently — never an empty bubble.
      if (isNonRenderIntent(m.intent)) continue
      const intentType = ((m.intent ?? {}) as Record<string, unknown>).type
      // 退役分镜块 (dock echo 形态): legacy storyboard block rows (usually
      // empty content) skip silently — an old project shows only the old
      // storyboard_ready markdown row. A legacy draft-failure row's real
      // prose falls through and replays as ordinary text (no marker); an
      // empty one skips (no-empty-bubble law).
      if (intentType === "storyboard") continue
      if (intentType === "storyboard_draft_failed" && !(m.content ?? "").trim()) continue
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
      // 素材节拍回放 (2026-09-24): a persisted beat row replays as a
      // settled activity unit IN ITS ARRAY POSITION, never a bubble.
      const beat = materialBeat(m.intent)
      if (beat !== undefined) {
        pushRow({
          id: m.id,
          role: "assistant",
          content: "",
          at: m.created_at,
          independentKind: "material",
          activity: { ...beat, at: beat.at ?? m.created_at },
        })
        continue
      }
      // An unknown (or empty) beat row skips — never an empty bubble.
      if (intentType === "material_beat" && !(m.content ?? "").trim()) continue
      // activity 数组行回放 (ADR-108 — 每帧一行): one persisted frame per
      // row, rendered at its array position (persisted order IS render
      // order — the walk never re-sorts).
      const frame = activityRowFrame(m.intent)
      if (frame !== undefined) {
        pushRow({
          id: m.id,
          role: "assistant",
          content: "",
          at: m.created_at,
          activity: frame,
        })
        continue
      }
      // A malformed activity row (frame off-shape) skips — never an empty
      // bubble.
      if (intentType === "activity") {
        continue
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
        runId: m.workflow_run_id,
        runDelivery: triggerSuggestions(m.intent) !== undefined,
        runDeliveryRef: triggerDeliveryRef(m.intent),
        outputRefs: triggerOutputRefs(m.intent),
        independentKind: triggerSuggestions(m.intent) !== undefined ? "trigger" : undefined,
        at: m.created_at,
        // from its intent dump — undefined on every other shape.
        suggestions: triggerSuggestions(m.intent),
        // The presenting row's storyboard block references replay with it
        // (the card resolves its DTO client-side; absent on legacy rows).
        blocks: m.blocks?.length ? m.blocks : undefined,
      })
    }
  }
  return history
}
