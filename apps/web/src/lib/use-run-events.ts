/** SSE run events (CHAT_ARCH §8): a pushed read of DB state.
 *
 * Subscribes to `GET /api/v1/runs/{id}/events` while a run is active. The
 * server sends a full `run.snapshot` on connect (idempotent reconnect), then
 * `step.updated` / `run.updated` diffs, and closes on terminal state. Uses
 * fetch-event-source because native EventSource cannot send the
 * Authorization header.
 */

import { useEffect, useRef, useState } from "react"
import { fetchEventSource } from "@microsoft/fetch-event-source"

import { API_URL, UNAUTHORIZED_EVENT } from "@/lib/api"
import { clearAuth, getToken } from "@/lib/auth"
import type { WorkflowStep } from "@/lib/types"

export interface RunEventsState {
  /** Steps from the latest snapshot/diffs (empty until the first snapshot). */
  steps: WorkflowStep[]
  status: string | null
  progress: number
  /** The run's creation time — the overlay's chronological anchor for
   * interleaving chat messages with the run block (#5). */
  createdAt: string | null
  /** True once the stream carried a terminal run state. */
  terminal: boolean
}

const INITIAL: RunEventsState = {
  steps: [],
  status: null,
  progress: 0,
  createdAt: null,
  terminal: false,
}

export function useRunEvents(
  runId: string | null,
  onTerminal?: () => void,
): RunEventsState {
  const [state, setState] = useState<RunEventsState>(INITIAL)
  const onTerminalRef = useRef(onTerminal)
  onTerminalRef.current = onTerminal

  useEffect(() => {
    if (!runId) {
      setState(INITIAL)
      return
    }
    const token = getToken()
    if (!token) return

    const ctrl = new AbortController()
    let terminalFired = false
    setState(INITIAL)

    const fireTerminal = () => {
      if (terminalFired) return
      terminalFired = true
      onTerminalRef.current?.()
    }

    fetchEventSource(`${API_URL}/api/v1/runs/${runId}/events`, {
      signal: ctrl.signal,
      headers: { Authorization: `Bearer ${token}` },
      onopen: async (res) => {
        if (res.status === 401) {
          clearAuth()
          window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
          throw new Error("unauthorized")
        }
        if (!res.ok) throw new Error(`run events: ${res.status}`)
      },
      onmessage: (msg) => {
        if (msg.event === "run.snapshot") {
          const data = JSON.parse(msg.data) as {
            run: {
              status: string
              progress: number
              created_at?: string | null
            }
            steps: WorkflowStep[]
          }
          // Historical runs arrive terminal in the snapshot itself — the
          // stream closes without a run.updated, so detect it here (chat
          // RunCard history rehydration depends on this).
          const terminal =
            data.run.status === "completed" || data.run.status === "failed"
          setState({
            steps: data.steps,
            status: data.run.status,
            progress: data.run.progress,
            createdAt: data.run.created_at ?? null,
            terminal,
          })
          if (terminal) fireTerminal()
        } else if (msg.event === "step.updated") {
          const step = JSON.parse(msg.data) as WorkflowStep
          setState((prev) => ({
            ...prev,
            steps: prev.steps.some((s) => s.id === step.id)
              ? prev.steps.map((s) => (s.id === step.id ? step : s))
              : [...prev.steps, step].sort((a, b) => a.seq - b.seq),
          }))
        } else if (msg.event === "run.updated") {
          const run = JSON.parse(msg.data) as {
            status: string
            progress: number
          }
          const terminal = run.status === "completed" || run.status === "failed"
          setState((prev) => ({
            ...prev,
            status: run.status,
            progress: run.progress,
            terminal: prev.terminal || terminal,
          }))
          if (terminal) fireTerminal()
        }
      },
      onclose: () => {
        // Server closed the stream (terminal state). Never retry.
        throw new Error("stream closed")
      },
      onerror: (err) => {
        // Stop auto-retry on auth/terminal; network errors retry by default.
        if (err instanceof Error && err.message === "unauthorized") throw err
      },
    }).catch(() => {
      // Aborted (unsubscribe / new run) or terminal close — both expected.
    })

    return () => ctrl.abort()
  }, [runId])

  return state
}
