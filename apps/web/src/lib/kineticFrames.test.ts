import assert from "node:assert/strict";
import { test } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { KineticBeatBlock } from "../../../../packages/video-remotion/src/blocks/KineticBeatBlock";
import { UiMontageBlock } from "../../../../packages/video-remotion/src/blocks/UiMontageBlock";
import { evaluateCamera } from "../../../../packages/video-remotion/src/engine/camera";
import { activeFocusStyle, type Frame } from "../../../../packages/video-remotion/src/blocks/Stage";

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

test("a delayed word starts at its cue even when the outgoing interval is long", () => {
  const props = {
    mode: "typewriter_swap" as const, words: ["Ready", "Go"], word_reveals_s: [0.4, 1.7],
    items: [], rows: 3, entrance_duration_s: 0.25,
  };
  const at = (tSec: number) => renderToStaticMarkup(createElement(KineticBeatBlock, { props, frame: { ...frame, tSec } }));
  assert.match(at(0.2), /visibility:hidden/);
  assert.match(at(1.1), />Ready</);
  assert.doesNotMatch(at(1.65), />Go</);
  assert.match(at(1.95), />Go</);
});

test("spoken focus moves between cards and settles the group at the cut", () => {
  const focus = (t: number, i: number) => activeFocusStyle(t, [0.3, 1.4], i, 3);
  assert.deepEqual(focus(0.1, 1), { scale: 1, opacity: 1 });
  assert.deepEqual(focus(0.6, 0), { scale: 1.025, opacity: 1 });
  assert.deepEqual(focus(1.7, 0), { scale: 0.99, opacity: 0.78 });
  assert.deepEqual(focus(1.7, 1), { scale: 1.025, opacity: 1 });
  assert.deepEqual(focus(2.95, 0), { scale: 1, opacity: 1 });
});

test("step camera covers the viewport at both edges at every supported zoom", () => {
  for (const zoom of [1, 1.32, 2.2]) {
    for (const x of [0, 0.08, 0.5, 0.92, 1]) {
      const camera = evaluateCamera("flat", 2, 5, x, 1-x, zoom, 0, 1, { motion: "static", stepCamera: true });
      const offsets = camera.viewport.match(/translate\(([-.\d]+)%, ([-.\d]+)%\) scale\(([-.\d]+)\)/);
      assert.ok(offsets);
      assert.equal(Number(offsets[3]), zoom);
      for (const pan of offsets.slice(1, 3).map(Number)) {
        assert.ok(pan <= 0 && pan + 100 * zoom >= 100 - 1e-8);
      }
    }
  }
  assert.equal(evaluateCamera("scroll_reveal", 2, 4, 0.5, 0.5, 1.05, 0.1, 0.9).cropY, 50);
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
