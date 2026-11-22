import assert from "node:assert/strict";
import test from "node:test";
import { videoSpecSchema } from "./schema";

function textSpec() {
  return {
    family: "video",
    format: 1,
    fps: { num: 30, den: 1 },
    width: 1920,
    height: 1080,
    background: "#FFFFFF",
    sample_rate: 48000,
    duration_frames: 120,
    fonts: [],
    tracks: [{
      track_id: "trk",
      kind: "visual",
      role: "title",
      order: 0,
      clips: [{
        clip_id: "clp",
        start_frame: 0,
        end_frame: 120,
        scene_id: "scn",
        source: null,
        object: {
          kind: "text",
          object_id: "obj",
          text: "One two",
          layout: { x: 0, y: 0, width: 800, height: 200 },
          style: {
            font_size: 170,
            color: "#000000",
            background: null,
            weight: 400,
            align: "left",
            line_height: 1,
            font: { font_id: "font", digest: "f".repeat(64) },
          },
          transform: { x: 0, y: 0, scale: 1, rotation: 0, origin: "center" },
          opacity: 1,
          segmentation_version: "scalar-grapheme-v1",
          layout_version: "explicit-line-inline-v1",
          parts: [{
            part_id: "line:0:7:test",
            kind: "line",
            text: "One two",
            text_range: { start: 0, end: 7 },
            layout_range: { start: 0, end: 7 },
          }],
        },
        animations: [
          {
            animation_id: "blur",
            target_object_id: "obj",
            target_text_part_id: null,
            property: "filter.blur",
            keyframes: [{ at: 0, value: 18, easing: { kind: "linear" } }],
          },
          {
            animation_id: "tracking",
            target_object_id: "obj",
            target_text_part_id: null,
            property: "text.letter_spacing",
            keyframes: [{ at: 0, value: -0.025, easing: { kind: "linear" } }],
          },
        ],
      }],
    }],
    provenance: {
      composition_id: "composition",
      composition_version_id: "version",
      content_digest: "d".repeat(64),
    },
  };
}

test("video-spec accepts the blur-slide text properties", () => {
  const parsed = videoSpecSchema.parse(textSpec());
  assert.deepEqual(
    parsed.tracks[0].clips[0].animations.map((animation) => animation.property),
    ["filter.blur", "text.letter_spacing"],
  );
});

test("legacy text styles read with zero letter spacing", () => {
  const parsed = videoSpecSchema.parse(textSpec());
  const object = parsed.tracks[0].clips[0].object;
  assert.equal(object.kind, "text");
  if (object.kind === "text") assert.equal(object.style.letter_spacing, 0);
});
