/** SSE frame routing (Phase 3 Batch A test seam — extracted from
 * chat-stream.ts's onmessage, 行为零变化): the PURE event-name → typed-frame
 * dispatch. JSON.parse stays inside the router so a malformed frame throws
 * exactly where the inline dispatch used to throw (fetch-event-source routes
 * the throw to onerror — same failure semantics as before).
 *
 * The frame vocabulary is the three-channel separation (ADR-087 §1):
 * System Status (`assistant.thinking`) / Activity (`assistant.activity`) /
 * Conversation (`assistant.delta` / `assistant.checkpoint` /
 * `question.preview`) + the terminal pair. Unknown events route to
 * "ignored" (heartbeat comment frames never reach onmessage at all). */

/** One user-safe activity frame (ADR-087 §3 Phase 2 — the append-oriented
 * Activity Stream). Status flips arrive as NEW frames carrying the same
 * `activity_id` (append-only wire; the client keeps an ordered map keyed by
 * id). `kind` is a user-semantic category — never a tool name; `key` is the
 * i18n copy identity for THAT status (active = progressive form, completed =
 * past-tense form, failed/cancelled = the active form, the ✗ says the rest).
 * The field set is the contract's whitelist — no params, results, or
 * reasoning ever ride this channel. */
export interface ActivityFramePayload {
  activity_id: string
  seq: number
  kind: "read" | "draft" | "run" | "repair"
  status: "active" | "completed" | "failed" | "cancelled"
  key: string | null
  /** 工作会话里程碑 (iter-2 ⑥, N-57): the whitelist's one extension — the
   * artifact count on `chat.explore.*Ready` frames, absent elsewhere. */
  count?: number
}

/** The thinking frame's payload: `{}` = a pure keepalive (drive the
 * indicator, never render); `{phase}` = a REAL System Status label
 * (`composing` — the sole survivor after Phase 3 Batch B retired
 * `creating_run` on the B4 dead-window forensics); `{phase: null}` = the
 * EXPLICIT phase clear (I-PFA-06 清除协议, 2026-09-18). `"phase" in
 * payload` separates the clear from a bare keepalive. Work evidence never
 * rides this channel (Phase 3 Batch B ③ — the retired inspecting key and
 * the drafting/repairing labels live on the Activity channel). */
export interface ThinkingPayload {
  phase?: string | null
}

/** The ask verdict's pill payload at object close (2026-09-09 用户拍板 ——
 * 「选项该和这句话一起来」): preview-dock from this frame; the terminal
 * envelope stays authoritative (envelope always wins). */
export interface QuestionPreviewPayload {
  question?: string | null
  options?: { id: string; label: string }[]
  allow_freeform?: boolean
  slot?: string | null
  default_path?: string | null
}

/** One routed stream frame — the onmessage dispatch's discriminated
 * output. `envelope`/`detail` stay `unknown`: the caller owns the envelope
 * type (the two surfaces type it differently). */
export type RoutedStreamFrame =
  | { kind: "delta"; text: string }
  | { kind: "thinking"; payload: ThinkingPayload }
  | { kind: "question_preview"; payload: QuestionPreviewPayload }
  | { kind: "checkpoint"; text: string }
  | { kind: "activity"; frame: ActivityFramePayload }
  | { kind: "completed"; envelope: unknown }
  | { kind: "failed"; detail: unknown; persisted: boolean }
  | { kind: "ignored" }

/** Route one SSE message to its typed frame. `terminal` names the turn's
 * terminal events ({completed, failed} — chat and answer turns differ).
 * Throws on malformed JSON (same as the retired inline dispatch). */
export function routeStreamFrame(
  event: string,
  data: string,
  terminal: { completed: string; failed: string },
): RoutedStreamFrame {
  if (event === "assistant.delta") {
    const parsed = JSON.parse(data) as { text: string }
    return { kind: "delta", text: parsed.text }
  }
  if (event === "assistant.thinking") {
    return { kind: "thinking", payload: JSON.parse(data) as ThinkingPayload }
  }
  if (event === "question.preview") {
    return {
      kind: "question_preview",
      payload: JSON.parse(data) as QuestionPreviewPayload,
    }
  }
  if (event === "assistant.checkpoint") {
    const parsed = JSON.parse(data) as { text: string }
    return { kind: "checkpoint", text: parsed.text }
  }
  if (event === "assistant.activity") {
    return { kind: "activity", frame: JSON.parse(data) as ActivityFramePayload }
  }
  if (event === terminal.completed) {
    return { kind: "completed", envelope: JSON.parse(data) }
  }
  if (event === terminal.failed) {
    const parsed = JSON.parse(data) as {
      detail?: unknown
      persisted?: boolean
    }
    return {
      kind: "failed",
      detail: parsed.detail,
      persisted: !!parsed.persisted,
    }
  }
  return { kind: "ignored" }
}
