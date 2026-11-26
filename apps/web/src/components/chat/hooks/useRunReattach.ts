/** Re-attachable RunEventBus subscription hook for seamless tab-switch / refresh sync. */
import { useEffect, useRef } from "react"

import { streamConversationEvents } from "@/lib/chat-stream"
import type { ActivityRowFramePayload, RowAppendPayload } from "@/lib/chatStreamFrames"
import type { ActivityFramePayload, StepPlanItem } from "../timeline/types"

export interface UseRunReattachOptions {
  conversationId: string | null
  enabled: boolean
  getAfterSeq: () => number
  onSynced?: (payload: {
    active: boolean
    runId: string | null
    turnId: string | null
    liveFocus: string | null
    steps: StepPlanItem[] | null
  }) => void
  onActivity?: (frame: ActivityFramePayload) => void
  onRowAppend?: (row: RowAppendPayload) => void
  onRowUpdate?: (id: string, frame: ActivityRowFramePayload) => void
  onTerminal?: (kind: "completed" | "failed") => void
}

export function useRunReattach({
  conversationId,
  enabled,
  getAfterSeq,
  onSynced,
  onActivity,
  onRowAppend,
  onRowUpdate,
  onTerminal,
}: UseRunReattachOptions) {
  const callbacksRef = useRef({
    getAfterSeq,
    onSynced,
    onActivity,
    onRowAppend,
    onRowUpdate,
    onTerminal,
  })
  callbacksRef.current = {
    getAfterSeq,
    onSynced,
    onActivity,
    onRowAppend,
    onRowUpdate,
    onTerminal,
  }

  useEffect(() => {
    if (!enabled || !conversationId) return
    const controller = new AbortController()
    const afterSeq = callbacksRef.current.getAfterSeq()
    void streamConversationEvents(conversationId, afterSeq, {
      signal: controller.signal,
      onSynced: (payload) => callbacksRef.current.onSynced?.(payload),
      onActivity: (frame) => callbacksRef.current.onActivity?.(frame),
      onRowAppend: (row) => callbacksRef.current.onRowAppend?.(row),
      onRowUpdate: (id, frame) => callbacksRef.current.onRowUpdate?.(id, frame),
      onTerminal: (kind) => callbacksRef.current.onTerminal?.(kind),
    }).catch(() => {
      // Best-effort re-attach; history polling remains fallback.
    })
    return () => {
      controller.abort()
    }
  }, [conversationId, enabled])
}
