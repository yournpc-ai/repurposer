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

export type RunTerminalSource = "snapshot" | "update" | null

export interface RunEventsState {
  /** Steps from the latest snapshot/diffs (empty until the first snapshot). */
  steps: WorkflowStep[]
  status: string | null
  progress: number
  /** The run's creation time — the overlay's chronological anchor for
   * interleaving chat messages with the run block (#5). */
  createdAt: string | null
  /** True once this attachment attempt carried a terminal run state. */
  terminal: boolean
  /** Snapshot terminal is historical hydration; an update terminal is live. */
  terminalSource: RunTerminalSource
  /** Existing server recovery identity used by trigger refs. */
  uploadRetryCount: number
  /** Client attachment identity; never part of the Run's domain identity. */
  subscriptionRunId: string | null
  subscriptionAttempt: number
}

function initialState(runId: string | null, attempt: number): RunEventsState {
  return {
    steps: [],
    status: runId ? "pending" : null,
    progress: 0,
    createdAt: null,
    terminal: false,
    terminalSource: null,
    uploadRetryCount: 0,
    subscriptionRunId: runId,
    subscriptionAttempt: attempt,
  }
}

/** A same-run recovery owns a new subscription generation. Cleanup alone is
 * not enough: an already-enqueued old callback must also fail this guard. */
export function createRunEventGeneration() {
  let current = 0
  return {
    begin(): number {
      current += 1
      return current
    },
    owns(generation: number): boolean {
      return generation === current
    },
    invalidate(generation: number): void {
      if (generation === current) current += 1
    },
  }
}

/** A new attachment reads its own initial active state, never the previous
 * attempt's terminal latch while the new effect is being installed. */
export function runEventsForAttachment(
  state: RunEventsState,
  runId: string | null,
  attempt: number,
): RunEventsState {
  return state.subscriptionRunId === runId && state.subscriptionAttempt === attempt
    ? state
    : initialState(runId, attempt)
}

export function useRunEvents(
  runId: string | null,
  onTerminal?: () => void,
  attempt = 0,
): RunEventsState {
  const [state, setState] = useState<RunEventsState>(() => initialState(runId, attempt))
  const onTerminalRef = useRef(onTerminal)
  onTerminalRef.current = onTerminal
  const generationRef = useRef(createRunEventGeneration())

  useEffect(() => {
    const generation = generationRef.current.begin()
    let disposed = false
    const owns = () => !disposed && generationRef.current.owns(generation)
    if (!runId) {
      setState(initialState(null, attempt))
      return () => {
        disposed = true
        generationRef.current.invalidate(generation)
      }
    }
    const token = getToken()
    if (!token) {
      setState(initialState(runId, attempt))
      return () => {
        disposed = true
        generationRef.current.invalidate(generation)
      }
    }

    const ctrl = new AbortController()
    let terminalFired = false
    setState(initialState(runId, attempt))

    const fireTerminal = () => {
      if (!owns() || terminalFired) return
      terminalFired = true
      onTerminalRef.current?.()
    }

    fetchEventSource(`${API_URL}/api/v1/runs/${runId}/events`, {
      signal: ctrl.signal,
      headers: { Authorization: `Bearer ${token}` },
      onopen: async (res) => {
        if (!owns()) return
        if (res.status === 401) {
          clearAuth()
          window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
          throw new Error("unauthorized")
        }
        if (!res.ok) throw new Error(`run events: ${res.status}`)
      },
      onmessage: (msg) => {
        if (!owns()) return
        if (msg.event === "run.snapshot") {
          const data = JSON.parse(msg.data) as {
            run: {
              status: string
              progress: number
              created_at?: string | null
              upload_retry_count?: unknown
            }
            steps: WorkflowStep[]
          }
          // Historical runs arrive terminal in the snapshot itself — the
          // stream closes without a run.updated, so detect it here.
          const terminal = ["completed", "failed", "cancelled"].includes(data.run.status)
          const retryCount = data.run.upload_retry_count
          setState((prev) => owns() ? {
            steps: data.steps,
            status: data.run.status,
            progress: data.run.progress,
            createdAt: data.run.created_at ?? null,
            terminal,
            terminalSource: terminal ? "snapshot" : null,
            uploadRetryCount:
              typeof retryCount === "number" && Number.isFinite(retryCount)
                ? Math.max(0, Math.floor(retryCount))
                : 0,
            subscriptionRunId: runId,
            subscriptionAttempt: attempt,
          } : prev)
          if (terminal) fireTerminal()
        } else if (msg.event === "step.updated") {
          const step = JSON.parse(msg.data) as WorkflowStep
          setState((prev) => owns() ? {
            ...prev,
            steps: prev.steps.some((s) => s.id === step.id)
              ? prev.steps.map((s) => (s.id === step.id ? step : s))
              : [...prev.steps, step].sort((a, b) => a.seq - b.seq),
          } : prev)
        } else if (msg.event === "run.updated") {
          const run = JSON.parse(msg.data) as {
            status: string
            progress: number
            upload_retry_count?: unknown
          }
          const terminal = ["completed", "failed", "cancelled"].includes(run.status)
          const retryCount = run.upload_retry_count
          setState((prev) => owns() ? {
            ...prev,
            status: run.status,
            progress: run.progress,
            terminal: prev.terminal || terminal,
            terminalSource: terminal ? "update" : prev.terminalSource,
            uploadRetryCount:
              typeof retryCount === "number" && Number.isFinite(retryCount)
                ? Math.max(0, Math.floor(retryCount))
                : prev.uploadRetryCount,
          } : prev)
          if (terminal) fireTerminal()
        }
      },
      onclose: () => {
        // Normal close disposes without reconnecting. A stale close is equally
        // inert; the new attempt owns all visible state and terminal callbacks.
      },
      onerror: (err) => {
        // A stale attempt must never schedule another reconnect. Current
        // network errors retain the library's existing bounded-by-lifecycle
        // retry behavior; auth errors stop immediately.
        if (!owns()) throw err
        if (err instanceof Error && err.message === "unauthorized") throw err
      },
    }).catch(() => {
      // Aborted (unsubscribe / new attempt) or terminal close — both expected.
    })

    return () => {
      disposed = true
      generationRef.current.invalidate(generation)
      ctrl.abort()
    }
  }, [runId, attempt])

  // A new same-run attachment must not render the previous attempt's latched
  // terminal for the one render before its effect resets the subscription.
  return runEventsForAttachment(state, runId, attempt)
}
