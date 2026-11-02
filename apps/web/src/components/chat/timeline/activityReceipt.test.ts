import { describe, expect, it } from "vitest"

import { foldCategories } from "./activity"
import { activityRowFrame, parseActivityReceipt } from "./history"
import type { ActivityRowFrame, VideoReviewReceipt } from "./types"

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
    receipt: value as VideoReviewReceipt,
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
    expect(categories[0].receipt?.frames[0].frame_id).toBe("F01")
    expect(categories[1].receipt?.frames[0].frame_id).toBe("F03")
    expect(categories[1].receipt?.findings).toEqual([])
  })

  it("drops unknown audio codes without inventing a replacement", () => {
    const parsed = parseActivityReceipt({
      ...receipt,
      output_issue_codes: ["AUDIO_FUTURE_CODE", "AUDIO_SILENT"],
    })
    expect(parsed?.output_issue_codes).toEqual(["AUDIO_SILENT"])
    expect(parsed?.findings).toEqual(receipt.findings)
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
