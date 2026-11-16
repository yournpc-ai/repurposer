import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  componentBakeRequestSchema,
  COMPONENT_DEPENDENCIES,
  fixedResourceSchema,
  MAX_FIXED_RESOURCE_BASE64_CHARS,
  MAX_FIXED_RESOURCE_BYTES,
  MAX_TOTAL_FIXED_RESOURCE_BYTES,
} from "./contract";

function resource(data: Buffer) {
  return {
    path: "textures/page.png",
    digest: createHash("sha256").update(data).digest("hex"),
    content_type: "image/png" as const,
    data_base64: data.toString("base64"),
  };
}

test("fixed resource envelope accepts a full-page image above the former threshold", () => {
  const parsed = fixedResourceSchema.parse(resource(Buffer.alloc(5 * 1024 * 1024, 1)));
  assert.equal(Buffer.from(parsed.data_base64, "base64").length, 5 * 1024 * 1024);
});

test("fixed resource limits remain bounded", () => {
  assert.equal(MAX_FIXED_RESOURCE_BYTES, 16 * 1024 * 1024);
  assert.equal(MAX_TOTAL_FIXED_RESOURCE_BYTES, 32 * 1024 * 1024);
  assert.equal(MAX_FIXED_RESOURCE_BASE64_CHARS, 4 * Math.ceil(MAX_FIXED_RESOURCE_BYTES / 3));
  assert.throws(() => fixedResourceSchema.parse(resource(Buffer.alloc(MAX_FIXED_RESOURCE_BYTES + 3, 1))));
});

test("bake accepts the API's resource count and rejects one above it", () => {
  const image = resource(Buffer.from([1]));
  const resources = Array.from({ length: 65 }, (_, index) => ({
    ...image,
    path: `textures/card-${index}.png`,
  }));
  const request = {
    producer: "remotion-project",
    program_digest: image.digest,
    dependencies: COMPONENT_DEPENDENCIES,
    code: "export default function Visual() { return null; }",
    parameters: {},
    output: { width: 640, height: 360, fps: 30, duration_frames: 60, background: "#000000" },
  };
  assert.equal(componentBakeRequestSchema.parse({ ...request, resources: resources.slice(0, 64) }).resources.length, 64);
  assert.equal(componentBakeRequestSchema.safeParse({ ...request, resources }).success, false);
});
