import { describe, expect, it } from "vitest"

import type { OverlayMessage } from "./types"
import { applyStoppedTurnFrontier, visibleFrontierForTurn } from "./visibility"

function row(partial: Partial<OverlayMessage> & Pick<OverlayMessage, "id" | "role">): OverlayMessage {
  return { content: "", ...partial }
}

describe("Chat Stop visible frontier", () => {
  it("reports only actually released prose and visible persisted facts", () => {
    const rows = [
      row({ id: "t1", role: "user", turnId: "t1", content: "request" }),
      row({
        id: "local-partial",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "partial-1",
        content: "abc",
        clientVisibleAtMs: 10,
      }),
      row({
        id: "local-interim",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "interim-1",
        content: "persisted but unseen",
      }),
      row({
        id: "activity-1",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "activity-1",
        activity: { activity_id: "a1", seq: 1, kind: "read", status: "active", key: "reading" },
      }),
      row({
        id: "structure-local",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "structure-1",
        content: "",
        blocks: [{
          kind: "video_storyboard",
          composition_id: "composition-1",
          composition_version_id: "version-1",
          version: 1,
        }],
      }),
    ]
    expect(visibleFrontierForTurn(rows, "t1", new Set(["structure-1"]))).toEqual({
      prose: [{ message_id: "partial-1", visible_chars: 3 }],
      activity_ids: ["activity-1"],
      structure_ids: ["structure-1"],
    })
  })

  it("does not infer visibility from mounted structure payloads", () => {
    const rows = [
      row({ id: "t1", role: "user", turnId: "t1", content: "request" }),
      row({
        id: "storyboard-local",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "storyboard-1",
        blocks: [{
          kind: "video_storyboard",
          composition_id: "composition-1",
          composition_version_id: "version-1",
          version: 1,
        }],
      }),
      row({
        id: "candidate-local",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "candidate-1",
        candidates: {
          candidateSetId: "set-1",
          topic: "topic",
          assetId: null,
          members: [{ start: 0, end: 1, excerpt: "excerpt" }],
          selected: [],
        },
      }),
    ]
    // Mounted/hidden rows have no renderer registration, so they cannot turn
    // a zero-visible Stop into a cancellation.
    expect(visibleFrontierForTurn(rows, "t1").structure_ids).toEqual([])
  })

  it("keeps a renderer-registered structure without inventing visible prose", () => {
    const rows = [
      row({ id: "t1", role: "user", turnId: "t1", content: "request" }),
      row({
        id: "structure-local",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "structure-1",
        blocks: [{
          kind: "video_storyboard",
          composition_id: "composition-1",
          composition_version_id: "version-1",
          version: 1,
        }],
      }),
      row({
        id: "partial-local",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "partial-1",
        content: "buffered only",
      }),
    ]
    const frontier = visibleFrontierForTurn(rows, "t1", new Set(["structure-1"]))
    const stopped = applyStoppedTurnFrontier(rows, new Set(["t1"]), "cancelled", frontier)
    expect(stopped.map((message) => message.id)).toEqual(["t1", "structure-local"])
    expect(stopped[1].blocks).toHaveLength(1)
  })

  it("retracts a Turn whose interim prose is persisted but never displayed", () => {
    const rows = [
      row({ id: "t1", role: "user", turnId: "t1", content: "restore me" }),
      row({
        id: "interim-1",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "interim-1",
        content: "unseen",
      }),
      row({ id: "t2", role: "user", turnId: "t2", content: "successor" }),
    ]
    const frontier = visibleFrontierForTurn(rows, "t1")
    expect(frontier.prose).toEqual([])
    const stopped = applyStoppedTurnFrontier(rows, new Set(["t1"]), "retracted", frontier)
    expect(stopped.map((message) => message.id)).toEqual(["t2"])
    // Replaying the same projection cannot resurrect retracted content.
    expect(applyStoppedTurnFrontier(stopped, new Set(["t1"]), "retracted", frontier))
      .toEqual(stopped)
  })

  it("keeps only the visible prefix and retires a visible active Activity", () => {
    const rows = [
      row({ id: "t1", role: "user", turnId: "t1", content: "keep request" }),
      row({
        id: "local-partial",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "partial-1",
        content: "abcdef",
        clientVisibleAtMs: 10,
        streaming: true,
      }),
      row({
        id: "interim-unseen",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "interim-unseen",
        content: "not shown",
      }),
      row({
        id: "activity-1",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "activity-1",
        activity: { activity_id: "a1", seq: 1, kind: "read", status: "active", key: "reading" },
      }),
    ]
    const frontier = visibleFrontierForTurn(rows, "t1")
    // More text may be released while the control request is in flight; the
    // reported frontier remains authoritative when the result lands.
    frontier.prose[0].visible_chars = 3
    const stopped = applyStoppedTurnFrontier(rows, new Set(["t1"]), "cancelled", frontier)
    expect(stopped.map((message) => message.id)).toEqual(["t1", "local-partial", "activity-1"])
    expect(stopped[1]).toMatchObject({ content: "abc", streaming: false })
    expect(stopped[2].activity?.status).toBe("cancelled")
  })

  it("counts and clips visible prefixes in Unicode code points", () => {
    const rows = [
      row({ id: "t1", role: "user", turnId: "t1", content: "request" }),
      row({
        id: "local",
        role: "assistant",
        turnId: "t1",
        serverMessageId: "partial-emoji",
        content: "ab😀def",
        clientVisibleAtMs: 10,
      }),
    ]
    const frontier = visibleFrontierForTurn(rows, "t1")
    expect(frontier.prose[0].visible_chars).toBe(6)
    frontier.prose[0].visible_chars = 3
    const stopped = applyStoppedTurnFrontier(rows, new Set(["t1"]), "cancelled", frontier)
    expect(stopped[1].content).toBe("ab😀")
  })

  it("an old stream's Stop cannot clear or trim its successor Turn", () => {
    const successor = row({
      id: "local-t2",
      role: "assistant",
      turnId: "t2",
      serverMessageId: "partial-2",
      content: "successor reply",
      clientVisibleAtMs: 20,
    })
    const rows = [
      row({ id: "t1", role: "user", turnId: "t1", content: "old" }),
      row({ id: "t2", role: "user", turnId: "t2", content: "new" }),
      successor,
    ]
    const stopped = applyStoppedTurnFrontier(rows, new Set(["t1"]), "retracted", {
      prose: [], activity_ids: [], structure_ids: [],
    })
    expect(stopped).toEqual([rows[1], successor])
  })
})
