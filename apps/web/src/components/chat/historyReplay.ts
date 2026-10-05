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
 * Wire types live here too (OverlayMessage / QuestionMessage / …): they
 * are the row vocabulary this mapper speaks, and ChatDock imports them
 * back — one source, no parallel copies. */

import {
  answeredQuestionText,
  type QuestionAnswer,
} from "./AnsweredQuestion"
import type { ActivityFramePayload } from "@/lib/chat-stream"
import type { CandidateMemberPayload } from "@/lib/chatStreamFrames"

/** One message row in the dock's flow (live-pushed or replayed). */
export interface OverlayMessage {
  id: string
  role: "user" | "assistant"
  content: string
  runId?: string | null
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
  /** Answered-question item (a settled question collapsing into the flow).
   * `questionId` = the settled row's id — the ask_user 不变量's join key:
   * a question whose QA archive is in the flow is DECIDED and must never
   * also render as the pending dock. */
  qa?: { question: string; answer: string; muted: boolean; detail?: string; questionId?: string }
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
  /** Trigger-turn suggestion pills — LEGACY REPLAY ONLY (ADR-081,
   * 2026-09-17): rows docked before the option-grammar unification carry
   * pill-shaped suggestions in the intent dump and replay as chips; new
   * rows dock a REAL numbered options question (messages.question payload)
   * instead and this stays undefined/empty. Set only after the row's prose
   * has drained (散文永远在先、提问随后). */
  suggestions?: SuggestionPill[]
  /** 素材节拍回放 (2026-09-24 素材节拍入库): a persisted material-beat row
   * (intent.type === "material_beat") replays as a SETTLED activity row,
   * never a bubble — the dock splits it out of the message stream into the
   * activity stream (the settled gray "已读完 X" survives a refresh). */
  beat?: MaterialBeatRow
  /** activity 持久化回放 (2026-09-25): a persisted turn's settled milestone
   * frames (intent.type === "activity_log"). The dock merges ONLY the
   * LATEST turn's frames into the activity stream — parity with the live
   * law (U9: a new turn's stream replaces the previous turn's rows). */
  milestones?: ActivityFramePayload[]
  /** Candidate Surface (Workspace 合同 v4.2 C8-c): the replayed (or live)
   * candidate card — the set's members + the CURRENT selection highlight
   * (folded from every selection event up to this point). The card renders
   * under its anchoring message; selection events from LATER turns repaint
   * it in place (chat 决策永不成节点 — the card is the selection state's
   * one seat). */
  candidates?: CandidateSurface
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

/** The trigger dump on a proactive row's intent column ({type:
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

/** The trigger's own name off a trigger_review dump ("run_completed" /
 * "craft_decompiled" — ADR-102 retired "understanding_warmed"). Same read
 * tolerance as triggerSuggestions. */
export function triggerName(intent: unknown): string | undefined {
  const data = (intent ?? {}) as Record<string, unknown>
  if (data.type !== "trigger_review") return undefined
  return typeof data.trigger === "string" ? data.trigger : undefined
}

/** A persisted turn's settled activity frames (2026-09-25 activity 持久化):
 * the SSE turn route stores the projector's settled_frames() as ONE message
 * row per turn ({type:"activity_log", ref, frames:[…]}). The replay
 * restores ONLY the LATEST turn's log — parity with the live law (U9: the
 * next turn's stream replaces the previous turn's rows), never rows the
 * live flow didn't show. Read tolerance: any off-shape frame drops the
 * whole dump to undefined (a plain assistant row), never a crash. */
export function activityLog(intent: unknown): ActivityFramePayload[] | undefined {
  const data = (intent ?? {}) as Record<string, unknown>
  if (data.type !== "activity_log") return undefined
  const raw = Array.isArray(data.frames) ? data.frames : null
  if (raw === null) return undefined
  const KINDS = new Set(["read", "draft", "run", "repair"])
  const STATUSES = new Set(["completed", "failed", "cancelled"])
  const frames: ActivityFramePayload[] = []
  for (const f of raw) {
    const d = (f ?? {}) as Record<string, unknown>
    if (
      typeof d.activity_id !== "string" ||
      typeof d.seq !== "number" ||
      typeof d.kind !== "string" ||
      !KINDS.has(d.kind) ||
      typeof d.status !== "string" ||
      !STATUSES.has(d.status) // settled only — an active frame never persists
    ) {
      return undefined
    }
    frames.push({
      activity_id: d.activity_id,
      seq: d.seq,
      kind: d.kind as ActivityFramePayload["kind"],
      status: d.status as ActivityFramePayload["status"],
      key: typeof d.key === "string" ? d.key : null,
      at: typeof d.at === "string" ? d.at : undefined,
      count: typeof d.count === "number" ? d.count : undefined,
      duration_ms: typeof d.duration_ms === "number" ? d.duration_ms : undefined,
    } as ActivityFramePayload)
  }
  return frames
}

/** A persisted material beat replayed as an activity row (2026-09-24
 * 素材节拍入库): wire-frame shape plus the beat's own interpolation fields
 * (the file's `name`, the batch progress `total` for the "N/M" label). */
export type MaterialBeatRow = ActivityFramePayload & {
  name?: string
  total?: number
}

/** The material-beat dump on a message row's intent column ({type:
 * "material_beat", beat, status, name?, count?, total?, ref?, duration_ms?})
 * — the pipeline's settled reading/understanding rows (app/chat/service's
 * record_material_beat). Beats are BORN SETTLED (the live active row stays
 * the dock's synthesized now-line); the replay renders the past-tense key.
 * `duration_ms` carries the user-perceived reading span (upload→processed)
 * so the settled row whispers "· 41s" like every other settled row.
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
   * recommends — the dock renders its muted suffix. Absent on legacy rows
   * and unrecommended asks. */
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
  /** 决策包阅读层 (iter-2 ③): task_book only — the Content Plans behind
   * the compiled chain; empty on the router-drafted docks (读容忍). */
  plans?: DecisionPlanRow[]
}

/** A question-carrying chat message (the ask_user machinery): the dock's pending
 * question and, once answered, its collapsed form in the flow. */
export interface QuestionMessage {
  id: string
  content: string | null
  /** The row's intent JSONB: task_book docks stamp the presented chain
   * here (计划行自完备, 方案 B — the envelope's row IS the whole plan
   * card, no second fetch); ask questions stash their replay payload.
   * Null on rows docked before the seal. */
  intent?: unknown
  question: QuestionPayload | null
  answer: QuestionAnswer | null
  workflow_run_id: string | null
  /** 建议谱系交互块 (ADR-099 §4): the row's persisted non-blocking
   * suggestion records (empty on every older row — 读容忍). */
  suggestions?: unknown
  /** ask 预览帧的乐观 dock (2026-09-09): the ask object closed stream-side
   * but the turn's tail — and with it the row's server-side birth — is
   * still generating, so this id does NOT exist server-side yet. A click
   * stashes and fires at the envelope's authoritative dock; a flip or
   * turn.failed rolls the preview back. Never persisted anywhere. */
  preview?: boolean
  created_at?: string
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

/** One archive row as the messages endpoint returns it (the mapper's input
 * wire — QuestionMessage plus the user-row extras). */
export interface HistoryRow extends QuestionMessage {
  role: "user" | "assistant"
  focus_output?: { id: string; label: string } | null
  attachments?: {
    id: string
    name: string
    type: string
    url?: string | null
  }[]
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
    if (m.role === "user") {
      history.push({
        id: m.id,
        role: "user",
        content: m.content ?? "",
        at: m.created_at,
        focus: m.focus_output ?? undefined,
        // Sent attachments persist on the message row — re-render the
        // chips so a refresh / another device keeps the record.
        assets: (m.attachments ?? []).map((a) => ({
          id: a.id,
          type: a.type,
          file_url: a.url ?? null,
          title: a.name,
          processing_status: "completed" as const,
        })),
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
            history.push({
              id: `${m.id}-echo`,
              role: "assistant",
              content: m.content ?? "",
              // The start's workflow_run_id rides the replay (parity
              // with the plain-row branch): the stamp is the
              // run↔message association the detached-run archive
              // (inline RunCard) reads.
              runId: m.workflow_run_id,
              at: m.created_at,
            })
          }
        } else if (hasOptions) {
          // ask 三分解剖: the framing prose replays as its own flow
          // message first (it sat above the dock live), then the QA
          // block quotes the BARE question — a refresh reads like the
          // live flow did.
          const echo = questionEcho(m)
          if (echo) {
            history.push({
              id: `${m.id}-echo`,
              role: "assistant",
              content: echo,
              at: m.created_at,
            })
          }
          const display = answeredQuestionText(
            m.answer,
            ctx.t,
            !!m.workflow_run_id,
          )
          history.push({
            id: m.id,
            role: "assistant",
            content: "",
            at: m.created_at,
            qa: {
              question: bareQuestion(m),
              answer: display.text,
              muted: display.muted,
              questionId: m.id,
            },
          })
        } else {
          // 形态律 (ADR-053 R1): an options-empty question's answered
          // form is the plain message pair — the question line stays a
          // plain assistant message, no AnsweredQuestion block.
          history.push({
            id: m.id,
            role: "assistant",
            content: m.content ?? "",
            runId: m.workflow_run_id,
            at: m.created_at,
          })
        }
      } else if (m.question.kind === "question" && !hasOptions) {
        // 形态律 (ADR-053 R1): a pending TEXT question never docks —
        // it lives in the flow as a plain assistant message (only
        // options questions raise the pill).
        history.push({
          id: m.id,
          role: "assistant",
          content: m.content ?? "",
          runId: m.workflow_run_id,
          at: m.created_at,
        })
      } else if (m.question.kind === "question") {
        // A pending OPTIONS question docks (the pill revives via the
        // pending_question fetch) — its framing prose replays as a
        // flow message so the refresh reads like the live flow did.
        const echo = questionEcho(m)
        if (echo) {
          history.push({
            id: `${m.id}-echo`,
            role: "assistant",
            content: echo,
            at: m.created_at,
          })
        }
      }
    } else {
      // 素材节拍回放 (2026-09-24): a persisted beat row replays as a
      // settled activity unit, never a bubble — the dock splits it out of
      // the message stream (flowMessages / replayedBeats).
      const beat = materialBeat(m.intent)
      if (beat !== undefined) {
        history.push({
          id: m.id,
          role: "assistant",
          content: "",
          at: m.created_at,
          beat: { ...beat, at: m.created_at },
        })
        continue
      }
      // activity 持久化回放 (2026-09-25): a turn's settled milestone log
      // rides as one row's payload — the dock merges the LATEST turn's
      // frames into the activity stream (U9 parity), never a bubble.
      const log = activityLog(m.intent)
      if (log !== undefined) {
        history.push({
          id: m.id,
          role: "assistant",
          content: "",
          at: m.created_at,
          milestones: log,
        })
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
              candidates: ev.surface,
            }
            history.push(row)
            cardBySetId.set(ev.surface.candidateSetId, row)
          } else {
            const card = cardBySetId.get(ev.candidateSetId)
            if (card?.candidates !== undefined) {
              card.candidates = { ...card.candidates, selected: ev.selected }
            }
          }
        }
        continue
      }
      history.push({
        id: m.id,
        role: "assistant",
        content: m.content ?? "",
        runId: m.workflow_run_id,
        at: m.created_at,
        // 触发回合回放 (T3): a proactive review row's pills rebuild
        // from its intent dump — undefined on every other shape.
        suggestions: triggerSuggestions(m.intent),
      })
    }
  }
  return history
}
