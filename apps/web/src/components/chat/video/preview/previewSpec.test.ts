import { describe, expect, it } from "vitest"

import { parsePreviewSpec, parseScopedPreviewSpec, sameScrubTarget, type VideoScrubScope } from "./previewSpec"

const identity = {
  composition_id: "composition-1",
  composition_version_id: "version-1",
  content_digest: "d".repeat(64),
}

function previewSpec() {
  return {
    family: "video",
    format: 1,
    fps: { num: 30, den: 1 },
    width: 640,
    height: 360,
    background: "#000000",
    sample_rate: 48000,
    duration_frames: 30,
    fonts: [],
    tracks: [{
      track_id: "track-1",
      kind: "visual",
      role: "main",
      order: 0,
      clips: [{
        clip_id: "clip-1",
        start_frame: 0,
        end_frame: 30,
        scene_id: "scene-1",
        source: null,
        object: {
          kind: "shape",
          object_id: "object-1",
          shape: "rect",
          layout: { x: 0, y: 0, width: 640, height: 360 },
          fill: "#ffffff",
          stroke: null,
          stroke_width: 0,
          corner_radius: 0,
          path: null,
          transform: { x: 0, y: 0, scale: 1, rotation: 0, origin: "center" },
          opacity: 1,
        },
        animations: [],
      }],
    }],
    provenance: identity,
  }
}

describe("composition preview spec admission", () => {
  it("accepts a supported spec for the exact immutable version", () => {
    expect(parsePreviewSpec(previewSpec(), identity).provenance).toEqual(identity)
  })

  it("rejects malformed specs", () => {
    expect(() => parsePreviewSpec(
      { ...previewSpec(), duration_frames: 0 }, identity,
    )).toThrow("Invalid video preview spec")
  })

  it("rejects schema-valid input outside the shared adapter capabilities", () => {
    expect(() => parsePreviewSpec(
      { ...previewSpec(), fps: { num: 30000, den: 1001 } }, identity,
    )).toThrow("fractional fps")
  })

  it("rejects provenance drift even when the spec itself is valid", () => {
    expect(() => parsePreviewSpec(previewSpec(), {
      ...identity,
      composition_version_id: "version-2",
    })).toThrow("Video preview identity mismatch")
  })
})

describe("scoped Scrub admission", () => {
  it("matches a persisted JSONB window independently of key order", () => {
    const window = { kind: "range", start_seconds: 7, end_seconds: 9 } as const
    expect(sameScrubTarget({ kind: "range", end_seconds: 9, start_seconds: 7 }, window)).toBe(true)
    expect(sameScrubTarget({ ...window, end_seconds: 8 }, window)).toBe(false)
    expect(sameScrubTarget({ ...window, kind: "segment", scene_id: "scene" }, window)).toBe(false)
  })

  const scope: VideoScrubScope = {
    target: { kind: "object", object_id: "object-1" },
    source_range_seconds: { start: 0, end: 1 },
    isolated_object: true,
    clip_ids: ["clip-1"],
  }

  it("accepts only the isolated Object's local spec", () => {
    expect(parseScopedPreviewSpec(previewSpec(), scope, identity).duration_frames).toBe(30)
  })

  it("rejects an old unscoped whole-composition preview", () => {
    expect(() => parseScopedPreviewSpec(previewSpec(), undefined, identity))
      .toThrow("Video preview scope missing")
  })

  it("rejects a spec that escapes the persisted target", () => {
    const escaped = previewSpec()
    escaped.tracks[0].clips[0].clip_id = "another-clip"
    expect(() => parseScopedPreviewSpec(escaped, scope, identity))
      .toThrow("Video preview escaped its Scrub scope")
  })
})
