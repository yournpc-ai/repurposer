import { describe, expect, it } from "vitest"

import {
  reduceCandidateFrame,
  releaseSettledCandidateRows,
  type CandidateEventPayload,
} from "@/lib/chatStreamFrames"
import { candidatesLog } from "./history"
import type { OverlayMessage } from "./types"

const set: CandidateEventPayload = {
  kind: "video_preset_set",
  candidate_set_id: "preset-set-1",
  topic: "native-video-presets",
  asset_id: null,
  turn_id: "turn-1",
  members: ["text-reveal", "typewriter"].map((preset_id) => ({
    start: 0,
    end: 4,
    excerpt: preset_id,
    provider: "native",
    preset_id,
    title: preset_id,
    preview_url: `https://media.example.com/${preset_id}.mp4`,
    preview_digest: "a".repeat(64),
    duration_seconds: 4,
    aspect: "16:9",
    width: 1920,
    height: 1080,
  })),
}

describe("video Preset candidate journey", () => {
  it("releases the complete set after final prose, then repaints only selection", () => {
    const pending = reduceCandidateFrame([], set, "2026-11-03T00:00:00Z")
    const user: OverlayMessage = { id: "turn-1", role: "user", content: "compare", turnId: "turn-1" }
    const reply: OverlayMessage = {
      id: "reply-1", role: "assistant", content: "Two options", turnId: "turn-1",
      streaming: false, proseDrainedAtMs: 100,
    }
    const released = releaseSettledCandidateRows([user, reply], pending, "reply-1")
    expect(released[2].candidates).toMatchObject({
      kind: "video_preset_set",
      candidateSetId: "preset-set-1",
      selected: [],
    })
    expect(released[2].candidates?.members.map((member) => member.preset_id))
      .toEqual(["text-reveal", "typewriter"])
    const selected = reduceCandidateFrame(released, {
      kind: "selection", candidate_set_id: "preset-set-1", selected: [1], turn_id: "turn-2",
    }, "2026-11-03T00:01:00Z")
    expect(selected.map((message) => message.id)).toEqual(released.map((message) => message.id))
    expect(selected[2].candidates?.selected).toEqual([1])
  })

  it("history replays the same complete set and rejects a partial ordinal array", () => {
    const replayed = candidatesLog({
      type: "candidates_log",
      events: [set, {
        kind: "selection", candidate_set_id: "preset-set-1", selected: [1],
      }],
    })
    expect(replayed?.[0]).toMatchObject({
      kind: "set",
      surface: {
        kind: "video_preset_set",
        candidateSetId: "preset-set-1",
        selected: [],
      },
    })
    expect(replayed?.[1]).toEqual({
      kind: "selection", candidateSetId: "preset-set-1", selected: [1],
    })
    const malformed = candidatesLog({
      type: "candidates_log",
      events: [{
        ...set,
        members: [set.members[0], { ...set.members[1], preview_url: null }],
      }],
    })
    expect(malformed).toEqual([])
  })
})
