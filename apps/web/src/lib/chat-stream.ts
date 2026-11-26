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
 * send the Authorization header. Reconnect-driven re-POST is DISABLED on both
 * turns: a retried POST would persist the user message a second time (chat) or
 * double-settle the question (answer — the row-lock turns the retry into a
 * 409, but the optimistic UI must not flicker through a phantom retry), so
 * every close/error path terminates the promise, and `openWhenHidden: true`
 * keeps the tab-hide/visible cycle from aborting the in-flight POST and
 * re-issuing it (fetch-event-source's default re-runs `create()` on
 * visibility — the server has no dedup, so each return-to-tab persisted a
 * duplicate user row while the aborted turn was stamped failed).
 */

import { fetchEventSource } from "@microsoft/fetch-event-source"

import { API_URL, UNAUTHORIZED_EVENT, WALLET_REFRESH_EVENT } from "@/lib/api"
import { clearAuth, getToken } from "@/lib/auth"
import { notifyConversationsChanged } from "@/lib/workbench"
import i18n from "@/lib/i18n"
import { routeStreamFrame } from "@/lib/chatStreamFrames"
import { normalizeStreamError } from "@/lib/streamTransport"
import { sseProbe } from "@/lib/sse-probe" // TEMPORARY forensics — delete with the probe
import type { CandidateEventPayload } from "@/lib/chatStreamFrames"
import type { ChatAttachment } from "@/lib/types"
import type { ChatMention } from "@/lib/mentions"

// The frame vocabulary's single seat is chatStreamFrames.ts (Phase 3 Batch
// A test seam) — re-exported here so existing import sites stay put.
export type {
  ThinkingPayload,
} from "@/lib/chatStreamFrames"
export type { ActivityFramePayload } from "@/components/chat/timeline/types"
import type {
  ActivityFramePayload,
  BriefAnswerItem,
  FailureCheckpoint,
  QuestionMessage,
  StepPlanItem,
} from "@/components/chat/timeline/types"
import type { SkillReference } from "@/lib/skills"
import type {
  ActivityRowFramePayload,
  RowAppendPayload,
  ThinkingPayload,
} from "@/lib/chatStreamFrames"

export interface ChatTurnBody {
  first_message?: boolean
  project_id: string
  conversation_id?: string
  message: string
  mentions?: ChatMention[]
  skill?: SkillReference
  /** Files staged in the input group and sent with this turn (the server
   * persists them on the user message row — refresh re-renders the chips). */
  attachments?: ChatAttachment[]
  /** The composer's persona choice, riding the first message of a fresh
   * project (ADR-038 — the single identity payload; the skin follows the
   * persona). */
  persona_id?: string
  /** The Studio Thread always sends false. */
}

export interface StreamChatOptions {
  signal: AbortSignal
  /** Durable opening user id (and segment runId), emitted before Agent execution begins. */
  onTurnStarted?: (turnId: string, runId?: string | null) => void
  /** Two-phase commit: emitted immediately after a user decision commits to DB. */
  onDecisionCommitted?: (payload: {
    runId: string | null
    turnId: string | null
    answeredQuestion: QuestionMessage
  }) => void
  /** Decoded prose fragment, in order — concatenate to render the preview. */
  onDelta?: (text: string, messageId: string | null) => void
  onThinking?: (payload: ThinkingPayload) => void
  onInterimProse?: (
    text: string,
    at: string | undefined,
    turnId: string | null,
    messageId: string,
    seq: number | null,
    runId?: string | null,
    displayRole?: "stage_note" | "rail_note",
  ) => void
  onActivity?: (frame: ActivityFramePayload) => void
  onCandidates?: (event: CandidateEventPayload) => void
  onRowAppend?: (row: RowAppendPayload) => void
  onRowUpdate?: (id: string, frame: ActivityRowFramePayload) => void
}

/** Answer endpoint payload (the answer doubles as resume). */
export interface AnswerTurnBody {
  kind: "option" | "freeform" | "bail" | "start" | "group"
  option_id?: string
  text?: string
  group_digest?: string
  answers?: BriefAnswerItem[]
  intent?: unknown
}

/** The one SSE turn pump both surfaces share (2026-09-05 减法批 — the two
 * former copies' fetchEventSource scaffolding was byte-identical; only the
 * URL, the body and the terminal event names differ, and those stay
 * explicit parameters, never inference). Resolves with the terminal
 * envelope; rejects with StreamTurnError(server detail) on pre-stream
 * failures and mid-stream `.failed` frames, StreamTransportError on a
 * post-open transport failure, and the abort error on stop (chat). */

/** A turn failure carrying the server's raw `detail` — a string for plain
 * errors, the structured object for typed failures (credits.insufficient,
 * API.md §4). `message` keeps the human string form so generic callers
 * degrade exactly as before; typed callers read `detail` via
 * asCreditsInsufficient & co. */
export class StreamTurnError extends Error {
  detail: unknown
  persisted: boolean
  turnId: string | null
  runId: string | null
  decisionCommitted: boolean
  checkpoint?: FailureCheckpoint

  constructor(
    detail: unknown,
    fallback: string,
    persisted = false,
    turnId: string | null = null,
    readonly messageId?: string,
    opts?: {
      runId?: string | null
      decisionCommitted?: boolean
      checkpoint?: FailureCheckpoint
    },
  ) {
    super(typeof detail === "string" && detail ? detail : fallback)
    this.name = "StreamTurnError"
    this.detail = detail
    this.persisted = persisted
    this.turnId = turnId
    this.runId = opts?.runId ?? null
    this.decisionCommitted = Boolean(opts?.decisionCommitted)
    this.checkpoint = opts?.checkpoint
  }
}

/** The answer endpoint's settled-question codes (2026-09-28 — before them
 * the raw "Question already answered" string leaked into the global toast
 * and the dead pill re-docked for another click, the「点击回答仍然报错」
 * loop): superseded = a newer question took the floor mid-click;
 * already_answered = the plain double gesture. Both are quiet settles on
 * the client, never error toasts. */
export function questionSettledCode(
  detail: unknown,
): "question.superseded" | "question.already_answered" | null {
  if (detail !== null && typeof detail === "object") {
    const code = (detail as { code?: unknown }).code
    if (code === "question.superseded" || code === "question.already_answered") {
      return code
    }
  }
  return null
}

function streamTurn<T>(
  url: string,
  body: unknown,
  terminal: { completed: string; failed: string },
  {
    signal,
    onTurnStarted,
    onDecisionCommitted,
    onDelta,
    onThinking,
    onInterimProse,
    onActivity,
    onCandidates,
    onRowAppend,
    onRowUpdate,
  }: {
    signal?: AbortSignal
    onTurnStarted?: (turnId: string, runId?: string | null) => void
    onDecisionCommitted?: StreamChatOptions["onDecisionCommitted"]
    onDelta?: (text: string, messageId: string | null) => void
    onThinking?: (payload: ThinkingPayload) => void
    onInterimProse?: StreamChatOptions["onInterimProse"]
    onActivity?: StreamChatOptions["onActivity"]
    onCandidates?: StreamChatOptions["onCandidates"]
    onRowAppend?: StreamChatOptions["onRowAppend"]
    onRowUpdate?: StreamChatOptions["onRowUpdate"]
  },
): Promise<T> {
  let streamOpened = false
  let processingFrame = false
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
      // A tab hide/visible cycle must not abort + re-POST the turn (see the
      // file header) — the stream stays open while the tab is hidden.
      openWhenHidden: true,
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
        sseProbe("stream.open", { url, status: res.status })
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
        streamOpened = true
      },
      onmessage: (msg) => {
        // A synchronous dispatch/handler throw leaves this true until onerror,
        // so its TypeError is never mistaken for a body-reader disconnect.
        processingFrame = true
        // The dispatch is the extracted PURE router (chatStreamFrames.ts —
        // same event names, same JSON.parse-in-place failure semantics).
        const frame = routeStreamFrame(msg.event, msg.data, terminal)
        sseProbe("stream.frame", {
          kind: frame.kind,
          ...(frame.kind === "delta" ? { chars: frame.text.length } : {}),
          ...(frame.kind === "thinking"
            ? { bare: !("phase" in frame.payload) }
            : {}),
        })
        if (frame.kind === "completed" || frame.kind === "failed") {
          window.dispatchEvent(new Event(WALLET_REFRESH_EVENT))
        }
        switch (frame.kind) {
          case "turn_started":
            onTurnStarted?.(frame.turnId, frame.runId ?? null)
            break
          case "decision_committed":
            onDecisionCommitted?.({
              runId: frame.runId,
              turnId: frame.turnId,
              answeredQuestion: frame.answeredQuestion,
            })
            break
          case "delta":
            onDelta?.(frame.text, frame.messageId)
            break
          case "thinking":
            onThinking?.(frame.payload)
            break
          case "interim_prose":
            onInterimProse?.(
              frame.text,
              frame.at,
              frame.turnId,
              frame.messageId,
              frame.seq,
              frame.runId ?? null,
              frame.displayRole,
            )
            break
          case "activity":
            onActivity?.(frame.frame)
            break
          case "row_append":
            onRowAppend?.(frame.row)
            break
          case "row_update":
            onRowUpdate?.(frame.id, frame.frame)
            break
          case "candidates":
            onCandidates?.(frame.event)
            break
          case "title_updated":
            notifyConversationsChanged(frame.projectId)
            break
          case "completed":
            resolve(frame.envelope as T)
            break
          case "failed":
            reject(
              new StreamTurnError(
                frame.detail,
                "Stream failed",
                frame.persisted,
                frame.turnId,
                frame.messageId,
                {
                  runId: frame.runId ?? null,
                  decisionCommitted: frame.decisionCommitted,
                  checkpoint: frame.checkpoint,
                },
              ),
            )
            break
          case "run_synced":
          case "ignored":
            break
        }
        // Server liveness keepalives arrive as bare-{} assistant.thinking
        // frames — routed above into onThinking, where the handler no-ops
        // them (liveness only; the frame cadence is the client watchdog's
        // dead-pipe signal).
        processingFrame = false
      },
      onclose: () => {
        sseProbe("stream.close", { url })
        // Server closed the stream. The terminal frame has already settled
        // the promise by now; anything else is a broken stream.
        throw new Error("stream closed")
      },
      onerror: (err) => {
        const normalized = normalizeStreamError(err, streamOpened, processingFrame)
        sseProbe("stream.error", {
          url,
          message: err instanceof Error ? err.message : String(err),
        })
        // Never retry (see the file header). A post-open transport failure is
        // typed so the caller can reconcile the archive without re-POSTing.
        throw normalized
      },
    }).then(() => {
      // fetch-event-source resolves (never rejects) when OUR input signal
      // aborts. Convert that transport completion into the AbortError the
      // turn owner awaits; otherwise sendChat's catch/finally never runs and
      // Stop leaves the composer busy forever.
      if (signal?.aborted) {
        reject(new DOMException("The operation was aborted.", "AbortError"))
      }
    }).catch((err) => {
      sseProbe("stream.reject", {
        url,
        name: err instanceof Error ? err.name : "?",
        message: err instanceof Error ? err.message : String(err),
      })
      reject(err)
    })
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
    signal?: AbortSignal
    onDecisionCommitted?: StreamChatOptions["onDecisionCommitted"]
    onDelta?: (text: string, messageId: string | null) => void
    onThinking?: (payload: ThinkingPayload) => void
    onInterimProse?: StreamChatOptions["onInterimProse"]
    onActivity?: StreamChatOptions["onActivity"]
    onCandidates?: StreamChatOptions["onCandidates"]
    onRowAppend?: StreamChatOptions["onRowAppend"]
    onRowUpdate?: StreamChatOptions["onRowUpdate"]
  },
): Promise<T> {
  return streamTurn(
    `${API_URL}/api/v1/chat/messages/${messageId}/answer`,
    body,
    { completed: "answer.completed", failed: "answer.failed" },
    handlers,
  )
}

/** Resume a conversation from its latest failure checkpoint via SSE. */
export function streamResume<T>(
  conversationId: string,
  handlers: StreamChatOptions,
): Promise<T> {
  return streamTurn(
    `${API_URL}/api/v1/chat/conversations/${conversationId}/resume`,
    {},
    { completed: "turn.completed", failed: "turn.failed" },
    handlers,
  )
}

/** Re-attach to an in-flight conversation run after tab switch or reconnect. */
export function streamConversationEvents(
  conversationId: string,
  afterSeq: number,
  handlers: {
    signal: AbortSignal
    onSynced?: (payload: {
      active: boolean
      runId: string | null
      turnId: string | null
      liveFocus: string | null
      steps: StepPlanItem[] | null
    }) => void
    onDelta?: (text: string, messageId: string | null) => void
    onThinking?: (payload: ThinkingPayload) => void
    onInterimProse?: StreamChatOptions["onInterimProse"]
    onActivity?: StreamChatOptions["onActivity"]
    onCandidates?: StreamChatOptions["onCandidates"]
    onRowAppend?: StreamChatOptions["onRowAppend"]
    onRowUpdate?: StreamChatOptions["onRowUpdate"]
    onTerminal?: (kind: "completed" | "failed") => void
  },
): Promise<void> {
  return new Promise((resolve, reject) => {
    const token = getToken()
    if (!token) {
      resolve()
      return
    }
    fetchEventSource(
      `${API_URL}/api/v1/chat/conversations/${conversationId}/events?after_seq=${Math.max(0, afterSeq)}`,
      {
        method: "GET",
        openWhenHidden: true,
        signal: handlers.signal,
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "text/event-stream",
          ...(i18n.language ? { "Accept-Language": i18n.language } : {}),
        },
        onopen: async (res) => {
          if (!res.ok) throw new Error(`events: ${res.status}`)
        },
        onmessage: (msg) => {
          const isAnswerTerminal =
            msg.event === "answer.completed" || msg.event === "answer.failed"
          const frame = routeStreamFrame(
            msg.event,
            msg.data,
            isAnswerTerminal
              ? { completed: "answer.completed", failed: "answer.failed" }
              : { completed: "turn.completed", failed: "turn.failed" },
          )
          switch (frame.kind) {
            case "run_synced":
              handlers.onSynced?.({
                active: frame.active,
                runId: frame.runId,
                turnId: frame.turnId,
                liveFocus: frame.liveFocus,
                steps: frame.steps,
              })
              if (!frame.active) resolve()
              break
            case "delta":
              handlers.onDelta?.(frame.text, frame.messageId)
              break
            case "thinking":
              handlers.onThinking?.(frame.payload)
              break
            case "interim_prose":
              handlers.onInterimProse?.(
                frame.text,
                frame.at,
                frame.turnId,
                frame.messageId,
                frame.seq,
                frame.runId ?? null,
              )
              break
            case "activity":
              handlers.onActivity?.(frame.frame)
              break
            case "row_append":
              handlers.onRowAppend?.(frame.row)
              break
            case "row_update":
              handlers.onRowUpdate?.(frame.id, frame.frame)
              break
            case "candidates":
              handlers.onCandidates?.(frame.event)
              break
            case "title_updated":
              notifyConversationsChanged(frame.projectId)
              break
            case "completed":
              window.dispatchEvent(new Event(WALLET_REFRESH_EVENT))
              handlers.onTerminal?.("completed")
              resolve()
              break
            case "failed":
              window.dispatchEvent(new Event(WALLET_REFRESH_EVENT))
              handlers.onTerminal?.("failed")
              resolve()
              break
            default:
              break
          }
        },
        onclose: () => {
          resolve()
        },
        onerror: (err) => {
          throw err
        },
      },
    )
      .then(() => resolve())
      .catch((err) => {
        if (handlers.signal.aborted) resolve()
        else reject(err)
      })
  })
}

/** One streamed chat turn. Resolves with the ChatResponse envelope (the
 * caller supplies its shape — the two surfaces type it differently); rejects
 * with StreamTurnError(server detail) on HTTP failures and mid-stream
 * turn.failed, and with the abort error on stop (callers check
 * `e.name === "AbortError"`). */
export function streamChat<T>(
  body: ChatTurnBody,
  { signal, onTurnStarted, onDelta, onThinking, onInterimProse, onActivity, onCandidates, onRowAppend, onRowUpdate }: StreamChatOptions,
): Promise<T> {
  return streamTurn(
    `${API_URL}/api/v1/chat`,
    body,
    { completed: "turn.completed", failed: "turn.failed" },
    { signal, onTurnStarted, onDelta, onThinking, onInterimProse, onActivity, onCandidates, onRowAppend, onRowUpdate },
  )
}
