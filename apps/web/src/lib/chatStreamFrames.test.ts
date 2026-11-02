/** Stream dispatch contract (Phase 3 Batch A): the SSE event-name → typed
 * frame routing — the three-channel separation (ADR-087 §1: System Status /
 * Activity / Conversation) plus the terminal pair, with the malformed-JSON
 * failure semantics the inline dispatch had (throw, never swallow). */

import { describe, expect, it } from "vitest"

import {
  releaseSettledCandidateRows,
  reduceCandidateFrame,
  routeStreamFrame,
} from "./chatStreamFrames"
import {
  buildConversationBlocks,
  buildConversationUnits,
} from "@/components/chat/timeline/project"
import type { OverlayMessage } from "@/components/chat/timeline/types"

const CHAT_TERMINAL = { completed: "turn.completed", failed: "turn.failed" }
const ANSWER_TERMINAL = { completed: "answer.completed", failed: "answer.failed" }

describe("conversation channel", () => {
  it("assistant.delta → delta text and its nullable server row identity", () => {
    expect(routeStreamFrame("assistant.delta", `{"text":"hel"}`, CHAT_TERMINAL))
      .toEqual({ kind: "delta", text: "hel", messageId: null })
    expect(routeStreamFrame("assistant.delta", `{"text":"hel","message_id":"row-1"}`, CHAT_TERMINAL))
      .toEqual({ kind: "delta", text: "hel", messageId: "row-1" })
  })

  it("assistant.interim_prose carries stable row identity, seq and Turn identity", () => {
    expect(
      routeStreamFrame(
        "assistant.interim_prose",
        `{"text":"found it","turn_id":"turn-7","message_id":"row-9","seq":12}`,
        CHAT_TERMINAL,
      ),
    ).toEqual({
      kind: "interim_prose",
      text: "found it",
      turnId: "turn-7",
      messageId: "row-9",
      seq: 12,
    })
  })

  it("assistant.interim_prose rejects a frame without its server row identity", () => {
    expect(() =>
      routeStreamFrame("assistant.interim_prose", `{"text":"old"}`, ANSWER_TERMINAL),
    ).toThrow("message_id")
  })

  it("assistant.candidates keeps nullable server identity on both event families", () => {
    const set = {
      kind: "set",
      candidate_set_id: "set-1",
      topic: "topic",
      members: [],
      turn_id: "turn-9",
    }
    expect(
      routeStreamFrame("assistant.candidates", JSON.stringify(set), CHAT_TERMINAL),
    ).toEqual({ kind: "candidates", event: set })
    const selection = { kind: "selection", candidate_set_id: "set-1", selected: [0] }
    expect(
      routeStreamFrame("assistant.candidates", JSON.stringify(selection), ANSWER_TERMINAL),
    ).toEqual({ kind: "candidates", event: selection })
  })

  it("question.preview → the pill payload", () => {
    const payload = { question: "which?", options: [{ id: "a", label: "A" }] }
    expect(routeStreamFrame("question.preview", JSON.stringify(payload), CHAT_TERMINAL))
      .toEqual({ kind: "question_preview", payload })
  })
})

describe("candidate live reducer identity", () => {
  const set = {
    kind: "set" as const,
    candidate_set_id: "set-1",
    topic: "Source picks",
    members: [],
    turn_id: "turn-server",
  }

  it("a new card consumes the frame identity, never the current client turn", () => {
    const rows = reduceCandidateFrame([], set, "2026-10-30T00:00:00Z")
    expect(rows[0]).toMatchObject({
      id: "live-cand-set-1",
      turnId: "turn-server",
      independentKind: undefined,
    })
  })

  it("old frames stay identity-unknown and selection never invents a relation", () => {
    const legacy = { ...set, turn_id: undefined }
    const born = reduceCandidateFrame([], legacy, "2026-10-30T00:00:00Z")
    expect(born[0].turnId).toBeUndefined()
    const selected = reduceCandidateFrame(born, {
      kind: "selection",
      candidate_set_id: "set-1",
      selected: [0],
      turn_id: "another-turn",
    }, "2026-10-30T00:00:01Z")
    expect(selected[0].turnId).toBeUndefined()
    expect(selected[0].candidates?.selected).toEqual([0])
  })

  it("an idempotent set repaint preserves the existing row identity and selection", () => {
    const existing: OverlayMessage[] = [{
      id: "history-candidate",
      role: "assistant",
      content: "",
      turnId: "turn-original",
      independentKind: "candidate",
      candidates: {
        candidateSetId: "set-1",
        topic: "Old",
        assetId: null,
        members: [],
        selected: [2],
      },
      hydrated: true,
    }]
    const next = reduceCandidateFrame(existing, set, "2026-10-30T00:00:00Z")
    expect(next[0].id).toBe("history-candidate")
    expect(next[0].turnId).toBe("turn-original")
    expect(next[0].candidates?.selected).toEqual([2])
  })

  it("births a pending set once after its drained final reply and keeps selection in place", () => {
    const user: OverlayMessage = {
      id: "turn-server",
      role: "user",
      content: "find sounds",
      turnId: "turn-server",
    }
    const pending = reduceCandidateFrame([], set, "2026-10-30T00:00:00Z")
    const thinkingReply: OverlayMessage = {
      id: "reply-local",
      role: "assistant",
      content: "Three candidates are ready.",
      turnId: "turn-server",
      streaming: true,
    }
    const thinking = [user, thinkingReply]
    expect(buildConversationUnits(thinking).map((unit) =>
      unit.kind === "message" ? unit.message.id : unit.rowKey,
    )).toEqual(["turn-server", "reply-local"])

    const settledReply = {
      ...thinkingReply,
      streaming: false,
      proseDrainedAtMs: 100,
    }
    const settled = releaseSettledCandidateRows(
      [user, settledReply],
      pending,
      "reply-local",
    )
    expect(settled.map((message) => message.id)).toEqual([
      "turn-server",
      "reply-local",
      "live-cand-set-1",
    ])
    expect(releaseSettledCandidateRows(settled, pending, "reply-local")).toBe(settled)
    const blocks = buildConversationBlocks(buildConversationUnits(settled))
    expect(blocks).toHaveLength(1)
    expect(blocks[0].kind).toBe("turn")
    expect(blocks[0].kind === "turn" && blocks[0].units.map((unit) =>
      unit.kind === "message" ? unit.message.id : unit.rowKey,
    )).toEqual(["turn-server", "reply-local", "live-cand-set-1"])

    const selected = reduceCandidateFrame(settled, {
      kind: "selection",
      candidate_set_id: "set-1",
      selected: [0],
      turn_id: "another-turn",
    }, "2026-10-30T00:00:01Z")
    expect(selected.map((message) => message.id)).toEqual(settled.map((message) => message.id))
    expect(selected.filter((message) => message.candidates)).toHaveLength(1)
    expect(selected[2].candidates?.selected).toEqual([0])
  })

  it("does not treat drained interim prose as the candidate's final release", () => {
    const user: OverlayMessage = {
      id: "turn-server",
      role: "user",
      content: "find sounds",
      turnId: "turn-server",
    }
    const interim: OverlayMessage = {
      id: "interim-server",
      role: "assistant",
      content: "I found some options.",
      turnId: "turn-server",
      streaming: false,
      proseDrainedAtMs: 50,
    }
    let pending = reduceCandidateFrame([], set, "2026-10-30T00:00:00Z")
    pending = reduceCandidateFrame(pending, {
      kind: "selection",
      candidate_set_id: "set-1",
      selected: [0],
      turn_id: "turn-server",
    }, "2026-10-30T00:00:01Z")
    const finalReply: OverlayMessage = {
      id: "reply-local",
      role: "assistant",
      content: "Three candidates are ready.",
      turnId: "turn-server",
      streaming: true,
    }
    expect(buildConversationUnits([user, interim, finalReply]).map((unit) =>
      unit.kind === "message" ? unit.message.id : unit.rowKey,
    )).toEqual(["turn-server", "interim-server", "reply-local"])

    const settled = releaseSettledCandidateRows(
      [user, interim, { ...finalReply, streaming: false, proseDrainedAtMs: 100 }],
      pending,
      "reply-local",
    )
    expect(settled.map((message) => message.id)).toEqual([
      "turn-server",
      "interim-server",
      "reply-local",
      "live-cand-set-1",
    ])
    expect(settled[3].candidates?.selected).toEqual([0])
  })

  it("does not merge different real candidate sets", () => {
    const first = reduceCandidateFrame([], set, "2026-10-30T00:00:00Z")
    const both = reduceCandidateFrame(first, {
      ...set,
      candidate_set_id: "set-2",
    }, "2026-10-30T00:00:01Z")
    expect(both.filter((message) => message.candidates)).toHaveLength(2)
    expect(both.map((message) => message.candidates?.candidateSetId)).toEqual(["set-1", "set-2"])
  })
})

describe("system status channel", () => {
  it("assistant.thinking routes the payload verbatim (keepalive `{}` included)", () => {
    expect(routeStreamFrame("assistant.thinking", `{}`, CHAT_TERMINAL))
      .toEqual({ kind: "thinking", payload: {} })
    // The surviving System Status labels are the film design span's
    // (Batch B ③ retired drafting/inspecting/repairing to the Activity
    // channel; composing retired later — a plain LLM window wears the base
    // thinking word, never an alias).
    expect(routeStreamFrame("assistant.thinking", `{"phase":"storyboarding"}`, CHAT_TERMINAL))
      .toEqual({ kind: "thinking", payload: { phase: "storyboarding" } })
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

  it("terminal.failed carries detail + persisted and tolerates missing identity", () => {
    expect(
      routeStreamFrame("turn.failed", `{"detail":"boom","persisted":true}`, CHAT_TERMINAL),
    ).toEqual({ kind: "failed", detail: "boom", persisted: true, turnId: null })
    expect(routeStreamFrame("turn.failed", `{"detail":"boom"}`, CHAT_TERMINAL))
      .toEqual({ kind: "failed", detail: "boom", persisted: false, turnId: null })
  })

  it("terminal.failed exposes the answer continuation's inherited identity", () => {
    expect(
      routeStreamFrame(
        "answer.failed",
        `{"detail":"boom","turn_id":"turn-original"}`,
        ANSWER_TERMINAL,
      ),
    ).toEqual({
      kind: "failed",
      detail: "boom",
      persisted: false,
      turnId: "turn-original",
    })
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
