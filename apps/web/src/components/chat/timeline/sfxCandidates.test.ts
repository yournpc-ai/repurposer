import { describe, expect, it } from "vitest"

import { reduceCandidateFrame } from "@/lib/chatStreamFrames"
import { isAudioCandidateSurface } from "../video/AudioCandidateSurface"
import {
  buildConversationBlocks,
  buildConversationUnits,
} from "./project"
import { candidatesLog, mapHistoryRows, type HistoryRow } from "./history"

const audioMember = {
  start: 0,
  end: 3.2,
  excerpt: "Door click",
  speaker: null,
  provider: "freesound",
  provider_id: "12345",
  title: "Door click",
  author: "field-recordist",
  duration_seconds: 3.2,
  source_url: "https://freesound.org/people/field-recordist/sounds/12345/",
  preview_url: "https://cdn.freesound.org/previews/123/12345-hq.mp3",
  license: "CC0",
  attribution: '"Door click" by field-recordist on Freesound (CC0 1.0)',
  query: "door click",
}

const setEvent = {
  kind: "set" as const,
  candidate_set_id: "sfx-set-1",
  topic: "door click",
  asset_id: null,
  members: [audioMember],
}

describe("SFX candidate live/history parity", () => {
  it("keeps the complete audio member facts in the existing kind:set envelope", () => {
    const live = reduceCandidateFrame([], setEvent, "2026-11-02T00:00:00Z")[0]
      .candidates
    const replayed = candidatesLog({ type: "candidates_log", events: [setEvent] })
    expect(live).toBeDefined()
    expect(replayed).toHaveLength(1)
    expect(replayed?.[0]).toMatchObject({
      kind: "set",
      surface: {
        candidateSetId: "sfx-set-1",
        members: [audioMember],
      },
    })
    expect(replayed?.[0].kind === "set" && replayed[0].surface.members).toEqual(
      live?.members,
    )
    expect(isAudioCandidateSurface(live!)).toBe(true)
  })

  it("keeps legacy transcript candidates on the no-playback fallback", () => {
    const replayed = candidatesLog({
      type: "candidates_log",
      events: [{
        kind: "set",
        candidate_set_id: "transcript-set",
        topic: "opening",
        asset_id: "asset-1",
        members: [{ start: 1, end: 2.5, excerpt: "Actual speech", speaker: "A" }],
      }],
    })
    expect(replayed?.[0].kind === "set" && replayed[0].surface.members[0])
      .toMatchObject({ start: 1, end: 2.5, excerpt: "Actual speech", speaker: "A" })
    expect(
      replayed?.[0].kind === "set" && isAudioCandidateSurface(replayed[0].surface),
    ).toBe(false)
  })

  it("replays the persisted set after its final reply and selection adds no card", () => {
    const base = { question: null, answer: null, workflow_run_id: null }
    const rows: HistoryRow[] = [
      {
        ...base,
        id: "user-1",
        role: "user",
        content: "find a click",
        turn_id: "turn-1",
        seq: 11,
      },
      {
        ...base,
        id: "reply-1",
        role: "assistant",
        content: "Three candidates are ready.",
        turn_id: "turn-1",
        seq: 12,
      },
      {
        ...base,
        id: "candidate-log-1",
        role: "assistant",
        content: "",
        turn_id: "turn-1",
        seq: 13,
        intent: { type: "candidates_log", events: [setEvent] },
      },
      {
        ...base,
        id: "selection-log-1",
        role: "assistant",
        content: "",
        turn_id: "turn-2",
        seq: 20,
        intent: {
          type: "candidates_log",
          events: [{
            kind: "selection",
            candidate_set_id: "sfx-set-1",
            selected: [0],
          }],
        },
      },
    ]
    const history = mapHistoryRows(rows, { t: (key) => key })
    expect(history.map((message) => message.id)).toEqual([
      "user-1",
      "reply-1",
      "candidate-log-1-cand-sfx-set-1",
    ])
    expect(history[2].candidates?.selected).toEqual([0])
    const blocks = buildConversationBlocks(buildConversationUnits(history))
    expect(blocks).toHaveLength(1)
    expect(blocks[0].kind).toBe("turn")
    expect(blocks[0].kind === "turn" && blocks[0].units.map((unit) =>
      unit.kind === "message" ? unit.message.id : unit.rowKey,
    )).toEqual(history.map((message) => message.id))
  })
})
