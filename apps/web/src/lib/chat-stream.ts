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

export interface ChatTurnBody {
  project_id: string
  message: string
  mentions?: { type: string; id: string; label: string }[]
  /** The canvas's focused product (ADR-041 D8 焦点注入): rides the turn as
   * one context line AND persists on the user message row — the rebuilt
   * history renders the gray focus prefix row after a refresh. */
  focus_output?: { id: string; label: string }
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
  /** Model-activity frame: fires with `{}` as a pure keepalive (reasoning
   * fragments / non-prose JSON chunks — drive the indicator, never render),
   * or with `{phase: "creating_run"}` at a REAL phase switch — the client
   * labels its thinking row from the phase and leaves it untouched on bare
   * keepalives. */
  onThinking?: (payload: { phase?: string }) => void
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
 * envelope; rejects with Error(server detail) on pre-stream failures and
 * mid-stream `.failed` frames, and with the abort error on stop (chat). */
function streamTurn<T>(
  url: string,
  body: unknown,
  terminal: { completed: string; failed: string },
  {
    signal,
    onDelta,
    onThinking,
  }: {
    signal?: AbortSignal
    onDelta?: (text: string) => void
    onThinking?: (payload: { phase?: string }) => void
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
          // to the JSON path.
          const data = await res.json().catch(() => ({}))
          throw new Error(
            (data as { detail?: string }).detail || `stream: ${res.status}`,
          )
        }
      },
      onmessage: (msg) => {
        if (msg.event === "assistant.delta") {
          const data = JSON.parse(msg.data) as { text: string }
          onDelta?.(data.text)
        } else if (msg.event === "assistant.thinking") {
          onThinking?.(JSON.parse(msg.data) as { phase?: string })
        } else if (msg.event === terminal.completed) {
          resolve(JSON.parse(msg.data))
        } else if (msg.event === terminal.failed) {
          const data = JSON.parse(msg.data) as { detail?: string }
          reject(new Error(data.detail || "Stream failed"))
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
 * the book path), so an option click gets the same wire as a typed turn —
 * the endpoint Accept-negotiates exactly like POST /chat, and this wrapper
 * only names its terminal events. */
export function streamAnswer<T>(
  messageId: string,
  body: AnswerTurnBody,
  handlers: {
    onDelta?: (text: string) => void
    onThinking?: (payload: { phase?: string }) => void
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
 * with Error(server detail) on HTTP failures and mid-stream turn.failed, and
 * with the abort error on stop (callers check `e.name === "AbortError"`). */
export function streamChat<T>(
  body: ChatTurnBody,
  { signal, onDelta, onThinking }: StreamChatOptions,
): Promise<T> {
  return streamTurn(
    `${API_URL}/api/v1/chat`,
    body,
    { completed: "turn.completed", failed: "turn.failed" },
    { signal, onDelta, onThinking },
  )
}
