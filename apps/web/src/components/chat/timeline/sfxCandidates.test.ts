import { describe, expect, it } from "vitest"

import { reduceCandidateFrame } from "@/lib/chatStreamFrames"
import {
  isAudioCandidateMember,
  isAudioCandidateSurface,
} from "../video/AudioCandidateSurface"
import {
  buildConversationBlocks,
  conversationBlockUnits,
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
  kind: "sfx_set" as const,
  candidate_set_id: "sfx-set-1",
  topic: "door click",
  asset_id: null,
  members: [audioMember],
}

const musicId = "6f27e054-cd2b-4c0f-b77b-99b72292d7b5"
const musicMember = {
  start: 0,
  end: 96.4,
  excerpt: "Focused Lines",
  speaker: null,
  provider: "music_library",
  provider_id: musicId,
  music_id: musicId,
  title: "Focused Lines",
  author: "Library Artist",
  duration_seconds: 96.4,
  source_url: null,
  preview_url: `/api/v1/music/${musicId}/stream`,
  license: "Library license",
  attribution: "Focused Lines by Library Artist",
  query: "focused electronic",
}

const musicSetEvent = {
  kind: "music_set" as const,
  candidate_set_id: "music-set-1",
  topic: "focused electronic",
  asset_id: null,
  members: [musicMember],
}

describe("SFX candidate live/history parity", () => {
  it("keeps complete audio facts in the sfx_set envelope on live and history", () => {
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
    const base = { question: null, answer: null }
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
    expect(blocks[0].kind === "turn" && conversationBlockUnits(blocks[0]).map((unit) =>
      unit.kind === "message" ? unit.message.id : unit.rowKey,
    )).toEqual(history.map((message) => message.id))
  })
})

describe("Music library candidate history", () => {
  it("replays every local member fact and retains the music_set surface kind", () => {
    const live = reduceCandidateFrame([], musicSetEvent, "2026-11-02T00:00:00Z")[0]
      .candidates
    const replayed = candidatesLog({
      type: "candidates_log",
      events: [musicSetEvent],
    })
    expect(replayed).toHaveLength(1)
    expect(replayed?.[0]).toMatchObject({
      kind: "set",
      surface: {
        kind: "music_set",
        candidateSetId: "music-set-1",
        assetId: null,
      },
    })
    expect(replayed?.[0].kind === "set" && replayed[0].surface.members)
      .toEqual([musicMember])
    expect(live?.kind).toBe("music_set")
    expect(live?.members).toEqual([musicMember])
    expect(replayed?.[0].kind === "set" && isAudioCandidateSurface(replayed[0].surface))
      .toBe(true)
  })

  it("accepts an absent source URL but rejects mismatched or provider-mixed members", () => {
    expect(isAudioCandidateMember({ ...musicMember, source_url: "" })).toBe(true)
    expect(isAudioCandidateMember({
      ...musicMember,
      music_id: "c1f3ee14-b143-4c62-9722-0d9f37266776",
    })).toBe(false)
    expect(isAudioCandidateMember({
      ...musicMember,
      provider: "freesound",
      source_url: "https://freesound.org/people/library/sounds/12345/",
      license: "CC0",
    })).toBe(false)

    const replayed = candidatesLog({
      type: "candidates_log",
      events: [musicSetEvent],
    })
    const surface = replayed?.[0].kind === "set" ? replayed[0].surface : undefined
    expect(surface && isAudioCandidateSurface({
      ...surface,
      members: [musicMember, audioMember],
    })).toBe(false)
  })
})
