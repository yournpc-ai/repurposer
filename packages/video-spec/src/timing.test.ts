import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { secondsToTicks, ticksToFrames, ticksToSeconds } from "./timing";

const fixture = JSON.parse(
  readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "../fixtures/timing_golden.json"),
    "utf8",
  ),
);

test("ticks_to_frames golden law (exact round-half-up, rational fps)", () => {
  for (const c of fixture.ticks_to_frames) {
    assert.equal(
      ticksToFrames(c.ticks, c.rate, c.fps_num, c.fps_den),
      c.frames,
      `ticks=${c.ticks} rate=${c.rate} fps=${c.fps_num}/${c.fps_den}`,
    );
  }
});

test("seconds_to_ticks golden law", () => {
  for (const c of fixture.seconds_to_ticks) {
    assert.equal(secondsToTicks(c.seconds, c.rate), c.ticks, `seconds=${c.seconds}`);
  }
});

test("negative ticks are rejected, never silently clamped", () => {
  assert.throws(() => ticksToFrames(-1, 90000, 30));
  assert.throws(() => secondsToTicks(-0.5, 90000));
});

test("ticksToSeconds is display-only inverse", () => {
  assert.equal(ticksToSeconds(45000, 90000), 0.5);
});
