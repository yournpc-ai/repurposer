/** Chat turn SSE client (CHAT_ARCH §8): the streaming transport for POST /chat
 * and its answer endpoint.
 *
 * Same endpoint, same payload as the plain apiFetch call — the difference is
 * the `Accept: text/event-stream` header, which flips the server into its
 * streaming mode: `assistant.delta` prose previews while the verdict JSON
 * generates, then one terminal frame carrying the exact response envelope
 * (the envelope always wins — deltas are a preview channel, never the source
 * of truth) or a `.failed` frame (a mid-stream failure the JSON path would
 * surface as an HTTP error).
 *
 * Uses fetch-event-source because native EventSource is GET-only and cannot
 * send the Authorization header. Auto-reconnect is DISABLED on both turns: a
 * retried POST would persist the user message a second time (chat) or
 * double-settle the question (answer — the row-lock turns the retry into a
 * 409, but the optimistic UI must not flicker through a phantom retry), so
 * every close/error path terminates the promise.
 */

import { fetchEventSource } from "@microsoft/fetch-event-source"

import { API_URL, UNAUTHORIZED_EVENT } from "@/lib/api"
import { clearAuth, getToken } from "@/lib/auth"
import i18n from "@/lib/i18n"
import { routeStreamFrame } from "@/lib/chatStreamFrames"

// The frame vocabulary's single seat is chatStreamFrames.ts (Phase 3 Batch
// A test seam) — re-exported here so existing import sites stay put.
export type {
  ActivityFramePayload,
  QuestionPreviewPayload,
  ThinkingPayload,
} from "@/lib/chatStreamFrames"
import type {
  ActivityFramePayload,
  QuestionPreviewPayload,
  ThinkingPayload,
} from "@/lib/chatStreamFrames"

export interface ChatTurnBody {
  project_id: string
  message: string
  mentions?: { type: string; id: string; label: string; quote?: string }[]
  /** Files staged in the input group and sent with this turn (the server
   * persists them on the user message row — refresh re-renders the chips). */
  attachments?: {
    id: string
    name: string
    type: "file" | "image" | "video" | "audio"
    url?: string
    size?: number
    status: "uploaded"
  }[]
  /** The composer's persona choice, riding the first message of a fresh
   * project (ADR-038 — the single identity payload; the skin follows the
   * persona). */
  persona_id?: string
  prior_intent?: unknown
  autonomy?: string
}

export interface StreamChatOptions {
  signal: AbortSignal
  /** Decoded prose fragment, in order — concatenate to render the preview. */
  onDelta?: (text: string) => void
  /** System Status frame: fires with `{}` as a pure keepalive (reasoning
   * fragments / non-prose JSON chunks — drive the indicator, never render),
   * or with `{phase: "composing"}` at a REAL macro-state switch (the sole
   * survivor — `"creating_run"` was deleted in Batch B ⑤ after the B4 CDP
   * dead-window forensics proved it never the sole cover) — the client
   * labels its status row from the phase and leaves it untouched on bare
   * keepalives. Work evidence never rides this channel (Phase 3 Batch B ③:
   * the retired drafting/inspecting/repairing labels live on the Activity
   * channel).
   * `{phase: null}` is the EXPLICIT phase clear
   * (I-PFA-06 清除协议, 2026-09-18): every call's name-known moment ends
   * the previous label — reset to the base label. The
   * `"phase" in payload` check separates the clear from a bare keepalive. */
  onThinking?: (payload: ThinkingPayload) => void
  /** The ask verdict's pill payload the moment its object closes in the
   * stream (2026-09-09 用户拍板——「选项该和这句话一起来」; object-level
   * trust: the ask object's prose key streams first, so question/options/
   * default_path are complete when the echo ends — the verdict's brief tail
   * is still generating). Preview-dock the pill from this frame; the
   * terminal envelope stays authoritative (envelope always wins), and a
   * flipped / failed turn rolls the preview back. */
  onQuestionPreview?: (payload: QuestionPreviewPayload) => void
  /** A user-facing checkpoint (ADR-085): a quiet iteration's grounded result
   * statement after an eligible read — the FULL text in one frame (quiet
   * iterations stream nothing; the client paces it out under the typewriter
   * law). Each checkpoint is its OWN bubble segment: finalize the current
   * segment, type this into a new one, then the settled reply lands in a
   * fresh segment — never merged into one message. Persisted server-side as
   * an intent.type="checkpoint" row, so a failed turn's rollback drops the
   * bubbles and a refresh re-renders them from history. */
  onCheckpoint?: (text: string) => void
  /** One activity frame (ADR-087 §3 Phase 2): append-oriented milestones of
   * the agent's work — status flips arrive as new frames on the same
   * activity_id; the server's terminal sweep guarantees zero active
   * activities at the envelope (T16-B), the client sweeps defensively too. */
  onActivity?: (frame: ActivityFramePayload) => void
}

/** Answer endpoint payload (the answer doubles as resume). */
export interface AnswerTurnBody {
  kind: "option" | "freeform" | "bail" | "start"
  option_id?: string
  text?: string
  autonomy?: string
  intent?: unknown
}

/** The one SSE turn pump both surfaces share (2026-09-05 减法批 — the two
 * former copies' fetchEventSource scaffolding was byte-identical; only the
 * URL, the body and the terminal event names differ, and those stay
 * explicit parameters, never inference). Resolves with the terminal
 * envelope; rejects with StreamTurnError(server detail) on pre-stream
 * failures and mid-stream `.failed` frames, and with the abort error on
 * stop (chat). */

/** A turn failure carrying the server's raw `detail` — a string for plain
 * errors, the structured object for typed failures (credits.insufficient,
 * API.md §4). `message` keeps the human string form so generic callers
 * degrade exactly as before; typed callers read `detail` via
 * asCreditsInsufficient & co. */
export class StreamTurnError extends Error {
  detail: unknown
  /** Turn durability (交互完整性批 A): the user message committed server-
   * side before the turn died — the flow must KEEP the bubble (a refresh
   * re-renders it from the DB), never roll the user's own words back.
   * False for pre-persistence rejections (entry caps) and pre-stream HTTP
   * failures, where the old rollback stays correct. */
  persisted: boolean

  constructor(detail: unknown, fallback: string, persisted = false) {
    super(typeof detail === "string" && detail ? detail : fallback)
    this.name = "StreamTurnError"
    this.detail = detail
    this.persisted = persisted
  }
}

function streamTurn<T>(
  url: string,
  body: unknown,
  terminal: { completed: string; failed: string },
  {
    signal,
    onDelta,
    onThinking,
    onQuestionPreview,
    onCheckpoint,
    onActivity,
  }: {
    signal?: AbortSignal
    onDelta?: (text: string) => void
    onThinking?: (payload: ThinkingPayload) => void
    onQuestionPreview?: StreamChatOptions["onQuestionPreview"]
    onCheckpoint?: StreamChatOptions["onCheckpoint"]
    onActivity?: StreamChatOptions["onActivity"]
  },
): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = getToken()
    if (!token) {
      clearAuth()
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
      reject(new Error("unauthorized"))
      return
    }
    fetchEventSource(url, {
      method: "POST",
      ...(signal ? { signal } : {}),
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        // The UI locale rides the stream (2026-09-04 言语语言律): this
        // transport bypasses apiFetch, so its Accept-Language injection
        // never covered chat turns — the browser's own locale leaked in and
        // pinned runs/speech to zh under an English UI. The middleware pins
        // this into run.context.ui_language and the speech-language line.
        ...(i18n.language ? { "Accept-Language": i18n.language } : {}),
      },
      body: JSON.stringify(body),
      onopen: async (res) => {
        if (res.status === 401) {
          clearAuth()
          window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
          throw new Error("unauthorized")
        }
        if (!res.ok) {
          // Pre-stream failures (404 access, 422 recipe rejection, …) arrive
          // as a plain JSON error body — keep the toast semantics identical
          // to the JSON path. A structured detail (credits.insufficient)
          // rides the error object for typed handling downstream.
          const data = await res.json().catch(() => ({}))
          throw new StreamTurnError(
            (data as { detail?: unknown }).detail,
            `stream: ${res.status}`,
          )
        }
      },
      onmessage: (msg) => {
        // The dispatch is the extracted PURE router (chatStreamFrames.ts —
        // same event names, same JSON.parse-in-place failure semantics).
        const frame = routeStreamFrame(msg.event, msg.data, terminal)
        switch (frame.kind) {
          case "delta":
            onDelta?.(frame.text)
            break
          case "thinking":
            onThinking?.(frame.payload)
            break
          case "question_preview":
            onQuestionPreview?.(frame.payload)
            break
          case "checkpoint":
            onCheckpoint?.(frame.text)
            break
          case "activity":
            onActivity?.(frame.frame)
            break
          case "completed":
            resolve(frame.envelope as T)
            break
          case "failed":
            reject(
              new StreamTurnError(frame.detail, "Stream failed", frame.persisted),
            )
            break
          case "ignored":
            break
        }
        // heartbeat comment frames never reach onmessage.
      },
      onclose: () => {
        // Server closed the stream. The terminal frame has already settled
        // the promise by now; anything else is a broken stream.
        throw new Error("stream closed")
      },
      onerror: (err) => {
        // Never retry (see the file header).
        throw err
      },
    }).catch((err) => reject(err))
  })
}

/** One streamed answer turn (the answer endpoint's SSE mode, 2026-09-04
 * 验收批): the answer's continuation is an LLM turn (a slot answer resumes
 * the plan path), so an option click gets the same wire as a typed turn —
 * the endpoint Accept-negotiates exactly like POST /chat, and this wrapper
 * only names its terminal events. The ask preview rides along too
 * (2026-09-09 对称拍板): a follow-up ask previews its pill mid-stream,
 * same as the chat turn's first ask. */
export function streamAnswer<T>(
  messageId: string,
  body: AnswerTurnBody,
  handlers: {
    onDelta?: (text: string) => void
    onThinking?: (payload: ThinkingPayload) => void
    onQuestionPreview?: StreamChatOptions["onQuestionPreview"]
    onActivity?: StreamChatOptions["onActivity"]
  },
): Promise<T> {
  return streamTurn(
    `${API_URL}/api/v1/chat/messages/${messageId}/answer`,
    body,
    { completed: "answer.completed", failed: "answer.failed" },
    handlers,
  )
}

/** One streamed chat turn. Resolves with the ChatResponse envelope (the
 * caller supplies its shape — the two surfaces type it differently); rejects
 * with StreamTurnError(server detail) on HTTP failures and mid-stream
 * turn.failed, and with the abort error on stop (callers check
 * `e.name === "AbortError"`). */
export function streamChat<T>(
  body: ChatTurnBody,
  { signal, onDelta, onThinking, onQuestionPreview, onCheckpoint, onActivity }: StreamChatOptions,
): Promise<T> {
  return streamTurn(
    `${API_URL}/api/v1/chat`,
    body,
    { completed: "turn.completed", failed: "turn.failed" },
    { signal, onDelta, onThinking, onQuestionPreview, onCheckpoint, onActivity },
  )
}
