/** The conversation timeline layer (ADR-108 数组位置律): the persisted
 * array's order IS the render order — this module MAPS rows to units and
 * never re-sorts (no timestamps, no walk keys, no anchors). Pure, no React
 * (the vitest seam); ChatDock composes the units, this module owns the
 * SHAPE (message vs activity vs fold) and the folding projection. */

import {
  foldActivityUnits,
  isConversationBoundary,
  isDraftSpanRow,
  isRunSpanRow,
} from "./activity"
import { parseActivityReceipt } from "./history"
import type {
  NativeJobReceipt,
  ConversationBlock,
  ConversationUnit,
  OverlayMessage,
} from "./types"

/** Array map (ADR-108): messages and their contents keep their positions —
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
  // Join a worker update to its declaration only within the same uninterrupted
  // opening. A receipt after approval belongs below the user's decision.
  let start = 0
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i]
    if (m.turnId !== messages[i + 1]?.turnId || !m.turnId ||
      isConversationBoundary(m) || i === messages.length - 1) {
      appendUnits(messages.slice(start, i + 1), units)
      start = i + 1
    }
  }
  return units
}

function appendUnits(messages: OverlayMessage[], units: ConversationUnit[]) {
  const jobs = new Map<string, NativeJobReceipt>()
  const activityCalls = new Set<string>()
  for (const message of messages) {
    if (!message.turnId) continue
    if (message.jobReceipt) jobs.set(message.jobReceipt.callId, message.jobReceipt)
    if (message.activity?.call_id && !message.activityDisplayHeld) {
      activityCalls.add(message.activity.call_id)
    }
  }
  for (const m of messages) {
    if (m.activityDisplayHeld) continue
    const a = m.activity
    if (a === undefined) {
      const job = m.jobReceipt
      if (!job) {
        units.push({ kind: "message", message: m })
        continue
      }
      // Some historical jobs have only an execution message. Keep its own
      // receipt at this position and its independently consumable content below.
      if (!activityCalls.has(job.callId)) {
        const pending = ["accepted", "queued", "active", "running"].includes(job.status)
        const failed = job.status === "failed" || job.status === "provider_unknown"
        units.push({
          kind: "activity", rowKey: `job:${m.birthKey ?? m.id}`, turnId: m.turnId, runId: m.runId,
          activity: {
            activity_id: job.callId, call_id: job.callId, tool_name: job.operation,
            kind: "run", key: null, jobReceipt: job,
            status: pending ? "active" : failed ? "failed" : "completed",
          },
        })
      }
      const hasStructuredContent = Boolean(
        m.blocks?.length || m.qa || m.outputRefs?.length || m.candidates || m.suggestions?.length || m.meta,
      )
      // Export completion already renders its status, credits, and clickable
      // thumbnail on the tool-call row; suppress the redundant boilerplate
      // "正式 MP4 已导出，待审片。" text row that otherwise duplicates the
      // agent's own follow-up prose.
      const redundantExportReceiptText =
        !hasStructuredContent && job.role === "export" && job.status === "available"
      if ((m.content && !redundantExportReceiptText) || hasStructuredContent) {
        units.push({ kind: "message", message: { ...m, jobReceipt: undefined, fromJobReceipt: true } })
      }
      continue
    }
    const retired = !a.call_id && ((!a.group_id && a.status === "cancelled") || isDraftSpanRow(a) || isRunSpanRow(a))
    if (!retired) {
      const jobReceipt = a.call_id && jobs.get(a.call_id)
      units.push({
        kind: "activity",
        activity: { ...a, receipt: parseActivityReceipt(a.receipt), ...(jobReceipt && { jobReceipt }) },
        rowKey: m.birthKey ?? m.id,
        turnId: m.turnId,
        runId: m.runId,
        independentKind: m.independentKind,
        workStartedAtMs: m.workStartedAtMs,
        workEndedAtMs: m.workEndedAtMs,
      })
    }
    if (m.qa || m.outputRefs?.length || m.blocks?.length || m.candidates) {
      units.push({ kind: "message", message: {
        ...m, birthKey: `${m.birthKey ?? m.id}:content`, activity: undefined, jobReceipt: undefined,
      } })
    }
  }
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
  const edge = beforeRowId == null ? messages.length : messages.findIndex(m => m.id === beforeRowId)
  if (edge < 0) return messages
  const visible = buildConversationUnits(messages.slice(0, edge))
  const lastHost = visible.slice().reverse().find(u => u.kind === "activity")
  const units = foldActivityUnits(visible, defaultWorkStartedAtMs, lastHost?.turnId)
  let fold: Extract<ConversationUnit, { kind: "activityFold" }> | undefined
  for (let i = units.length - 1; i >= 0; i -= 1) {
    const unit = units[i]
    if (
      unit.kind === "activityFold" &&
      unit.rows.length > 0 && // an active-only attempt is not completed work
      unit.openTail &&
      currentRowKeys.has(unit.clockRowKey)
    ) {
      fold = unit
      break
    }
  }
  if (!fold) return messages
  let changed = false
  const next = messages.map((m) => {
    if ((m.birthKey ?? m.id) !== fold.clockRowKey || !m.activity) return m
    if (m.workEndedAtMs != null) return m
    changed = true
    return {
      ...m,
      ...(fold.clockRowKey === fold.rowKey && m.workStartedAtMs == null && fold.startedAtMs != null
        ? { workStartedAtMs: fold.startedAtMs }
        : {}),
      workEndedAtMs: endedAtMs,
    }
  })
  return changed ? next : messages
}
