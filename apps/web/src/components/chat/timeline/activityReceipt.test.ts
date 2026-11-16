import { describe, expect, it } from "vitest"

import { foldCategories } from "./activity"
import { activityRowFrame, parseActivityReceipt } from "./history"
import type {
  ActivityReceipt,
  ActivityRowFrame,
  ComponentReceipt,
  MusicSearchReceipt,
  MusicSelectionReceipt,
  SfxImportReceipt,
  SfxSearchReceipt,
  VideoReviewReceipt,
  VideoRevisionReceipt,
} from "./types"

const receipt = {
  kind: "video_review",
  frames: [
    { frame_id: "F01", time_seconds: 1.5 },
    { frame_id: "F02", time_seconds: 3 },
  ],
  findings: [
    {
      kind: "observed_issue",
      frame_id: "F01",
      observed: "The title is clipped.",
    },
    {
      kind: "aesthetic_suggestion",
      frame_id: "F02",
      observed: "The closing frame could have clearer hierarchy.",
    },
  ],
  output_issue_codes: ["AUDIO_QUIET"],
  scope: {
    actual_output_decoded: true,
    static_frames_checked: true,
    deterministic_output_checks: true,
    sampled_frame_signals_checked: true,
    audio_signal_checked: true,
    motion_and_transitions_checked: false,
    audio_and_av_sync_checked: false,
  },
} satisfies VideoReviewReceipt

function liveRow(value: unknown, id = "a1"): ActivityRowFrame {
  return {
    activity_id: id,
    kind: "draft",
    status: "completed",
    key: "chat.activity.videoReviewDone",
    receipt: value as ActivityReceipt,
  }
}

describe("video review Activity receipt", () => {
  it("uses the same evidence shape for live rows and history hydration", () => {
    const history = activityRowFrame({
      type: "activity",
      frame: { ...liveRow(receipt), receipt },
    })
    expect(history).toBeDefined()
    expect(history?.receipt).toEqual(parseActivityReceipt(receipt))

    const categories = foldCategories([history!, liveRow(receipt, "a2")])
    expect(categories).toHaveLength(2)
    expect(categories.map((category) => category.receipt)).toEqual([
      parseActivityReceipt(receipt),
      parseActivityReceipt(receipt),
    ])
  })

  it("keeps receipt-bearing reviews in evidence order instead of collapsing them to ×N", () => {
    const second = {
      ...receipt,
      frames: [{ frame_id: "F03", time_seconds: 8.25 }],
      findings: [],
      output_issue_codes: ["AUDIO_CLIPPED"],
    } satisfies VideoReviewReceipt
    const categories = foldCategories([liveRow(receipt), liveRow(second, "a2")])
    expect(categories.map((category) => category.repeat)).toEqual([1, 1])
    expect(categories[0].receipt?.kind === "video_review" &&
      categories[0].receipt.frames[0].frame_id).toBe("F01")
    expect(categories[1].receipt?.kind === "video_review" &&
      categories[1].receipt.frames[0].frame_id).toBe("F03")
    expect(categories[1].receipt?.kind === "video_review" &&
      categories[1].receipt.findings).toEqual([])
  })

  it("drops unknown audio codes without inventing a replacement", () => {
    const parsed = parseActivityReceipt({
      ...receipt,
      output_issue_codes: ["AUDIO_FUTURE_CODE", "AUDIO_SILENT"],
    })
    expect(parsed?.kind === "video_review" && parsed.output_issue_codes).toEqual(["AUDIO_SILENT"])
    expect(parsed?.kind === "video_review" && parsed.findings).toEqual(receipt.findings)
  })

  it("falls back to ordinary categories for old, missing-field, or malformed receipts", () => {
    const old = activityRowFrame({ type: "activity", frame: liveRow(undefined) })
    expect(old?.receipt).toBeUndefined()
    expect(parseActivityReceipt(null)).toBeUndefined()
    expect(parseActivityReceipt({ ...receipt, kind: "other" })).toBeUndefined()
    expect(parseActivityReceipt({ ...receipt, frames: [{ frame_id: "F01" }] })).toBeUndefined()
    expect(parseActivityReceipt({
      ...receipt,
      scope: { ...receipt.scope, audio_signal_checked: "yes" },
    })).toBeUndefined()

    const categories = foldCategories([
      liveRow({ ...receipt, findings: [{ kind: "unknown" }] }),
      liveRow({ ...receipt, findings: [{ kind: "unknown" }] }, "a2"),
    ])
    expect(categories).toHaveLength(1)
    expect(categories[0].repeat).toBe(2)
    expect(categories[0].receipt).toBeUndefined()
  })
})

const component = {
  kind: "component",
  components: [{
    clip_id: "clp_component",
    program_digest: "a".repeat(64),
    media_digest: "b".repeat(64),
    poster_url: "https://media.test/component.png",
    preview_frame: 30,
    dynamic_sample_frames: [0, 30, 59],
    duration_frames: 60,
    fps: 15,
  }],
} satisfies ComponentReceipt

const revision = {
  kind: "video_revision",
  version: 3,
  settings: ["background"],
  scenes: {
    added: [],
    removed: [],
    moved: [{ scene_id: "scn_main", from_seconds: 2, to_seconds: 3 }],
  },
  clips: {
    added: [{ clip_id: "clp_audio", kind: "audio" }],
    removed: [],
    updated: [{ clip_id: "clp_component", changes: ["object"] }],
  },
  transitions_changed: false,
  components: component.components,
} satisfies VideoRevisionReceipt

const sfx = {
  kind: "sfx_search",
  candidate_set_id: "11111111-1111-1111-1111-111111111111",
  topic: "door click",
  members: [{ member_index: 0, ordinal: 1, title: "Door click", duration_seconds: 3.2 }],
} satisfies SfxSearchReceipt

const sfxImport = {
  kind: "sfx_import",
  candidate_set_id: sfx.candidate_set_id,
  member_index: 0,
  asset_id: "asset-1",
  snapshot_id: "snapshot-1",
  snapshot_digest: "e".repeat(64),
  title: "Door click",
  duration_seconds: 3.2,
} satisfies SfxImportReceipt

const musicSearch = {
  kind: "music_search",
  candidate_set_id: "22222222-2222-2222-2222-222222222222",
  topic: "focused electronic",
  members: [{ member_index: 0, ordinal: 1, title: "Focused Lines", duration_seconds: 96 }],
} satisfies MusicSearchReceipt

const musicSelection = {
  kind: "music_selection",
  candidate_set_id: musicSearch.candidate_set_id,
  member_index: 0,
  music_id: "6f27e054-cd2b-4c0f-b77b-99b72292d7b5",
  title: "Focused Lines",
  duration_seconds: 96,
} satisfies MusicSelectionReceipt

describe("D5 typed work receipts", () => {
  it("keeps component, revision, SFX and Music evidence identical through live and history", () => {
    for (const evidence of [component, revision, sfx, sfxImport, musicSearch, musicSelection]) {
      expect(parseActivityReceipt(evidence)).toEqual(evidence)
      const history = activityRowFrame({
        type: "activity",
        frame: { ...liveRow(evidence), receipt: evidence },
      })
      expect(history?.receipt).toEqual(evidence)
    }
    const categories = foldCategories([
      liveRow(component),
      liveRow(revision, "a2"),
      liveRow(sfx, "a3"),
      liveRow(sfxImport, "a4"),
      liveRow(musicSearch, "a5"),
      liveRow(musicSelection, "a6"),
    ])
    expect(categories.map((category) => category.repeat)).toEqual([1, 1, 1, 1, 1, 1])
    expect(categories.map((category) => category.receipt?.kind)).toEqual([
      "component",
      "video_revision",
      "sfx_search",
      "sfx_import",
      "music_search",
      "music_selection",
    ])
  })

  it("drops malformed new evidence without losing the ordinary Activity row", () => {
    expect(parseActivityReceipt({
      ...component,
      components: [{ ...component.components[0], dynamic_sample_frames: [0] }],
    })).toBeUndefined()
    expect(parseActivityReceipt({
      ...revision,
      clips: { ...revision.clips, updated: [{ clip_id: "clp_component", changes: ["raw_args"] }] },
    })).toBeUndefined()
    expect(parseActivityReceipt({ ...sfx, members: [] })).toBeUndefined()
    expect(parseActivityReceipt({ ...musicSearch, members: [] })).toBeUndefined()
    expect(parseActivityReceipt({
      ...musicSelection,
      duration_seconds: "96",
    })).toBeUndefined()
    expect(activityRowFrame({
      type: "activity",
      frame: { ...liveRow(component), receipt: { kind: "future_receipt" } },
    })).toBeDefined()
  })
})
