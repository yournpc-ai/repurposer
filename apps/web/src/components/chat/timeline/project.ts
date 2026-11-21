/** The conversation timeline layer (ADR-108 数组位置律): the persisted
 * array's order IS the render order — this module MAPS rows to units and
 * never re-sorts (no timestamps, no walk keys, no anchors). Pure, no React
 * (the vitest seam); ChatDock composes the units, this module owns the
 * SHAPE (message vs activity vs fold) and the folding projection. */

import {
  foldActivityUnits,
  isDraftSpanRow,
  isRunSpanRow,
} from "./activity"
import type {
  ConversationBlock,
  ConversationUnit,
  OverlayMessage,
} from "./types"

/** Array map (ADR-108): each message row maps to ONE unit in place —
 * activity-carrying rows become activity units at their array position.
 * An ACTIVE activity enters the walk immediately: its host is the live work
 * segment's seat, so a short first activity never depends on the bottom
 * now-line becoming visible. A CANCELLED attempt retires from the visible
 * walk (automatic retry / stop is not a finished work receipt); its forensic
 * record remains server-side. Real FAILED rows stay visible. Retired draft /
 * run spans keep their existing card / receipt evidence. */
export function buildConversationUnits(
  messages: OverlayMessage[],
): ConversationUnit[] {
  const units: ConversationUnit[] = []
  const deliveries = new Map<string, OverlayMessage>()
  const receipts = new Map<string, OverlayMessage>()
  const nextAnswer = new Map<string, OverlayMessage>()
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (m.mediaProgress) {
      if (m.runId) receipts.set(m.runId, m)
      continue
    }
    if (m.mediaOpeningId && m.content.trim() && !m.activity) nextAnswer.set(m.mediaOpeningId, m)
    if (m.runId && m.runDelivery && m.content.trim()) deliveries.set(m.runId, m)
    if (m.activity?.kind === "run" && m.runId && m.turnId) {
      const answer = nextAnswer.get(m.turnId)
      if (answer && !deliveries.has(m.runId)) deliveries.set(m.runId, answer)
    }
    if (m.role === "user") nextAnswer.clear()
  }
  for (const m of messages) {
    if (m.activityDisplayHeld || m.mediaProgress) continue
    if (m.runId && m.activity?.kind === "run") {
      const answer = deliveries.get(m.runId)
      const completed = !!answer || receipts.has(m.runId)
      const end = answer?.clientVisibleAtMs ?? (answer?.at ? Date.parse(answer.at) : undefined)
      const start = m.at ? Date.parse(m.at) : undefined
      const receipt = receipts.get(m.runId)
      const taskEnd = receipt?.at ? Date.parse(receipt.at) : end
      const elapsed = start != null && taskEnd != null && taskEnd >= start ? taskEnd - start : undefined
      units.push({
        kind: "activity", rowKey: m.birthKey ?? m.id, turnId: m.turnId, workRunId: m.runId,
        workEndedAtMs: end != null && Number.isFinite(end) ? end : undefined,
        activity: {
          ...m.activity, status: completed ? "completed" : m.activity.status === "cancelled" ? "cancelled" : "active",
          key: completed ? `${m.activity.key}Done` : m.activity.key, duration_ms: elapsed,
        },
      })
      continue
    }
    const a = m.activity
    if (a === undefined) {
      units.push({ kind: "message", message: m })
      if (m.continuationTurnId && m.content.trim() && (m.hydrated || m.proseDrainedAtMs != null)) {
        // The stage answered, but the original request is still executing.
        // Give the next work segment an anchor that its first tool will inherit.
        const key = `continue:${m.serverMessageId ?? m.id}`
        units.push({
          kind: "activity", turnId: m.continuationTurnId, rowKey: key,
          activity: { activity_id: key, kind: "run", status: "active", key: null, at: m.at },
        })
      }
      continue
    }
    if (!a.group_id && a.status === "cancelled") continue // abandoned attempt, not a work receipt
    if (isDraftSpanRow(a) || isRunSpanRow(a)) continue // 落定即退役
    units.push({
      kind: "activity",
      activity: a,
      rowKey: m.birthKey ?? m.id,
      turnId: m.turnId,
      independentKind: m.independentKind,
      workStartedAtMs: m.workStartedAtMs,
      workEndedAtMs: m.workEndedAtMs,
    })
  }
  return units
}

type SourceBlock =
  | { kind: "turn"; key: string; turnId: string; units: ConversationUnit[] }
  | { kind: "standalone"; key: string; factKind: NonNullable<OverlayMessage["independentKind"]> | "legacy"; units: ConversationUnit[] }


export function buildConversationBlocks(units: ConversationUnit[]): ConversationBlock[] {
  const blocks: SourceBlock[] = []
  for (const unit of units) {
    const firstKey = unit.kind === "message" ? unit.message.birthKey ?? unit.message.id : unit.rowKey
    const turnId = unit.kind === "message" ? unit.message.turnId : unit.turnId
    const independentKind =
      unit.kind === "message" ? unit.message.independentKind : unit.independentKind
    if (!turnId || independentKind) {
      blocks.push({
        kind: "standalone",
        key: `${independentKind ?? "legacy"}:${firstKey}`,
        factKind: independentKind ?? "legacy",
        units: [unit],
      })
      continue
    }
    const current = blocks[blocks.length - 1]
    if (current?.kind === "turn" && current.turnId === turnId &&
      !(unit.kind === "message" && unit.message.role === "user")) {
      current.units.push(unit)
    } else {
      blocks.push({ kind: "turn", key: `turn:${firstKey}`, turnId, units: [unit] })
    }
  }
  // Turn ownership is established above from the real user row. Only then
  // remove its duplicate option bubble, and only when the matching option QA
  // is present in this same projection. The underlying message and turn id stay intact.
  const optionQuestionIds = new Set<string>()
  for (const unit of units) {
    if (unit.kind !== "message") continue
    const qa = unit.message.qa
    if (qa?.answerKind === "option" && qa.questionId) optionQuestionIds.add(qa.questionId)
  }
  const visibleBlocks: SourceBlock[] = []
  for (const block of blocks) {
    const visibleUnits = block.units.filter(
      (unit) =>
        unit.kind !== "message" ||
        unit.message.role !== "user" ||
        (unit.message.assets?.length ?? 0) > 0 ||
        unit.message.focus != null ||
        !unit.message.answeredQuestionId ||
        !optionQuestionIds.has(unit.message.answeredQuestionId),
    )
    if (visibleUnits.length > 0) visibleBlocks.push({ ...block, units: visibleUnits })
  }
  return composeResponses(visibleBlocks)
}

/** Compose only explicit associations in their existing transcript position.
 * An intervening user/QA/activity/world fact closes the current Run container;
 * later deliveries keep their own response instead of moving across it. */
function composeResponses(groups: SourceBlock[]): ConversationBlock[] {
  const result: ConversationBlock[] = []
  for (const group of groups) {
    if (group.kind === "turn") {
      const first = group.units[0]
      const user = first?.kind === "message" && first.message.role === "user" ? first.message : null
      result.push({ kind: "turn", key: group.key, turnId: group.turnId, user,
        slots: user ? group.units.slice(1) : group.units })
    } else {
      result.push({ kind: "standalone", key: group.key, factKind: group.factKind, slots: group.units })
    }
  }
  return result
}

/** Read the original transcript order from a presentation container. Run work
 * is a view of existing Run state, never an invented transcript unit. */
export function conversationBlockUnits(block: ConversationBlock): ConversationUnit[] {
  return [
    ...(block.kind === "turn" && block.user ? [{ kind: "message" as const, message: block.user }] : []),
    ...block.slots,
  ]
}

/** Seal the CURRENT turn's last open work segment at a real display /
 * terminal timestamp. `currentRowKeys` contains HOST MESSAGE ids observed
 * on this turn's row.append/update channel, so an old segment can neither
 * be sealed nor reopened by a later turn.
 * The clock lives on the first host row, survives fold remounts and later
 * frame merges, and is write-once. History has no such client fact and keeps
 * its honest activity-span fallback. `defaultWorkStartedAtMs` is the actual
 * client gesture for turns without a user / QA row (Start); it never
 * outranks a preceding visible-prose drain boundary. A display-edge seal
 * passes `beforeRowId`: only a fold BEFORE that exact prose row is eligible,
 * so a preceding interim_prose can never seal the activity segment born after
 * it. Terminal seals omit the boundary and close the current trailing fold. */
export function closeWorkSegment(
  messages: OverlayMessage[],
  currentRowKeys: ReadonlySet<string>,
  endedAtMs: number,
  defaultWorkStartedAtMs?: number,
  beforeRowId?: string,
): OverlayMessage[] {
  if (currentRowKeys.size === 0 || !Number.isFinite(endedAtMs)) return messages
  if (beforeRowId != null && !messages.some((m) => m.id === beforeRowId)) {
    return messages
  }
  const units = foldActivityUnits(
    buildConversationUnits(messages),
    defaultWorkStartedAtMs,
  )
  let fold: Extract<ConversationUnit, { kind: "activityFold" }> | undefined
  let crossedBoundary = beforeRowId == null
  for (let i = units.length - 1; i >= 0; i -= 1) {
    const unit = units[i]
    if (!crossedBoundary) {
      if (unit.kind === "message" && unit.message.id === beforeRowId) {
        crossedBoundary = true
      }
      continue
    }
    if (
      unit.kind === "activityFold" &&
      unit.rows.length > 0 && // an active-only attempt is not completed work
      unit.openTail &&
      currentRowKeys.has(unit.rowKey)
    ) {
      fold = unit
      break
    }
  }
  if (!fold) return messages
  let changed = false
  const next = messages.map((m) => {
    if ((m.birthKey ?? m.id) !== fold.rowKey || !m.activity) return m
    if (m.workEndedAtMs != null) return m
    changed = true
    return {
      ...m,
      ...(m.workStartedAtMs == null && fold.startedAtMs != null
        ? { workStartedAtMs: fold.startedAtMs }
        : {}),
      workEndedAtMs: endedAtMs,
    }
  })
  return changed ? next : messages
}
