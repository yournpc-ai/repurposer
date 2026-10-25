/** Admission and placement for server rows recovered outside their birth SSE.
 *
 * The live array is not a second history replay: an old activity that a poll
 * happens to discover must not suddenly appear at the live edge. Prose is
 * different — a delivery still has to arrive — so it is inserted at its
 * persisted seq position and paced by the caller. No clock participates in
 * either decision. */

import type { OverlayMessage } from "./historyReplay"

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

/** Mount replay is older than rows born locally after mount. It only fills
 * missing archive ids; an existing live row keeps its typing and identity. */
export function prependMissingHistory(
  prev: OverlayMessage[],
  history: OverlayMessage[],
): OverlayMessage[] {
  const known = new Set(prev.map((message) => message.id))
  const missing = history.filter((message) => !known.has(message.id))
  return missing.length > 0 ? [...missing, ...prev] : prev
}
