/** reconcileStartAfterAbort — the Start-answer dead-stream recovery's
 * decision machine. The state problem under test: the Start request reached
 * the backend but the SSE receipt was lost — a lost receipt is NOT a failed
 * production. ORIGINAL QUESTION ROW FIRST: a newer pending dock never
 * proves the original start failed (its workflow_run_id wins over every
 * inference); a still-pending original is 尚未确认启动 (the request may
 * still be mid-flight), never an absolute "not started". The deps are
 * read-only by construction — the recovery can never auto-retry
 * production. */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { QuestionMessage } from "@/components/chat/historyReplay"

import { reconcileStartAfterAbort, type StartRecoveryDeps } from "./startRecovery"

function questionRow(over: Partial<QuestionMessage> = {}): QuestionMessage {
  return {
    id: "q1",
    content: "echo",
    question: { kind: "task_book" },
    answer: null,
    workflow_run_id: null,
    ...over,
  }
}

function deps(over: Partial<StartRecoveryDeps> = {}): StartRecoveryDeps {
  return {
    fetchConversation: async () => ({ id: "conv1", pending_question: null }),
    fetchMessages: async () => [],
    ...over,
  }
}

const START_ANSWER = { kind: "start" } as unknown as QuestionMessage["answer"]

describe("reconcileStartAfterAbort", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("backend accepted, receipt lost → started, attaching the row's run", async () => {
    // THE regression: the start committed before the pipe died — the
    // pending question is gone and the answered task_book row carries the
    // run. The recovery must attach THAT run, never restore the pill.
    const answered = questionRow({ answer: START_ANSWER, workflow_run_id: "run-abc" })
    const d = deps({ fetchMessages: async () => [answered] })
    const rec = await reconcileStartAfterAbort(questionRow(), d)
    expect(rec).toEqual({ state: "started", runId: "run-abc" })
  })

  it("原 Start 成功且已有新 pending → 仍找回原 run (a newer dock never outranks the row's run)", async () => {
    // New required case ①: the start committed AND a newer question has
    // since docked. The original row's workflow_run_id wins — the newer
    // pending does NOT prove the start failed.
    const answered = questionRow({ answer: START_ANSWER, workflow_run_id: "run-abc" })
    const d = deps({
      fetchConversation: async () => ({
        id: "conv1",
        pending_question: questionRow({ id: "q2-newer" }),
      }),
      fetchMessages: async () => [answered],
    })
    const rec = await reconcileStartAfterAbort(questionRow(), d)
    expect(rec).toEqual({ state: "started", runId: "run-abc" })
  })

  it("原请求处理中、读取仍见 pending → unconfirmed，不误报确定失败", async () => {
    // New required case ②: still pending, no run — the request may still
    // be mid-flight server-side. UNCONFIRMED (the fresh row restores),
    // never a settled/failed verdict.
    const pending = questionRow()
    const d = deps({
      fetchConversation: async () => ({ id: "conv1", pending_question: pending }),
      fetchMessages: async () => [questionRow()],
    })
    const rec = await reconcileStartAfterAbort(questionRow(), d)
    expect(rec).toEqual({ state: "unconfirmed", question: pending })
    expect(rec.state).not.toBe("settled")
  })

  it("answered without a run (bail / rejected start) → settled, never re-dock", async () => {
    const d = deps({
      fetchMessages: async () => [
        questionRow({
          answer: { kind: "bail" } as unknown as QuestionMessage["answer"],
        }),
      ],
    })
    const rec = await reconcileStartAfterAbort(questionRow(), d)
    expect(rec).toEqual({ state: "settled" })
  })

  it("unanswered original + a newer dock holds the floor → settled (superseded)", async () => {
    const d = deps({
      fetchConversation: async () => ({
        id: "conv1",
        pending_question: questionRow({ id: "q2-newer" }),
      }),
      fetchMessages: async () => [questionRow()],
    })
    const rec = await reconcileStartAfterAbort(questionRow(), d)
    expect(rec).toEqual({ state: "settled" })
  })

  it("pending gone and the row missing from the page → unknown (unprovable)", async () => {
    const d = deps({ fetchMessages: async () => [questionRow({ id: "someone-else" })] })
    const rec = await reconcileStartAfterAbort(questionRow(), d)
    expect(rec).toEqual({ state: "unknown" })
  })

  it("transport still down on the conversation read → unknown", async () => {
    const d = deps({ fetchConversation: async () => null })
    const rec = await reconcileStartAfterAbort(questionRow(), d)
    expect(rec).toEqual({ state: "unknown" })
  })

  it("transport down on the messages read → unknown", async () => {
    const d = deps({ fetchMessages: async () => null })
    const rec = await reconcileStartAfterAbort(questionRow(), d)
    expect(rec).toEqual({ state: "unknown" })
  })

  it("a hanging recovery read hits the deadline → unknown, never a stuck composer", async () => {
    // The recovery's own fetches ride apiFetch (no timeout): a half-open
    // connection would hang them — re-creating the stuck-chatBusy bug
    // inside the recovery. The whole recovery is deadline-bounded instead.
    const hanging = new Promise<never>(() => {})
    const d = deps({ fetchConversation: () => hanging })
    const recPromise = reconcileStartAfterAbort(questionRow(), d, { timeoutMs: 10_000 })
    await vi.advanceTimersByTimeAsync(10_000)
    expect(await recPromise).toEqual({ state: "unknown" })
  })

  it("the deadline timer is cleared once the decision lands", async () => {
    const pending = questionRow()
    const d = deps({
      fetchConversation: async () => ({ id: "conv1", pending_question: pending }),
      fetchMessages: async () => [questionRow()],
    })
    const rec = await reconcileStartAfterAbort(questionRow(), d, { timeoutMs: 10_000 })
    expect(rec.state).toBe("unconfirmed")
    expect(vi.getTimerCount()).toBe(0)
  })
})
