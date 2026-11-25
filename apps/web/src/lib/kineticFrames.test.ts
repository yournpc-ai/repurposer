import assert from "node:assert/strict";
import { test } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { KineticBeatBlock } from "../../../../packages/video-remotion/src/blocks/KineticBeatBlock";
import { UiMontageBlock } from "../../../../packages/video-remotion/src/blocks/UiMontageBlock";
import type { Frame } from "../../../../packages/video-remotion/src/blocks/Stage";

const frame: Frame = {
  tSec: 0, durSec: 2, width: 1920, height: 1080, scaleUnit: 1, fontFamily: "sans-serif",
  resources: ["first.png", "second.png", "third.png"],
};

test("typewriter phases preserve clusters, retract the first word and hold the last", () => {
  const props = {
    mode: "typewriter_swap" as const, words: ["👩🏽‍💻设计", "Launch"], items: [], rows: 3, entrance_duration_s: 0.25,
  };
  const textAt = (tSec: number) => renderToStaticMarkup(createElement(KineticBeatBlock, {
    props, frame: { ...frame, tSec },
  })).replace(/<[^>]*>/g, "");
  assert.equal(textAt(0), "");
  assert.equal(textAt(0.1), "👩🏽‍💻");
  assert.equal(textAt(0.45), "👩🏽‍💻设计");
  assert.equal(textAt(0.85), "👩🏽‍💻");
  assert.equal(textAt(0.95), "");
  assert.equal(textAt(1.95), "Launch");
  assert.equal(textAt(0.45), "👩🏽‍💻设计");
});

test("rapid cuts switch pinned screens on the beat and a single screen keeps moving", () => {
  const props = { layout_mode: "rapid_cut" as const, cut_interval_s: 0.35, entrance_duration_s: 0.35 };
  const at = (tSec: number, resources = frame.resources) => renderToStaticMarkup(createElement(UiMontageBlock, {
    props, frame: { ...frame, tSec, resources },
  }));
  assert.match(at(0.34), /<img src="first.png"/);
  assert.match(at(0.35), /<img src="second.png"/);
  assert.doesNotMatch(at(0.35), /<img src="first.png"/);
  assert.match(at(0.70), /<img src="third.png"/);
  assert.notEqual(at(0.4, ["one.png"]), at(1.6, ["one.png"]));
  assert.equal(at(0.35), at(0.35));
});
