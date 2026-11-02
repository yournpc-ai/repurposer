import type { OverlayMessage } from "./types"

export interface VisibleProseFrontier {
  message_id: string
  visible_chars: number
}

export interface ChatTurnVisibleFrontier {
  prose: VisibleProseFrontier[]
  activity_ids: string[]
  structure_ids: string[]
}

/** The only client Stop evidence: text actually released by the typewriter,
 * visible Activity rows, and structure ids registered by open renderers.
 * Message payload existence is never a visibility signal. */
export function visibleFrontierForTurn(
  messages: readonly OverlayMessage[],
  turnId: string,
  visibleStructureIds: ReadonlySet<string> = new Set(),
): ChatTurnVisibleFrontier {
  const frontier: ChatTurnVisibleFrontier = {
    prose: [],
    activity_ids: [],
    structure_ids: [],
  }
  for (const message of messages) {
    if (message.role !== "assistant" || message.turnId !== turnId) continue
    const serverId = message.serverMessageId
    if (!serverId) continue
    if (message.clientVisibleAtMs != null && message.content.trim()) {
      frontier.prose.push({
        message_id: serverId,
        // Protocol unit = Unicode code points, matching Python's text slice.
        visible_chars: Array.from(message.content).length,
      })
    }
    if (message.activity && message.activity.status !== "cancelled") {
      frontier.activity_ids.push(serverId)
    }
    if (visibleStructureIds.has(serverId)) {
      frontier.structure_ids.push(serverId)
    }
  }
  return frontier
}

/** Project the server's authoritative Stop result onto the live array. A
 * retraction removes the whole Turn; a cancellation keeps only the reported
 * visible prefix/facts and retires an active Activity by the existing law. */
export function applyStoppedTurnFrontier(
  messages: readonly OverlayMessage[],
  turnIds: ReadonlySet<string>,
  outcome: "cancelled" | "retracted",
  frontier: ChatTurnVisibleFrontier,
): OverlayMessage[] {
  const prose = new Map(frontier.prose.map((row) => [row.message_id, row.visible_chars]))
  const activities = new Set(frontier.activity_ids)
  const structures = new Set(frontier.structure_ids)
  const next: OverlayMessage[] = []
  for (const message of messages) {
    const openingRow = message.role === "user" && turnIds.has(message.id)
    const owned = openingRow || (message.turnId != null && turnIds.has(message.turnId))
    if (!owned) {
      next.push(message)
      continue
    }
    if (outcome === "retracted") continue
    if (openingRow) {
      next.push(message)
      continue
    }
    const serverId = message.serverMessageId
    if (!serverId) continue
    const prefix = Math.min(prose.get(serverId) ?? 0, Array.from(message.content).length)
    const visibleText = Array.from(message.content).slice(0, prefix).join("")
    const keepProse = visibleText.trim().length > 0
    const keepActivity = activities.has(serverId)
    const keepStructure = structures.has(serverId)
    if (!keepProse && !keepActivity && !keepStructure) continue
    next.push({
      ...message,
      content: visibleText,
      streaming: false,
      blocks: keepStructure ? message.blocks : undefined,
      candidates: keepStructure ? message.candidates : undefined,
      activity:
        keepActivity && message.activity?.status === "active"
          ? { ...message.activity, status: "cancelled" }
          : message.activity,
    })
  }
  return next
}
