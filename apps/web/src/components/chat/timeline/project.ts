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
  for (const m of messages) {
    const a = m.activity
    if (a === undefined) {
      units.push({ kind: "message", message: m })
      continue
    }
    if (a.status === "cancelled") continue // abandoned attempt, not a work receipt
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

export interface ConversationRunProjection {
  attachedRunId?: string | null
  /** Only an active attached Run pins to the live edge. */
  pinAttachedRun?: boolean
}

/** rows → units → blocks. Only explicit turnId joins units into a TurnBlock;
 * independent and legacy facts retain their own block type. A Run anchors
 * immediately before its first explicitly associated delivery, preserving
 * mid-run QA above it. Without a delivery, the centralized legacy fallback
 * uses the first explicit Run association; timestamps and last-delivery
 * adjacency never participate. */
export function buildConversationBlocks(
  units: ConversationUnit[],
  runProjection: ConversationRunProjection = {},
): ConversationBlock[] {
  const runOrder: string[] = []
  const firstAssociationAfter = new Map<string, number>()
  const firstDeliveryAt = new Map<string, number>()
  for (let index = 0; index < units.length; index += 1) {
    const unit = units[index]
    if (unit.kind !== "message" || !unit.message.runId) continue
    const runId = unit.message.runId
    if (!runOrder.includes(runId)) runOrder.push(runId)
    if (unit.message.runDelivery) {
      if (!firstDeliveryAt.has(runId)) firstDeliveryAt.set(runId, index)
    } else if (!firstAssociationAfter.has(runId)) {
      firstAssociationAfter.set(runId, index + 1)
    }
  }

  const attachedRunId = runProjection.attachedRunId ?? null
  const insertions = new Map<number, string[]>()
  const insert = (index: number, runId: string) => {
    const existing = insertions.get(index) ?? []
    existing.push(runId)
    insertions.set(index, existing)
  }
  for (const runId of runOrder) {
    if (runProjection.pinAttachedRun && runId === attachedRunId) continue
    const index = firstDeliveryAt.get(runId) ?? firstAssociationAfter.get(runId)
    if (index != null) insert(index, runId)
  }
  if (attachedRunId) {
    const alreadyAnchored = runOrder.includes(attachedRunId) &&
      !(runProjection.pinAttachedRun === true)
    if (runProjection.pinAttachedRun || !alreadyAnchored) {
      insert(units.length, attachedRunId)
    }
  }

  type AnchoredUnit = ConversationUnit | { kind: "runAnchor"; runId: string }
  const anchoredUnits: AnchoredUnit[] = []
  for (let index = 0; index <= units.length; index += 1) {
    for (const runId of insertions.get(index) ?? []) {
      anchoredUnits.push({ kind: "runAnchor", runId })
    }
    if (index < units.length) anchoredUnits.push(units[index])
  }

  const blocks: ConversationBlock[] = []
  for (const unit of anchoredUnits) {
    if (unit.kind === "runAnchor") {
      blocks.push({ kind: "runAnchor", key: `run:${unit.runId}`, runId: unit.runId })
      continue
    }
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
    if (current?.kind === "turn" && current.turnId === turnId) {
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
  const visibleBlocks: ConversationBlock[] = []
  for (const block of blocks) {
    if (block.kind === "runAnchor") {
      visibleBlocks.push(block)
      continue
    }
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
  return visibleBlocks
}

/** Seal the CURRENT turn's last open work segment at a real display /
 * terminal timestamp. `currentRowKeys` contains HOST MESSAGE ids observed
 * on this turn's row.append/update channel — never per-turn activity_ids,
 * so an old segment with the same "a1" can neither be sealed nor reopened.
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
