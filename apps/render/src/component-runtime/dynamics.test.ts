import assert from "node:assert/strict";
import test from "node:test";

import { assertDynamicComponentFrames } from "./dynamics";
import { ComponentPolicyError } from "./policy";

test("static TSX output is rejected from bounded real-frame samples", () => {
  const staticPixels = Buffer.from("same rendered AbsoluteFill pixels");
  assert.throws(
    () => assertDynamicComponentFrames([
      { frame: 0, png: staticPixels },
      { frame: 30, png: staticPixels },
      { frame: 59, png: staticPixels },
    ]),
    ComponentPolicyError,
  );
});

test("one changed sampled frame proves bounded dynamic output without source scans", () => {
  assert.doesNotThrow(() => assertDynamicComponentFrames([
    { frame: 0, png: Buffer.from("first") },
    { frame: 30, png: Buffer.from("changed") },
    { frame: 59, png: Buffer.from("first") },
  ]));
});
