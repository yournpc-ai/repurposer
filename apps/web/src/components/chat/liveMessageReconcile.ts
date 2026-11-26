/** Admission and placement for server rows recovered outside their birth SSE.
 *
 * The live array is not a second history replay: an old activity that a poll
 * happens to discover must not suddenly appear at the live edge. Prose is
 * different — a delivery still has to arrive — so it is inserted at its
 * persisted seq position and paced by the caller. No clock participates in
 * either decision. */

import type {
  ActivityRowFrame,
  OverlayMessage,
  MessageBlock,
} from "./timeline/types"
import { stampServerMessageId } from "./timeline/identity"
import { deliveryOutputRefs, messageReceiptFacts, parseFeedbackSummary, parseStepsPlan } from "./timeline/history"

export { prependMissingHistory, stampServerMessageId } from "./timeline/identity"

/** The last server position this client has observed, including non-render
 * rows. Rendered rows are a fallback while their observation stamp is still
 * propagating through React state. */
export function observedMessageSeq(
  observed: number | null,
  messages: OverlayMessage[],
): number | null {
  let latest = observed
  for (const message of messages) {
    if (message.seq != null && (latest == null || message.seq > latest)) {
      latest = message.seq
    }
  }
  return latest
}

/** A poll admits activity only when it extends the server tail observed
 * before that response. The first response after a client with no server
 * observation is a baseline, never permission to replay old work rows. */
export function isFreshPolledRow(
  seq: number | null | undefined,
  observedBefore: number | null,
): boolean {
  return seq != null && observedBefore != null && seq > observedBefore
}

/** Birth adapter for server-born prose recovery. Content still enters through
 * the caller's typewriter; structured references arrive with the same row. */
export function buildRecoveredProseMessage({
  id,
  seq,
  createdAt,
  turnId,
  blocks,
  outputRefs,
  intent,
}: {
  id: string
  seq?: number | null
  createdAt?: string
  turnId?: string | null
  blocks?: MessageBlock[]
  outputRefs?: string[]
  intent?: unknown
}): OverlayMessage {
  return {
    id,
    serverMessageId: id,
    role: "assistant",
    content: "",
    streaming: true,
    seq: seq ?? undefined,
    at: createdAt,
    turnId: turnId ?? undefined,
    blocks: blocks?.length ? blocks : undefined,
    ...messageReceiptFacts(intent),
    outputRefs,
  }
}

export function buildRecoveredActivityRow({
  id,
  seq,
  createdAt,
  turnId,
  beat,
}: {
  id: string
  seq?: number | null
  createdAt?: string
  turnId?: string | null
  beat: ActivityRowFrame
}): { message: OverlayMessage; registerHost: boolean } {
  return {
    message: {
      id,
      role: "assistant",
      content: "",
      turnId: turnId ?? undefined,
      seq: seq ?? undefined,
      at: createdAt,
      activity: { ...beat, at: beat.at ?? createdAt },
    },
    registerHost: true,
  }
}

/** Apply an accepted envelope only to its existing speech seat. Ownership
 * is checked by the caller before scheduling; a deferred updater never
 * appends a vanished stopped row or rewrites the successor's presentation. */
export function stampMessagePresentation(
  messages: OverlayMessage[],
  previewId: string,
  message: {
    id: string
    run_id?: string | null
    display_role?: OverlayMessage["displayRole"] | null
    question?: unknown
    answer?: unknown
    blocks?: MessageBlock[]
    intent?: unknown
    steps?: unknown
    feedback?: unknown
  },
): OverlayMessage[] {
  const blocks = message.blocks?.length ? message.blocks : undefined
  const outputRefs = deliveryOutputRefs(message.intent)
  const facts = messageReceiptFacts(message.intent)
  const steps = parseStepsPlan(message.steps, message.intent)
  const feedback = parseFeedbackSummary(message.feedback)
  const intentObj = message.intent && typeof message.intent === "object"
    ? (message.intent as Record<string, unknown>)
    : null
  const turnProse = intentObj?.turn_prose === true
  const runId =
    typeof message.run_id === "string" && message.run_id
      ? message.run_id
      : typeof intentObj?.run_id === "string" && intentObj.run_id
        ? intentObj.run_id
        : undefined
  const displayRole = message.display_role ?? undefined
  const questionPayload = message.question as { options?: unknown[]; items?: unknown[] } | null | undefined
  const isDockedQuestionFraming = Boolean(
    questionPayload &&
    !message.answer &&
    ((questionPayload.options?.length ?? 0) > 0 || (questionPayload.items?.length ?? 0) > 0),
  )
  if (
    !blocks &&
    outputRefs.length === 0 &&
    !facts.jobReceipt &&
    !steps &&
    feedback === undefined &&
    !turnProse &&
    !runId &&
    !displayRole &&
    !isDockedQuestionFraming
  ) return messages
  const targetId = messages.some((row) => row.id === previewId) ? previewId : message.id
  return messages.map((row) => row.id === targetId ? {
    ...row,
    ...(blocks ? { blocks } : {}),
    ...facts,
    ...(steps ? { steps } : {}),
    ...(turnProse ? { turnProse: true } : {}),
    ...(runId ? { runId } : {}),
    ...(displayRole ? { displayRole } : {}),
    ...(isDockedQuestionFraming ? { questionEcho: true } : {}),
    ...(feedback !== undefined ? { feedback } : {}),
    ...(outputRefs.length > 0 ? { outputRefs } : {}),
  } : row)
}

/** Stream ownership is the owner object's identity, not the latest turn id.
 * A stopped stream can therefore never adopt or clear its successor. */
export function isTurnOwner<T>(current: T | null, owner: T): boolean {
  return current === owner
}

export function releaseTurnOwner<T>(current: T | null, owner: T): T | null {
  return isTurnOwner(current, owner) ? null : current
}

/** A persisted early failure carries the server turn id before any assistant
 * row arrives. Reconcile the optimistic user row by its exact local id so the
 * live block and a later history replay share the same ownership. */
export function reconcilePersistedFailure(
  prev: OverlayMessage[],
  rollbackId: string,
  turnId: string,
): OverlayMessage[] {
  const rows = prev.map((message) =>
    message.id === rollbackId ? { ...message, turnId } : message,
  )
  return stampServerMessageId(rows, rollbackId, turnId)
}

/** Insert one recovered row without disturbing the birth order of rows
 * already live. A later persisted seq is an exact successor. With no such
 * successor, a backfilled row goes before the unsequenced optimistic suffix;
 * a fresh row stays at the live edge. Duplicate server ids are no-ops. */
export function insertRecoveredMessage(
  prev: OverlayMessage[],
  row: OverlayMessage,
  { fresh }: { fresh: boolean },
): OverlayMessage[] {
  if (prev.some((message) => message.id === row.id)) return prev

  const seq = row.seq
  if (seq != null) {
    const successor = prev.findIndex(
      (message) => message.seq != null && message.seq > seq,
    )
    if (successor >= 0) {
      return [...prev.slice(0, successor), row, ...prev.slice(successor)]
    }
  }

  if (fresh) return [...prev, row]

  let lastSequenced = -1
  for (let index = 0; index < prev.length; index += 1) {
    if (prev[index].seq != null) lastSequenced = index
  }
  const insertion = lastSequenced + 1
  return [...prev.slice(0, insertion), row, ...prev.slice(insertion)]
}
