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
  VideoStoryboardBlock,
} from "./timeline/types"
import { stampServerMessageId } from "./timeline/identity"

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

/** Generic watch windows speak only for the new tail. Run review is the one
 * scoped exception: its delivery may already precede a newer user turn, but
 * it still belongs to this run and is inserted by seq rather than dropped. */
export function shouldAdmitPolledTrigger({
  fresh,
  reviewRunId,
  rowRunId,
}: {
  fresh: boolean
  reviewRunId: string | null
  rowRunId: string | null | undefined
}): boolean {
  return reviewRunId == null ? fresh : rowRunId === reviewRunId
}

/** A recovery delivery carries the server's persistent upload-retry number.
 * The initial terminal transition is attempt zero; no timestamp participates. */
export function deliveryUploadRetryCount(ref: string | undefined): number | null {
  if (ref == null || ref.length === 0) return 0
  const match = /:upload-retry-(\d+)$/.exec(ref)
  if (!match) return ref.includes(":upload-retry-") ? null : 0
  const count = Number(match[1])
  return Number.isSafeInteger(count) ? count : null
}

export function isCurrentRunAttemptDelivery(
  message: Pick<OverlayMessage, "runId" | "runDelivery" | "runDeliveryRef">,
  runId: string | null,
  uploadRetryCount: number,
): boolean {
  return (
    runId != null &&
    message.runId === runId &&
    message.runDelivery === true &&
    deliveryUploadRetryCount(message.runDeliveryRef) === uploadRetryCount
  )
}

/** Live review still settles only after the existing drained-suggestions edge;
 * a hydrated delivery is already a historical fact and never waits 60s. */
export function runReviewerLanded(
  messages: OverlayMessage[],
  runId: string | null,
  uploadRetryCount: number,
): boolean {
  return messages.some(
    (message) =>
      isCurrentRunAttemptDelivery(message, runId, uploadRetryCount) &&
      (message.suggestions !== undefined || message.hydrated === true),
  )
}

export function hasAnyRunDelivery(messages: OverlayMessage[], runId: string | null): boolean {
  return runId != null && messages.some((message) => message.runId === runId && message.runDelivery === true)
}

/** Birth adapter for server-born prose recovery. Content still enters through
 * the caller's typewriter; structured references arrive with the same row. */
export function buildRecoveredProseMessage({
  id,
  seq,
  createdAt,
  turnId,
  runId,
  blocks,
  runDelivery,
  runDeliveryRef,
  outputRefs,
}: {
  id: string
  seq?: number | null
  createdAt?: string
  turnId?: string | null
  runId?: string | null
  blocks?: VideoStoryboardBlock[]
  runDelivery: boolean
  runDeliveryRef?: string
  outputRefs?: string[]
}): OverlayMessage {
  return {
    id,
    role: "assistant",
    content: "",
    streaming: true,
    seq: seq ?? undefined,
    at: createdAt,
    runId,
    turnId: turnId ?? undefined,
    blocks: blocks?.length ? blocks : undefined,
    runDelivery,
    runDeliveryRef,
    outputRefs,
    independentKind: runDelivery ? "trigger" : undefined,
  }
}

/** Adapt one fresh polled activity/material row with the same identity facts
 * as history replay. Only ordinary turn activities register as live work
 * hosts; material beats are independent world facts and never join that set. */
export function buildRecoveredActivityRow({
  id,
  seq,
  createdAt,
  turnId,
  beat,
  material,
}: {
  id: string
  seq?: number | null
  createdAt?: string
  turnId?: string | null
  beat: ActivityRowFrame
  material: boolean
}): { message: OverlayMessage; registerHost: boolean } {
  return {
    message: {
      id,
      role: "assistant",
      content: "",
      turnId: turnId ?? undefined,
      independentKind: material ? "material" : undefined,
      seq: seq ?? undefined,
      at: createdAt,
      activity: { ...beat, at: beat.at ?? createdAt },
    },
    registerHost: !material,
  }
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
