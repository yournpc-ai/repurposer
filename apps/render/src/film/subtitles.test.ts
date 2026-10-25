import assert from "node:assert/strict";
import test from "node:test";
import { filmSpecSchema } from "./schema";

const spec = (scene: object) => ({family: "film", theme: {canvas: "#FFFFFF", ink: "#000000"}, scenes: [
  {type: "words", frames: 120, dark: false, lines: ["Picture"], ...scene},
]});
const track = {cues: [{at: 0.5, end: 2, text: "Independent subtitles"}]};

test("silent scene accepts independent subtitles and resolves style defaults", () => {
  const scene = filmSpecSchema.parse(spec({subtitle_track: track})).scenes[0];
  assert.equal(scene.audio, undefined);
  assert.equal(scene.subtitle_track?.style.enter, "fade");
  assert.equal(scene.subtitle_track?.style.color, "#FFFFFF");
  assert.equal(scene.subtitle_track?.style.background, "#000000");
});

test("obsolete captions field, overlapping and out-of-window cues are rejected", () => {
  assert.equal(filmSpecSchema.safeParse(spec({captions: []})).success, false);
  for (const cues of [
    [{at: 1, end: 1, text: "bad"}],
    [{at: 0, end: 5, text: "too long"}],
    [{at: 0, end: 2, text: "first"}, {at: 1, end: 3, text: "overlap"}],
  ]) {
    assert.equal(filmSpecSchema.safeParse(spec({subtitle_track: {cues}})).success, false);
  }
});
