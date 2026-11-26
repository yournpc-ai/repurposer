/** SSE frame routing (Phase 3 Batch A test seam — extracted from
 * chat-stream.ts's onmessage, 行为零变化): the PURE event-name → typed-frame
 * dispatch. JSON.parse stays inside the router so a malformed frame throws
 * exactly where the inline dispatch used to throw (fetch-event-source routes
 * the throw to onerror — same failure semantics as before).
 *
 * The frame vocabulary is the three-channel separation (ADR-087 §1):
 * System Status (`assistant.thinking`) / Activity (`assistant.activity`) /
 * Conversation (`assistant.delta` / `assistant.interim_prose` /
 * `assistant.candidates` — the v4.2 C8-c Candidate
 * Surface channel) + the terminal pair. Unknown events route to
 * "ignored" (heartbeat comment frames never reach onmessage at all). */

import type {
  ActivityFramePayload,
  ActivityRowFrame,
  CandidateMemberPayload,
  CandidateSurface,
  DisplayRole,
  FailureCheckpoint,
  MessageBlock,
  OverlayMessage,
  QuestionMessage,
  StepPlanItem,
} from "@/components/chat/timeline/types"

/** The thinking frame's payload: `{}` = a pure keepalive (drive the
 * indicator, never render); `{phase}` = a REAL System Status label
 * (the film design span's capturing / storyboarding / storyboard_revision
 * are the sole survivors after Phase 3 Batch B); `{phase: null}` = the
 * EXPLICIT phase clear (I-PFA-06 清除协议, 2026-09-18). `"phase" in
 * payload` separates the clear from a bare keepalive. Work evidence never
 * rides this channel (Phase 3 Batch B ③ — the retired inspecting key and
 * the drafting/repairing labels live on the Activity channel). */
export interface ThinkingPayload {
  phase?: string | null
}


/** One ``assistant.candidates`` event. ``set`` = a transcript candidate
 * set's birth, ``sfx_set``/``music_set`` = the same envelope carrying audio
 * candidates (or idempotent re-emit — the client replaces by candidate_set_id);
 * ``selection`` = the set's FULL current selection (the client replaces,
 * never unions — a revise re-point drops the old pick by construction).
 * Chat decisions never become graph nodes; this channel is their only
 * surface. */
export type CandidateEventPayload =
  | {
      kind: "set" | "sfx_set" | "music_set" | "video_preset_set" | "voice_set"
      candidate_set_id: string
      topic: string
      asset_id?: string | null
      members: CandidateMemberPayload[]
      selected?: number[]
      turn_id?: string | null
    }
  | {
      kind: "selection"
      candidate_set_id: string
      selected: number[]
      turn_id?: string | null
    }

/** One routed stream frame — the onmessage dispatch's discriminated
 * output. `envelope`/`detail` stay `unknown`: the caller owns the envelope
 * type (the two surfaces type it differently). */
/** The transcript array's SSE mirror (ADR-108 §3): ``assistant.row.append``
 * fixes a row's position in the array, ``assistant.row.update`` mutates it
 * in place — the live reducer and the history replay eat the SAME semantics
 * (persisted order IS render order). The append payload mirrors
 * ChatMessageResponse; two families ride the channel — activity rows
 * (intent carries the frame) and plain assistant rows (ADR-129: the design
 * beat's published storyboard message). */
export interface RowAppendPayload {
  id: string
  role: "user" | "assistant"
  content: string
  turn_id?: string | null
  run_id?: string | null
  display_role?: DisplayRole | null
  seq?: number | null
  /** The row's intent dump — activity rows carry {type:"activity", frame}. */
  intent?: unknown
  question?: QuestionMessage["question"]
  answer?: QuestionMessage["answer"]
  /** Structured presentation blocks (Video Project phase B) — the
   * storyboard card's resolve references on the presenting row. */
  blocks?: MessageBlock[]
  steps?: StepPlanItem[] | null
  created_at?: string | null
}

/** The persisted activity row's frame shape (the ``intent.frame`` dump):
 * the wire ``ActivityFramePayload`` minus its live-channel bookkeeping
 * (`seq` — the array position already carries order), plus the settle
 * merge's stamps. */
export type ActivityRowFramePayload = Omit<ActivityFramePayload, "seq" | "kind" | "focus" | "steps"> & {
  kind: ActivityRowFrame["kind"]
  seq?: number
}

export type RoutedStreamFrame =
  | { kind: "turn_started"; turnId: string; runId?: string | null }
  | {
      kind: "decision_committed"
      runId: string | null
      turnId: string | null
      answeredQuestion: QuestionMessage
    }
  | {
      kind: "run_synced"
      active: boolean
      runId: string | null
      turnId: string | null
      liveFocus: string | null
      steps: StepPlanItem[] | null
    }
  | { kind: "delta"; text: string; messageId: string | null }
  | { kind: "thinking"; payload: ThinkingPayload }
  | { kind: "candidates"; event: CandidateEventPayload }
  | {
      kind: "interim_prose"
      text: string
      at?: string
      turnId: string | null
      runId?: string | null
      displayRole?: "stage_note" | "rail_note"
      messageId: string
      seq: number | null
    }
  | { kind: "activity"; frame: ActivityFramePayload }
  | { kind: "row_append"; row: RowAppendPayload }
  | { kind: "row_update"; id: string; frame: ActivityRowFramePayload }
  | {
      kind: "title_updated"
      projectId: string
      conversationId: string
      projectTitle?: string
      conversationTitle?: string
    }
  | { kind: "completed"; envelope: unknown }
  | {
      kind: "failed"
      detail: unknown
      persisted: boolean
      turnId: string | null
      runId?: string | null
      messageId?: string
      decisionCommitted?: boolean
      checkpoint?: FailureCheckpoint
    }
  | { kind: "ignored" }

/** Live Candidate Surface reducer. Set identity comes from the server frame;
 * selection repaints never adopt a neighbouring or current turn. */
export function reduceCandidateFrame(
  prev: OverlayMessage[],
  event: CandidateEventPayload,
  at: string,
): OverlayMessage[] {
  if (event.kind === "selection") {
    return prev.map((message) =>
      message.candidates?.candidateSetId === event.candidate_set_id
        ? {
            ...message,
            candidates: { ...message.candidates, selected: event.selected },
          }
        : message,
    )
  }
  const initialSelected = Array.isArray(event.selected)
    ? event.selected.filter((i): i is number => typeof i === "number" && Number.isInteger(i) && i >= 0)
    : []
  const surface: CandidateSurface = {
    kind:
      event.kind === "video_preset_set" ||
      event.kind === "music_set" ||
      event.kind === "voice_set"
        ? event.kind
        : undefined,
    candidateSetId: event.candidate_set_id,
    topic: event.topic,
    assetId: event.asset_id ?? null,
    members: event.members,
    selected: initialSelected,
  }
  const exists = prev.some(
    (message) => message.candidates?.candidateSetId === event.candidate_set_id,
  )
  if (exists) {
    return prev.map((message) =>
      message.candidates?.candidateSetId === event.candidate_set_id
        ? {
            ...message,
            candidates: {
              ...surface,
              selected: Array.isArray(event.selected)
                ? initialSelected
                : (message.candidates?.selected ?? []),
            },
          }
        : message,
    )
  }
  return [
    ...prev,
    {
      id: `live-cand-${event.candidate_set_id}`,
      role: "assistant",
      content: "",
      turnId: event.turn_id ?? undefined,
      independentKind: event.turn_id ? undefined : "candidate",
      at,
      candidates: surface,
    },
  ]
}

/** Release tool-time candidates only after their turn's final prose has
 * drained. Pending rows have never occupied the visible timeline, so this is
 * their single birth directly behind the exact final reply — never a move.
 * Existing hydrated/live sets win by candidate_set_id, keeping replay and
 * idempotent re-emits from creating a second card. */
export function releaseSettledCandidateRows(
  prev: OverlayMessage[],
  pending: readonly OverlayMessage[],
  replyId: string,
): OverlayMessage[] {
  if (pending.length === 0) return prev
  const replyIndex = prev.findIndex(
    (message) => message.id === replyId && message.role === "assistant",
  )
  if (replyIndex < 0) return prev
  const turnId = prev[replyIndex].turnId
  if (!turnId) return prev
  const existing = new Set(
    prev.flatMap((message) =>
      message.candidates ? [message.candidates.candidateSetId] : [],
    ),
  )
  const candidates = pending.filter((message) =>
    message.candidates !== undefined &&
    message.turnId === turnId &&
    !existing.has(message.candidates.candidateSetId),
  )
  if (candidates.length === 0) return prev
  return [
    ...prev.slice(0, replyIndex + 1),
    ...candidates,
    ...prev.slice(replyIndex + 1),
  ]
}

/** Route one SSE message to its typed frame. `terminal` names the turn's
 * terminal events ({completed, failed} — chat and answer turns differ).
 * Throws on malformed JSON (same as the retired inline dispatch). */
export function routeStreamFrame(
  event: string,
  data: string,
  terminal: { completed: string; failed: string },
): RoutedStreamFrame {
  if (event === "turn.started") {
    const parsed = JSON.parse(data) as { turn_id: string; run_id?: string | null }
    return {
      kind: "turn_started",
      turnId: parsed.turn_id,
      ...(typeof parsed.run_id === "string" ? { runId: parsed.run_id } : {}),
    }
  }
  if (event === "decision.committed") {
    const parsed = JSON.parse(data) as {
      run_id?: string | null
      turn_id?: string | null
      answered_question: QuestionMessage
    }
    return {
      kind: "decision_committed",
      runId: typeof parsed.run_id === "string" ? parsed.run_id : null,
      turnId: typeof parsed.turn_id === "string" ? parsed.turn_id : null,
      answeredQuestion: parsed.answered_question,
    }
  }
  if (event === "run.synced") {
    const parsed = JSON.parse(data) as {
      active?: boolean
      run_id?: string | null
      turn_id?: string | null
      live_focus?: string | null
      steps?: StepPlanItem[] | null
    }
    return {
      kind: "run_synced",
      active: Boolean(parsed.active),
      runId: typeof parsed.run_id === "string" ? parsed.run_id : null,
      turnId: typeof parsed.turn_id === "string" ? parsed.turn_id : null,
      liveFocus: typeof parsed.live_focus === "string" ? parsed.live_focus : null,
      steps: Array.isArray(parsed.steps) ? parsed.steps : null,
    }
  }
  if (event === "assistant.delta") {
    const parsed = JSON.parse(data) as { text: string; message_id?: string | null }
    return {
      kind: "delta",
      text: parsed.text,
      messageId: typeof parsed.message_id === "string" ? parsed.message_id : null,
    }
  }
  if (event === "assistant.thinking") {
    return { kind: "thinking", payload: JSON.parse(data) as ThinkingPayload }
  }

  if (event === "assistant.candidates") {
    return {
      kind: "candidates",
      event: JSON.parse(data) as CandidateEventPayload,
    }
  }
  if (event === "assistant.interim_prose") {
    const parsed = JSON.parse(data) as {
      text: string
      at?: string | null
      turn_id?: string | null
      run_id?: string | null
      display_role?: string | null
      message_id?: unknown
      seq?: unknown
    }
    if (typeof parsed.message_id !== "string" || !parsed.message_id) {
      throw new Error("assistant.interim_prose requires message_id")
    }
    const displayRole =
      parsed.display_role === "rail_note" || parsed.display_role === "stage_note"
        ? parsed.display_role
        : undefined
    return {
      kind: "interim_prose",
      text: parsed.text,
      at: typeof parsed.at === "string" ? parsed.at : undefined,
      turnId: typeof parsed.turn_id === "string" ? parsed.turn_id : null,
      ...(typeof parsed.run_id === "string" ? { runId: parsed.run_id } : {}),
      ...(displayRole ? { displayRole } : {}),
      messageId: parsed.message_id,
      seq: typeof parsed.seq === "number" ? parsed.seq : null,
    }
  }
  if (event === "title.updated") {
    const parsed = JSON.parse(data) as {
      project_id?: string
      conversation_id?: string
      project_title?: string
      conversation_title?: string
    }
    if (typeof parsed.project_id === "string" && typeof parsed.conversation_id === "string") {
      return {
        kind: "title_updated",
        projectId: parsed.project_id,
        conversationId: parsed.conversation_id,
        ...(typeof parsed.project_title === "string"
          ? { projectTitle: parsed.project_title }
          : {}),
        ...(typeof parsed.conversation_title === "string"
          ? { conversationTitle: parsed.conversation_title }
          : {}),
      }
    }
    return { kind: "ignored" }
  }
  if (event === "assistant.activity") {
    return { kind: "activity", frame: JSON.parse(data) as ActivityFramePayload }
  }
  if (event === "assistant.row.append") {
    const parsed = JSON.parse(data) as { row: RowAppendPayload }
    return { kind: "row_append", row: parsed.row }
  }
  if (event === "assistant.row.update") {
    const parsed = JSON.parse(data) as { id: string; frame: ActivityRowFramePayload }
    return { kind: "row_update", id: parsed.id, frame: parsed.frame }
  }
  if (event === terminal.completed) {
    return { kind: "completed", envelope: JSON.parse(data) }
  }
  if (event === terminal.failed) {
    const parsed = JSON.parse(data) as {
      detail?: unknown
      persisted?: boolean
      message_id?: string
      turn_id?: string | null
      run_id?: string | null
      decision_committed?: boolean
      checkpoint?: FailureCheckpoint
    }
    return {
      kind: "failed",
      ...(typeof parsed.message_id === "string" ? { messageId: parsed.message_id } : {}),
      ...(typeof parsed.run_id === "string" ? { runId: parsed.run_id } : {}),
      ...(parsed.decision_committed === true ? { decisionCommitted: true } : {}),
      ...(parsed.checkpoint && typeof parsed.checkpoint === "object"
        ? { checkpoint: parsed.checkpoint }
        : {}),
      detail: parsed.detail,
      persisted: !!parsed.persisted,
      turnId: typeof parsed.turn_id === "string" ? parsed.turn_id : null,
    }
  }
  return { kind: "ignored" }
}
