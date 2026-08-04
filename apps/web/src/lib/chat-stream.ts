/** Chat turn SSE client (CHAT_ARCH §8): the streaming transport for POST /chat.
 *
 * Same endpoint, same payload as the plain apiFetch call — the difference is
 * the `Accept: text/event-stream` header, which flips the server into its
 * streaming mode: `assistant.delta` prose previews while the verdict JSON
 * generates, then one terminal `turn.completed` carrying the exact
 * ChatResponse payload (the envelope always wins — deltas are a preview
 * channel, never the source of truth) or `turn.failed` (a mid-stream
 * failure the JSON path would surface as an HTTP error).
 *
 * Uses fetch-event-source because native EventSource is GET-only and cannot
 * send the Authorization header. Auto-reconnect is DISABLED: a retried POST
 * would persist the user message a second time (the server has no dedup by
 * design), so every close/error path terminates the promise.
 */

import { fetchEventSource } from "@microsoft/fetch-event-source"

import { API_URL, UNAUTHORIZED_EVENT } from "@/lib/api"
import { clearAuth, getToken } from "@/lib/auth"

export interface ChatTurnBody {
  project_id: string
  asset_id?: string
  asset_type?: "clip" | "derivative"
  message: string
  mentions?: { type: string; id: string; label: string }[]
  brand_template_id?: string
  prior_intent?: unknown
  autonomy?: string
}

export interface StreamChatOptions {
  signal: AbortSignal
  /** Decoded prose fragment, in order — concatenate to render the preview. */
  onDelta?: (text: string) => void
}

/** One streamed chat turn. Resolves with the ChatResponse envelope (the
 * caller supplies its shape — the two surfaces type it differently); rejects
 * with Error(server detail) on HTTP failures and mid-stream turn.failed, and
 * with the abort error on stop (callers check `e.name === "AbortError"`). */
export function streamChat<T>(
  body: ChatTurnBody,
  { signal, onDelta }: StreamChatOptions,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = getToken()
    if (!token) {
      clearAuth()
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
      reject(new Error("unauthorized"))
      return
    }
    fetchEventSource(`${API_URL}/api/v1/chat`, {
      method: "POST",
      signal,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
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
            (data as { detail?: string }).detail || `chat: ${res.status}`,
          )
        }
      },
      onmessage: (msg) => {
        if (msg.event === "assistant.delta") {
          const data = JSON.parse(msg.data) as { text: string }
          onDelta?.(data.text)
        } else if (msg.event === "turn.completed") {
          resolve(JSON.parse(msg.data))
        } else if (msg.event === "turn.failed") {
          const data = JSON.parse(msg.data) as { detail?: string }
          reject(new Error(data.detail || "Chat failed"))
        }
        // heartbeat comment frames never reach onmessage.
      },
      onclose: () => {
        // Server closed the stream. turn.completed/turn.failed have already
        // settled the promise by now; anything else is a broken stream.
        throw new Error("stream closed")
      },
      onerror: (err) => {
        // Never retry: a retried POST would duplicate the user message.
        throw err
      },
    }).catch((err) => reject(err))
  })
}
