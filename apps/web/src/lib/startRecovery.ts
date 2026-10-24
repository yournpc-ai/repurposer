/** Start-answer dead-stream recovery (2026-10-22 拍板, 事实判断收紧 — backend-
 * accepted, receipt-lost): the Start pill's answer stream died silently (the
 * answer watchdog tripped), and the connection's death says NOTHING about
 * the production — a lost receipt is not a failed start. Re-read the
 * world's truth through the EXISTING read-only seats (the conversation's
 * pending question + the message rows), ORIGINAL QUESTION ROW FIRST: a
 * NEWER pending dock does NOT prove the original start failed — the run
 * may have committed before the pipe died (and before any newer dock), so
 * the original row's ``workflow_run_id`` is checked before ANY inference.
 * Exactly one honest state lands:
 *
 * - ``started`` — the original row carries a ``workflow_run_id``: the
 *   start committed. The run surface attaches (the RunTaskList IS the
 *   evidence); the pill never comes back — whatever the pending read says.
 * - ``unconfirmed`` — the original question still stands pending with no
 *   run: the request may STILL be mid-flight server-side (the server's
 *   disconnect-cancel may not have landed yet). Never an absolute "not
 *   started, no run" — the pill restores and the copy says the start is
 *   UNCONFIRMED; starting again is the USER's re-click, deduped
 *   server-side by the row lock / the settled-question codes (this
 *   machine never auto-retries production).
 * - ``settled`` — no run, and the original question is answered (without a
 *   run) or superseded by a newer dock. A settled question never re-docks
 *   (the dead-pill loop law, 2026-09-28).
 * - ``unknown`` — the truth is unreadable right now (the transport is
 *   still down, or the original row isn't in the fetched page). The pill
 *   restores (safe: a redundant re-click settles quietly) and the copy
 *   says the state could not be confirmed — never a guess in either
 *   direction.
 *
 * Pure decision machine: the two fetchers are injected so the regression
 * simulates backend-accepted-but-client-disconnected without a network.
 * The deps are READ-ONLY by construction — the recovery can never fire a
 * second start (不自动重复制作). The whole recovery is deadline-bounded
 * (apiFetch has no timeout — a half-open connection would hang the
 * recovery's own reads and re-create the stuck composer); the deadline
 * timer is cleared the moment the decision lands. */

import type { QuestionMessage } from "@/components/chat/historyReplay"

export type StartRecovery =
  | { state: "started"; runId: string }
  | { state: "unconfirmed"; question: QuestionMessage }
  | { state: "settled" }
  | { state: "unknown" }

export interface StartRecoveryDeps {
  /** GET the conversation — ``null`` = transport failure (never "no
   * pending question"; the tri-state is the whole point). */
  fetchConversation: () => Promise<{
    id?: string
    pending_question?: QuestionMessage | null
  } | null>
  /** GET the conversation's message rows — ``null`` = transport failure. */
  fetchMessages: (convId: string) => Promise<QuestionMessage[] | null>
}

export async function reconcileStartAfterAbort(
  question: QuestionMessage,
  deps: StartRecoveryDeps,
  opts?: { timeoutMs?: number },
): Promise<StartRecovery> {
  const timeoutMs = opts?.timeoutMs ?? 15_000
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      decide(question, deps),
      new Promise<StartRecovery>((resolve) => {
        timer = setTimeout(() => resolve({ state: "unknown" }), timeoutMs)
      }),
    ])
  } finally {
    // The deadline never outlives the decision — a landed recovery leaves
    // no timer behind (and a tripped one is already spent).
    if (timer !== undefined) clearTimeout(timer)
  }
}

async function decide(
  question: QuestionMessage,
  deps: StartRecoveryDeps,
): Promise<StartRecovery> {
  const conv = await deps.fetchConversation()
  if (!conv?.id) return { state: "unknown" }
  const pending = conv.pending_question ?? null
  const rows = await deps.fetchMessages(conv.id)
  if (rows === null) return { state: "unknown" }
  const row = rows.find((r) => r.id === question.id)
  // ORIGINAL ROW FIRST: the run beats every inference — a newer pending
  // dock does NOT prove the start failed.
  if (row?.workflow_run_id) return { state: "started", runId: row.workflow_run_id }
  if (pending != null && !pending.answer && pending.id === question.id) {
    // Still pending, no run — the request may still be mid-flight
    // server-side. UNCONFIRMED, never an absolute "not started".
    return { state: "unconfirmed", question: pending }
  }
  if (row?.answer) return { state: "settled" } // answered without a run
  if (row && pending && !pending.answer) {
    // The original row stands unanswered but a DIFFERENT question holds
    // the floor — superseded (the row lock rejects a late answer).
    return { state: "settled" }
  }
  return { state: "unknown" } // row missing / inconsistent — unprovable
}
