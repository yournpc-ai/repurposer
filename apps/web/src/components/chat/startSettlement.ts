/** sendChat's start-envelope prose gate.
 *
 * A start_run whose own speech is empty returns the already-answered plan
 * row; its echo must not be typed a second time. An auto-started plan can
 * instead be born AND answered in the same turn, before its echo was ever
 * shown. Row identity alone cannot distinguish those cases — only the
 * client-visible message flow can.
 */

import type { OverlayMessage } from "./historyReplay"

export function shouldPaceStartEnvelopeProse(opts: {
  content: string
  assistantMessageId: string
  answeredQuestionId?: string | null
  messages: OverlayMessage[]
}): boolean {
  const { content, assistantMessageId, answeredQuestionId, messages } = opts
  if (!content.trim()) return false
  // A distinct assistant row is the start turn's own speech, never the old
  // plan echo — it must pace even when its words happen to repeat an echo.
  if (assistantMessageId !== answeredQuestionId) return true
  return !messages.some(
    (m) =>
      m.role === "assistant" && m.meta !== "error" && m.content === content,
  )
}
