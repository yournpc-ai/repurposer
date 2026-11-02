import assert from "node:assert/strict";
import test from "node:test";

import { bakeComponent, ComponentBakeError } from "./bake";
import { COMPONENT_DEPENDENCIES, type ComponentBakeRequest } from "./contract";

const request: ComponentBakeRequest = {
  runtime: "component-v1",
  program_digest: "a".repeat(64),
  dependencies: COMPONENT_DEPENDENCIES,
  code: "export default () => <AbsoluteFill />",
  parameters: {},
  output: { width: 640, height: 360, fps: 15, duration_frames: 60, background: "#101010" },
};

test("untrusted bake fails closed before touching the runner by default", async () => {
  const previous = process.env.COMPONENT_BAKE_ENABLED;
  delete process.env.COMPONENT_BAKE_ENABLED;
  try {
    await assert.rejects(() => bakeComponent(request), ComponentBakeError);
  } finally {
    if (previous === undefined) delete process.env.COMPONENT_BAKE_ENABLED;
    else process.env.COMPONENT_BAKE_ENABLED = previous;
  }
});
