/** Stream dispatch contract (Phase 3 Batch A): the SSE event-name → typed
 * frame routing — the three-channel separation (ADR-087 §1: System Status /
 * Activity / Conversation) plus the terminal pair, with the malformed-JSON
 * failure semantics the inline dispatch had (throw, never swallow). */

import { describe, expect, it } from "vitest"

import { routeStreamFrame } from "./chatStreamFrames"

const CHAT_TERMINAL = { completed: "turn.completed", failed: "turn.failed" }
const ANSWER_TERMINAL = { completed: "answer.completed", failed: "answer.failed" }

describe("conversation channel", () => {
  it("assistant.delta → delta text", () => {
    expect(routeStreamFrame("assistant.delta", `{"text":"hel"}`, CHAT_TERMINAL))
      .toEqual({ kind: "delta", text: "hel" })
  })

  it("assistant.checkpoint → checkpoint text (its own bubble segment)", () => {
    expect(routeStreamFrame("assistant.checkpoint", `{"text":"found it"}`, CHAT_TERMINAL))
      .toEqual({ kind: "checkpoint", text: "found it" })
  })

  it("question.preview → the pill payload", () => {
    const payload = { question: "which?", options: [{ id: "a", label: "A" }] }
    expect(routeStreamFrame("question.preview", JSON.stringify(payload), CHAT_TERMINAL))
      .toEqual({ kind: "question_preview", payload })
  })
})

describe("system status channel", () => {
  it("assistant.thinking routes the payload verbatim (keepalive `{}` included)", () => {
    expect(routeStreamFrame("assistant.thinking", `{}`, CHAT_TERMINAL))
      .toEqual({ kind: "thinking", payload: {} })
    // The surviving System Status label (Batch B ③ retired drafting/
    // inspecting/repairing to the Activity channel).
    expect(routeStreamFrame("assistant.thinking", `{"phase":"composing"}`, CHAT_TERMINAL))
      .toEqual({ kind: "thinking", payload: { phase: "composing" } })
  })

  it("the explicit phase clear ({phase: null}) routes as a payload, not an ignore", () => {
    expect(routeStreamFrame("assistant.thinking", `{"phase":null}`, CHAT_TERMINAL))
      .toEqual({ kind: "thinking", payload: { phase: null } })
  })
})

describe("activity channel", () => {
  it("assistant.activity → the append-only frame", () => {
    const frame = {
      activity_id: "act-1",
      seq: 3,
      kind: "draft",
      status: "active",
      key: "chat.activity.draft",
    }
    expect(routeStreamFrame("assistant.activity", JSON.stringify(frame), CHAT_TERMINAL))
      .toEqual({ kind: "activity", frame })
  })
})

describe("transcript array mirror (ADR-108 §3)", () => {
  it("assistant.row.append → the row payload (append fixes the position)", () => {
    const row = {
      id: "row-1",
      role: "assistant",
      content: "",
      seq: 7,
      intent: { type: "activity", frame: { activity_id: "a1", kind: "read", status: "active", key: "chat.inspecting.transcript" } },
      created_at: "2026-10-07T10:00:00Z",
    }
    expect(
      routeStreamFrame("assistant.row.append", JSON.stringify({ row }), CHAT_TERMINAL),
    ).toEqual({ kind: "row_append", row })
  })

  it("assistant.row.update → id + the settled frame (in-place, position never moves)", () => {
    const frame = {
      activity_id: "a1",
      kind: "read",
      status: "completed",
      key: "chat.inspectingDone.transcript",
      duration_ms: 820,
    }
    expect(
      routeStreamFrame(
        "assistant.row.update",
        JSON.stringify({ id: "row-1", frame }),
        CHAT_TERMINAL,
      ),
    ).toEqual({ kind: "row_update", id: "row-1", frame })
  })
})

describe("terminal pair", () => {
  it("the terminal names come from the turn, never hardcoded", () => {
    expect(routeStreamFrame("turn.completed", `{"ok":1}`, CHAT_TERMINAL))
      .toEqual({ kind: "completed", envelope: { ok: 1 } })
    expect(routeStreamFrame("answer.completed", `{"ok":2}`, CHAT_TERMINAL))
      // a chat turn does NOT resolve on the answer endpoint's terminal
      .toEqual({ kind: "ignored" })
    expect(routeStreamFrame("answer.completed", `{"ok":2}`, ANSWER_TERMINAL))
      .toEqual({ kind: "completed", envelope: { ok: 2 } })
  })

  it("terminal.failed carries detail + persisted (turn durability)", () => {
    expect(
      routeStreamFrame("turn.failed", `{"detail":"boom","persisted":true}`, CHAT_TERMINAL),
    ).toEqual({ kind: "failed", detail: "boom", persisted: true })
    expect(routeStreamFrame("turn.failed", `{"detail":"boom"}`, CHAT_TERMINAL))
      .toEqual({ kind: "failed", detail: "boom", persisted: false })
  })
})

describe("failure + ignore semantics", () => {
  it("unknown events are ignored (forward compatibility)", () => {
    expect(routeStreamFrame("assistant.future", `{}`, CHAT_TERMINAL)).toEqual({
      kind: "ignored",
    })
  })

  it("malformed JSON throws (same as the retired inline dispatch — never swallowed)", () => {
    expect(() => routeStreamFrame("assistant.delta", `{oops`, CHAT_TERMINAL)).toThrow()
    expect(() => routeStreamFrame("turn.completed", `not json`, CHAT_TERMINAL)).toThrow()
  })
})
